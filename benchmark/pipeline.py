#!/usr/bin/env python3
"""SA-TRP mutation pipeline: candidate sampling, mutant materialisation, screen/matrix jobs.

  sample <stack> [--covered] [K=100] [SEED]  -> store/<stack>/candidates.json
  materialize <stack>                        -> store/<stack>/mutants/<mid>/... + candidates.json updated
  screen-jobs <stack>                        -> store/<stack>/jobs_screen.jsonl (K mutants x 6 scenarios + 6 BASE twins)
  matrix-jobs <stack> <selected.json> <N_SEEDS> -> store/<stack>/jobs_matrix.jsonl
"""
import json, os, sys, random, collections, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutgen2
from gen_jobs import STORE, NOMINAL, make_job

HOME = os.path.expanduser('~')
TARGETS = {
  'openpilot': dict(repo=f'{HOME}/openpilot/openpilot', files=[
      'selfdrive/controls/controlsd.py', 'selfdrive/controls/radard.py',
      'selfdrive/controls/lib/longitudinal_planner.py', 'selfdrive/controls/lib/longcontrol.py',
      'selfdrive/controls/lib/latcontrol_torque.py', 'selfdrive/controls/lib/drive_helpers.py',
      'selfdrive/modeld/parse_model_outputs.py', 'selfdrive/modeld/fill_model_msg.py',
      'selfdrive/modeld/constants.py'],
      strata={'selfdrive/controls/lib/longitudinal_planner.py': 'planning', 'selfdrive/controls/lib/drive_helpers.py': 'planning',
              'selfdrive/controls/lib/longcontrol.py': 'control', 'selfdrive/controls/lib/latcontrol_torque.py': 'control',
              'selfdrive/controls/controlsd.py': 'control', 'selfdrive/controls/radard.py': 'perception',
              'selfdrive/modeld/parse_model_outputs.py': 'perception', 'selfdrive/modeld/fill_model_msg.py': 'perception',
              'selfdrive/modeld/constants.py': 'perception'},
      # radard: only the vision-lead branch is live in the radarless sim car
      line_filter={'selfdrive/controls/radard.py': lambda ln: ln >= 141}),
  'transfuser': dict(repo=f'{HOME}/transfuser_repo', files=[
      'team_code_transfuser/model.py', 'team_code_transfuser/submission_agent.py', 'team_code_transfuser/config.py'],
      strata={'team_code_transfuser/model.py': 'control', 'team_code_transfuser/submission_agent.py': 'agent',
              'team_code_transfuser/config.py': 'config'},
      line_filter={}),
}
STRATUM_QUOTA = {'openpilot': {'planning': 30, 'control': 30, 'perception': 40},
                 'transfuser': {'control': 40, 'agent': 45, 'config': 15}}
OP_CAP = 0.4        # literal-based ops (CRP+CSC+IDX) share cap
PER_OP_CAP = 18     # per operator per stack in the candidate set
SCREEN_RUN_IDX = 40  # seed slot outside the BASE range


def _mid(site_id):
    return 'm' + hashlib.md5(site_id.encode()).hexdigest()[:8]


def cmd_sample(stack, covered=True, K=100, seed=20260929):
    t = TARGETS[stack]
    cov = None
    if covered:
        cov = json.load(open(f'{HOME}/satrp_mutation/coverage/{stack}/covered_lines.json'))
    sites = []
    for rel in t['files']:
        c = set(cov.get(rel, [])) if cov is not None else None
        if cov is not None and not c:
            print('  no coverage for', rel); continue
        for s in mutgen2.file_sites(t['repo'], rel, c):
            lf = t['line_filter'].get(rel)
            if lf and not lf(s['line']):
                continue
            s['stratum'] = t['strata'][rel]
            sites.append(s)
    by = collections.Counter((s['stratum'], s['op']) for s in sites)
    print(stack, 'eligible sites', len(sites), '(covered filter', covered, ')')
    for k, v in sorted(by.items()): print('   ', k, v)
    rng = random.Random(seed)
    rng.shuffle(sites)
    # stratified greedy fill with per-op and literal caps, one site per (file,line,op) to avoid near-duplicates
    picked, per_op, per_str, seen = [], collections.Counter(), collections.Counter(), set()
    lit_cap = int(K * OP_CAP)
    def ok(s):
        key = (s['file'], s['line'], s['op'])
        if key in seen: return False
        if per_str[s['stratum']] >= STRATUM_QUOTA[stack][s['stratum']]: return False
        if per_op[s['op']] >= PER_OP_CAP: return False
        if s['op'] in ('CRP', 'CSC', 'IDX') and sum(per_op[o] for o in ('CRP', 'CSC', 'IDX')) >= lit_cap: return False
        return True
    for s in sites:
        if len(picked) >= K: break
        if ok(s):
            picked.append(s); seen.add((s['file'], s['line'], s['op'])); per_op[s['op']] += 1; per_str[s['stratum']] += 1
    for s in picked:
        s['mid'] = _mid(s['id'])
    out = dict(stack=stack, seed=seed, K=K, covered=covered, per_op=dict(per_op), per_stratum=dict(per_str), candidates=picked)
    json.dump(out, open(f'{STORE}/{stack}/candidates.json', 'w'), indent=1)
    print('picked', len(picked), dict(per_op), dict(per_str))


