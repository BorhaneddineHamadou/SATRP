#!/usr/bin/env python3
"""SA-TRP mutation campaign job generation.

  suite   -> store/<stack>/suite.json  (30 scenarios, stratified on nominal k=5 outcome)
  base    -> store/<stack>/jobs_base.jsonl (run_idx 5..N_BASE-1; r0-r4 reused from nominal)
  screen  -> jobs for the 1-run mutant screen (later)
  matrix  -> jobs for the full matrix (later)
Seed scheme = the Proxima nominal campaigns': GLOBAL_SEED + sid*1000 + run_idx.
"""
import json, os, random, sys, collections

HOME = os.path.expanduser('~')
STORE = f'{HOME}/satrp_mutation/ads/store'
NOMINAL = {
  'openpilot': dict(jobs=f'{HOME}/proxima/results/phase1_seeing/campaign_nominal_jobs.jsonl',
                    results=f'{HOME}/proxima/results/phase1_seeing/campaign_nominal_jobs_task*.results.jsonl',
                    global_seed=20260722, duration=130),
  'transfuser': dict(jobs=f'{HOME}/proxima/results/transfuser_campaign/campaign_nominal_jobs.jsonl',
                     results=None, global_seed=20260806, duration=40),
}
# per-template quota and target mix over nominal triggers/5 bins: (zero, low 1-2, high 3-5)
QUOTA = {
  'openpilot':  {'ProxLeadDecel': 6, 'ProxLeadStopped': 6, 'ProxCutIn': 6, 'ProxOncomingDrift': 6, 'ProxCrossingTraffic': 6},
  'transfuser': {'ProxLeadDecel': 4, 'ProxLeadStopped': 4, 'ProxCutIn': 8, 'ProxOncomingDrift': 8, 'ProxCrossingTraffic': 6},
}
MIX = (0.3, 0.4, 0.3)
N_BASE = 40


def load_nominal(stack):
    cfg = NOMINAL[stack]
    jobs = [json.loads(l) for l in open(cfg['jobs']) if l.strip()]
    bysid = {}
    for j in jobs:
        bysid.setdefault(j['sid'], j)
    trig = collections.defaultdict(list)
    if stack == 'openpilot':
        import glob
        rows = {}
        for f in glob.glob(cfg['results']):
            for l in open(f):
                if l.strip():
                    r = json.loads(l); rows[r['job_id']] = r
        for jid, r in rows.items():
            sid = int(jid.split('_')[0][1:])
            trig[sid].append(bool(r.get('contact')) or r.get('outcome') in ('out_of_lane', 'collision'))
    else:
        nc = json.load(open(f'{HOME}/satrp_mutation/coverage/transfuser/nominal_contacts.json'))
        for cls, d in nc.items():
            for sid, k in d.items():
                trig[int(sid)] = [True] * k + [False] * (5 - k)
    return bysid, trig


def cmd_suite(stack, seed=20260929):
    bysid, trig = load_nominal(stack)
    rng = random.Random(seed)
    suite = []
    for cls, q in QUOTA[stack].items():
        sids = [s for s, j in bysid.items() if j['scenario_cls'] == cls]
        bins = {'zero': [], 'low': [], 'high': []}
        for s in sids:
            k = sum(trig[s])
            bins['zero' if k == 0 else 'low' if k <= 2 else 'high'].append(s)
        want = [round(q * m) for m in MIX]
        want[1] += q - sum(want)
        picked = []
        for b, w in zip(('zero', 'low', 'high'), want):
            pool = sorted(bins[b]); rng.shuffle(pool)
            picked += pool[:w]
        # fill shortfall from the other bins
        if len(picked) < q:
            rest = [s for s in sids if s not in picked]; rng.shuffle(rest)
            picked += rest[:q - len(picked)]
        for s in picked:
            suite.append(dict(sid=s, scenario_cls=cls, params=bysid[s]['params'],
                              nominal_triggers=sum(trig[s]), nominal_runs=len(trig[s])))
    suite.sort(key=lambda d: d['sid'])
    os.makedirs(f'{STORE}/{stack}', exist_ok=True)
    json.dump(dict(stack=stack, seed=seed, quota=QUOTA[stack], mix=MIX, suite=suite),
              open(f'{STORE}/{stack}/suite.json', 'w'), indent=1)
    c = collections.Counter((d['scenario_cls'], d['nominal_triggers']) for d in suite)
    print(stack, 'suite', len(suite), 'scenarios;', 'mean nominal trigger rate',
          round(sum(d['nominal_triggers'] for d in suite) / (5 * len(suite)), 3))
    for cls in QUOTA[stack]:
        print('  ', cls, {k: v for (c2, k), v in sorted(c.items()) if c2 == cls})


def make_job(stack, d, run_idx, tag, mutant=None):
    cfg = NOMINAL[stack]
    jid = f"{tag}_s{d['sid']}_r{run_idx}"
    job = dict(job_id=jid, scenario_cls=d['scenario_cls'], params=d['params'], sid=d['sid'],
               run_idx=run_idx, seed=cfg['global_seed'] + d['sid'] * 1000 + run_idx,
               duration=cfg['duration'], perturb=None,
               trace_out=f"{STORE}/{stack}/traces_{tag}/{jid}.npz")
    if mutant:
        job.update(mutant)
    return job


def cmd_base(stack):
    suite = json.load(open(f'{STORE}/{stack}/suite.json'))['suite']
    out = f'{STORE}/{stack}/jobs_base.jsonl'
    n = 0
    with open(out, 'w') as f:
        for d in suite:                       # scenario-major, like the campaigns
            for r in range(5, N_BASE):        # r0-r4 exist in the nominal store
                f.write(json.dumps(make_job(stack, d, r, 'base')) + '\n'); n += 1
    print(stack, 'base jobs', n, '->', out)


if __name__ == '__main__':
    cmd, stack = sys.argv[1], sys.argv[2]
    {'suite': cmd_suite, 'base': cmd_base}[cmd](stack)
