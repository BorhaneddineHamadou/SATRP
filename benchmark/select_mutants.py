#!/usr/bin/env python3
"""Pick the matrix mutants from screen_classes.json under stratum/operator quotas.
usage: select_mutants.py <stack> [N=28] [SEED]  -> store/<stack>/selected.json
Mix target: ~55% partial, ~25% silent, ~10% mass-fail, ~10% borderline(partial with 1 trigger diff).
Dedupe: mutants from the same file whose (trig, above_floor) vectors are identical keep one."""
import json, os, sys, random, collections
HOME = os.path.expanduser('~')
STORE = f'{HOME}/satrp_mutation/ads/store'
stack = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 28; seed = int(sys.argv[3]) if len(sys.argv) > 3 else 20260929
MIX = {'partial': 0.55, 'silent': 0.25, 'mass-fail': 0.10, 'borderline': 0.10}
PER_FILE = {'openpilot': 5, 'transfuser': 12}[stack]   # TF has only 3 mutable files
PER_OP = 6
sc = json.load(open(f'{STORE}/{stack}/screen_classes.json'))
rng = random.Random(seed)
muts = [m for m in sc['mutants'] if m['cls'] not in ('stillborn', 'pending')]
# borderline = partial with exactly one trigger difference and no divergence
for m in muts:
    if m['cls'] == 'partial' and abs(m['triggers'] - m['base_triggers']) <= 1 and m['divergent'] == 0:
        m['cls2'] = 'borderline'
    else:
        m['cls2'] = m['cls']
# dedupe NEAR-duplicates only: same source file AND same source line (e.g. CSC x2/x05 of one literal,
# ROR/NEG of one condition) with an identical screen outcome vector. Six screen samples cannot
# establish redundancy between mutants at different sites, so those are all kept.
line_of = {}
for c in json.load(open(f'{STORE}/{stack}/candidates.json'))['candidates']:
    line_of[c['mid']] = (c['file'], c['line'])
seen = set(); uniq = []
rng.shuffle(muts)
for m in muts:
    vec = (line_of.get(m['mid']), tuple((r['trig'], r['above_floor']) for r in m['rows']))
    if m['cls2'] != 'silent' and vec in seen:
        continue
    seen.add(vec); uniq.append(m)
want = {k: round(N * v) for k, v in MIX.items()}
want['partial'] += N - sum(want.values())
picked, per_file, per_op = [], collections.Counter(), collections.Counter()
def ok(m):
    f = m['site'].split(':')[0]
    return per_file[f] < PER_FILE and per_op[m['op']] < PER_OP
for cls, w in want.items():
    pool = [m for m in uniq if m['cls2'] == cls]
    # prefer graded partials: sort by |trigger diff| descending variety -> shuffle already
    for m in pool:
        if w <= 0: break
        if ok(m) and m not in picked:
            picked.append(m); per_file[m['site'].split(':')[0]] += 1; per_op[m['op']] += 1; w -= 1
    if w > 0:
        print(f'  shortfall {w} in {cls}')
# fill any shortfall with remaining partials then silents
for m in uniq:
    if len(picked) >= N: break
    if m not in picked and ok(m) and m['cls2'] in ('partial', 'silent'):
        picked.append(m); per_file[m['site'].split(':')[0]] += 1; per_op[m['op']] += 1
out = dict(stack=stack, N=N, seed=seed, want=want,
           counts=dict(collections.Counter(m['cls2'] for m in picked)),
           per_op=dict(per_op), per_file=dict(per_file),
           selected=[m['mid'] for m in picked],
           detail=[dict(mid=m['mid'], site=m['site'], op=m['op'], cls=m['cls2'], trig=m['triggers'], base=m['base_triggers'], div=m['divergent']) for m in picked])
json.dump(out, open(f'{STORE}/{stack}/selected.json', 'w'), indent=1)
print(stack, 'selected', len(picked), out['counts'], out['per_op'])