def cmd_materialize(stack):
    t = TARGETS[stack]
    c = json.load(open(f'{STORE}/{stack}/candidates.json'))
    for s in c['candidates']:
        mdir = f"{STORE}/{stack}/mutants/{s['mid']}"
        os.makedirs(mdir, exist_ok=True)
        if stack == 'openpilot':
            dst, md5 = mutgen2.apply_site(t['repo'], mdir, s)
            # daemons are launched as 'selfdrive.controls.controlsd' (no prefix) while
            # their imports use 'openpilot.selfdrive....' -> map BOTH module names
            mod = s['file'][:-3].replace('/', '.')
            s['mutant'] = dict(mid=s['mid'], site=s['id'],
                               file_map=f'openpilot.{mod}={dst};{mod}={dst}', md5=md5)
        else:
            dst, md5 = mutgen2.apply_site(t['repo'], mdir, s, tree=True, pkg_rel='team_code_transfuser')
            s['mutant'] = dict(mid=s['mid'], site=s['id'], team_code_dir=f'{mdir}/team_code_transfuser', md5=md5)
    json.dump(c, open(f'{STORE}/{stack}/candidates.json', 'w'), indent=1)
    print('materialized', len(c['candidates']), 'mutants under', f'{STORE}/{stack}/mutants')


def _job_mut(stack, s):
    if stack == 'openpilot':
        return dict(mutant=dict(mid=s['mid'], site=s['id'], file_map=s['mutant']['file_map'], md5=s['mutant']['md5']))
    return dict(mutant=dict(mid=s['mid'], site=s['id'], md5=s['mutant']['md5']), team_code_dir=s['mutant']['team_code_dir'])


def screen_scenarios(stack):
    """6 screen scenarios: per template the suite member with the median nominal
    trigger count (both directions visible), plus the hardest OncomingDrift/CutIn."""
    suite = json.load(open(f'{STORE}/{stack}/suite.json'))['suite']
    out = []
    for cls in ('ProxLeadDecel', 'ProxLeadStopped', 'ProxCutIn', 'ProxOncomingDrift', 'ProxCrossingTraffic'):
        m = sorted([d for d in suite if d['scenario_cls'] == cls], key=lambda d: d['nominal_triggers'])
        out.append(m[len(m) // 2])
    extra = sorted([d for d in suite if d['scenario_cls'] in ('ProxOncomingDrift', 'ProxCutIn') and d not in out],
                   key=lambda d: -d['nominal_triggers'])[0]
    out.append(extra)
    return out


def cmd_screen_jobs(stack):
    c = json.load(open(f'{STORE}/{stack}/candidates.json'))
    scen = screen_scenarios(stack)
    out = f'{STORE}/{stack}/jobs_screen.jsonl'; n = 0
    with open(out, 'w') as f:
        for tag in ('screen', 'screentwin'):  # two BASE runs at the SAME seed: divergence + execution-noise floor
            for d in scen:
                f.write(json.dumps(make_job(stack, d, SCREEN_RUN_IDX, tag)) + '\n'); n += 1
        for s in c['candidates']:
            for d in scen:
                j = make_job(stack, d, SCREEN_RUN_IDX, f"screen_{s['mid']}", _job_mut(stack, s))
                f.write(json.dumps(j) + '\n'); n += 1
    print(stack, 'screen jobs', n, '->', out, '| scenarios', [(d['sid'], d['scenario_cls'], d['nominal_triggers']) for d in scen])


def cmd_matrix_jobs(stack, selected_json, n_seeds):
    c = {s['mid']: s for s in json.load(open(f'{STORE}/{stack}/candidates.json'))['candidates']}
    sel = json.load(open(selected_json))['selected']
    suite = json.load(open(f'{STORE}/{stack}/suite.json'))['suite']
    out = f'{STORE}/{stack}/jobs_matrix.jsonl'; n = 0
    with open(out, 'w') as f:
        for d in suite:               # scenario-major: a half-drained campaign covers whole scenarios
            for mid in sel:
                for r in range(int(n_seeds)):
                    f.write(json.dumps(make_job(stack, d, r, f'mx_{mid}', _job_mut(stack, c[mid]))) + '\n'); n += 1
    print(stack, 'matrix jobs', n, '->', out)


if __name__ == '__main__':
    a = sys.argv[1:]
    cmd, stack = a[0], a[1]
    if cmd == 'sample':
        cov = '--covered' in a
        rest = [x for x in a[2:] if x != '--covered']
        cmd_sample(stack, cov, int(rest[0]) if rest else 100, int(rest[1]) if len(rest) > 1 else 20260929)
    elif cmd == 'materialize': cmd_materialize(stack)
    elif cmd == 'screen-jobs': cmd_screen_jobs(stack)
    elif cmd == 'matrix-jobs': cmd_matrix_jobs(stack, a[2], a[3])
