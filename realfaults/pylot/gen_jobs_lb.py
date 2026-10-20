#!/usr/bin/env python3
"""Tier-2 real-fault study, leaderboard block (Pylot): one job = one leaderboard
route evaluated once by the Pylot image's leaderboard 1.0 evaluator.  NO
hand-built routes: uses carla_garage's shipped per-scenario-class Town01 route
XML + scenario JSON (leaderboard 1.0 format, read unchanged by the image's
leaderboard):
  s1 control loss | s3 pedestrian crossing | s4 cyclist/vehicle crossing (straight road)
  s7 red-light crossing traffic | s8 unprotected left | s9 right turn w/ crossing (junctions)

Outputs (under ~/satrp_real/pylot/):
  jobs_lb_smoke_video.jsonl  first route of EVERY class x ALL 9 versions (base +
                             versions.json recommended_order), run_idx 0 -> 54 jobs
  jobs_lb_base.jsonl         base x ROUTES_PER_CLASS routes per class x N_BASE runs
  jobs_lb_versions.jsonl     8 versions x same routes x N_VER runs
Seed = GLOBAL_SEED + 1000*(1000 + 100*class_idx + route_pos) + run_idx + 500000
(same formula as the TF++ generator plus a +500000 class-offset so Pylot seeds
differ from TF++'s).  Job schema = lb_worker.py's:
  pylot_dir = versions/<vid>/pylot (bind-mounted over /workspace/team_code/pylot)
  conf      = versions/<vid>/pylot/simulation/challenge/challenge.conf (default
              perception path; v_speed7 differs ONLY there)
  proof_files = versions.json md5_version for the version's changed files
              (base: md5_base of every file any version changes, asserted
              against the base tree)
  difftrace_required = status == "ready" (the worker additionally requires the
              deployed tree to be instrumented before enforcing it)
Env: ROUTES_PER_CLASS (default 2).
"""
import hashlib
import json
import os
import xml.etree.ElementTree as ET

HOME = os.path.expanduser('~')
ROOT = f'{HOME}/satrp_real/pylot'
DATA = f'{HOME}/satrp_real/tfpp/carla_garage/leaderboard/data/training'
VERSIONS = f'{ROOT}/versions/versions.json'
# DIFFTRACE_TREES=1 (default): deploy the instrumented copies versions_dt/<vid> (difftrace patches
# applied; base carries all 8 traces) so every run proves the mechanism fired; 0 -> pristine versions/.
TREES_DIR = 'versions_dt' if os.environ.get('DIFFTRACE_TREES', '1') != '0' else 'versions'
GLOBAL_SEED = 20260806
SEED_OFFSET = 500000
N_BASE = 40
N_VER = 24
CLASSES = ('s1', 's3', 's4', 's7', 's8', 's9')
TOWN = 'Town01'
ROUTES_PER_CLASS = int(os.environ.get('ROUTES_PER_CLASS', 2))


def md5_file(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


def class_files(cls):
    n = cls[1:]
    return (f'{DATA}/routes/{cls}/{TOWN}_Scenario{n}.xml',
            f'{DATA}/scenarios/{cls}/{TOWN}_Scenario{n}.json')


def routes(cls):
    xml, js = class_files(cls)
    root = ET.parse(xml).getroot()
    return [dict(cls=cls, class_idx=CLASSES.index(cls), route_pos=i, route_id=r.attrib['id'],
                 town=r.attrib.get('town', TOWN), routes_xml=xml, scenarios_json=js)
            for i, r in enumerate(root.findall('route'))]


def load_versions():
    d = json.load(open(VERSIONS))
    vers = {v['vid']: v for v in d['versions']}
    order = list(d['recommended_order'])
    assert set(order) == set(vers), (order, list(vers))
    # base: md5_base of every changed file, asserted against the base tree
    base_files = {}
    for v in vers.values():
        for f, m in v['md5_base'].items():
            base_files.setdefault(f, m)
            assert base_files[f] == m, (v['vid'], f)
    for f, m in base_files.items():
        got = md5_file(f'{ROOT}/versions/base/{f}')
        assert got == m, f'base {f}: tree md5 {got} != versions.json md5_base {m}'
    vers['base'] = dict(vid='base', status='base', files=sorted(base_files),
                        md5_version=base_files)
    for vid, v in vers.items():                      # version trees match versions.json
        for f, m in v['md5_version'].items():
            got = md5_file(f'{ROOT}/versions/{vid}/{f}')
            assert got == m, f'{vid} {f}: tree md5 {got} != versions.json md5_version {m}'
    return vers, order


def make_job(rt, run_idx, tag, vid, vinfo, res_dir):
    jid = f"{tag}_{rt['cls']}_rt{rt['route_id']}_r{run_idx}"
    tree = f'{ROOT}/{TREES_DIR}/{vid}'
    return dict(
        job_id=jid, route_id=rt['route_id'], route_index=rt['route_pos'], scenario_class=rt['cls'],
        town=rt['town'], routes_xml=rt['routes_xml'], scenarios_json=rt['scenarios_json'],
        seed=GLOBAL_SEED + 1000 * (1000 + 100 * rt['class_idx'] + rt['route_pos']) + run_idx + SEED_OFFSET,
        run_idx=run_idx, vid=vid, status=vinfo['status'],
        pylot_dir=f'{tree}/pylot', conf=f'{tree}/pylot/simulation/challenge/challenge.conf',
        proof_files=dict(vinfo['md5_version']),
        difftrace_required=(vinfo['status'] == 'ready'),
        results_out=f'{ROOT}/{res_dir}/{jid}.json')


def main():
    vers, order = load_versions()
    per_class = {c: routes(c) for c in CLASSES}
    for c, r in per_class.items():
        print(c, len(r), 'routes, ids', [x['route_id'] for x in r][:8], '...')
    n = 0
    with open(f'{ROOT}/jobs_lb_smoke_video.jsonl', 'w') as f:
        for vid in ['base'] + order:
            for c in CLASSES:
                f.write(json.dumps(make_job(per_class[c][0], 0, f'lbvsmoke_{vid}', vid, vers[vid],
                                            'lb_results_smoke_video')) + '\n'); n += 1
    print('lb smoke-video jobs', n)
    sel = [rt for c in CLASSES for rt in per_class[c][:ROUTES_PER_CLASS]]
    n = 0
    with open(f'{ROOT}/jobs_lb_base.jsonl', 'w') as f:
        for rt in sel:
            for r in range(N_BASE):
                f.write(json.dumps(make_job(rt, r, 'lbbase', 'base', vers['base'], 'lb_results_base')) + '\n'); n += 1
    print('lb base jobs', n, f'({len(sel)} routes x {N_BASE})')
    n = 0
    with open(f'{ROOT}/jobs_lb_versions.jsonl', 'w') as f:
        for rt in sel:
            for vid in order:
                for r in range(N_VER):
                    f.write(json.dumps(make_job(rt, r, f'lb_{vid}', vid, vers[vid], f'lb_results_{vid}')) + '\n'); n += 1
    print('lb version jobs', n, f'({len(sel)} routes x {len(order)} versions x {N_VER})')


if __name__ == '__main__':
    main()
