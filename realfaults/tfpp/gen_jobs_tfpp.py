#!/usr/bin/env python3
"""Tier-1 real-fault study: job files for the carla_garage TransFuser++
(leaderboard_1) agent run in the Proxima in-process CARLA host.

Reuses the 30-scenario suite of the SA-TRP mutation campaign
(~/satrp_mutation/ads/store/transfuser/suite.json) and its seed formula
(GLOBAL_SEED 20260806 + sid*1000 + run_idx), so every (sid, run_idx) cell is
the same choreographed scenario instance the TransFuser-2022 base/mutant
campaigns saw.

Outputs (all under ~/satrp_real/tfpp/):
  jobs_base.jsonl      base version (HEAD), run_idx 0..39  -> 1,200 jobs
  jobs_versions.jsonl  2 reverted-fix versions x 30 x run_idx 0..23 -> 1,440 jobs
  jobs_smoke.jsonl     3 jobs: one CutIn scenario, run_idx 0, one per version
Job schema = ~/satrp_mutation/ads/store/transfuser/jobs_matrix.jsonl.
"""
import json
import os
import sys

HOME = os.path.expanduser('~')
ROOT = f'{HOME}/satrp_real/tfpp'
SUITE = f'{HOME}/satrp_mutation/ads/store/transfuser/suite.json'
VERSIONS = f'{ROOT}/versions.json'
GLOBAL_SEED = 20260806       # TF stack, same as gen_jobs.NOMINAL['transfuser']
DURATION = 40
N_BASE = 40                  # run_idx 0..39
N_VER = 24                   # run_idx 0..23
VIDS = ('v_lidar_stale', 'v_speed_offset')
SMOKE_SID = 81               # ProxCutIn, nominal_triggers 5/5 (TF-2022): the
                             # cut-in that forces a reaction


def _versions():
    v = {d['vid']: d for d in json.load(open(VERSIONS))}
    return v


def make_job(d, run_idx, tag, vid, vinfo, trace_dir):
    jid = f"{tag}_s{d['sid']}_r{run_idx}"
    return dict(
        job_id=jid, scenario_cls=d['scenario_cls'], params=d['params'],
        sid=d['sid'], run_idx=run_idx,
        seed=GLOBAL_SEED + d['sid'] * 1000 + run_idx,
        duration=DURATION, perturb=None,
        trace_out=f"{ROOT}/{trace_dir}/{jid}.npz",
        mutant=dict(mid=vid, site=vinfo['site'], md5=vinfo['md5']),
        team_code_dir=f"{ROOT}/versions/{vid}/team_code")


def main():
    suite = json.load(open(SUITE))['suite']
    assert len(suite) == 30, len(suite)
    vers = _versions()
    for vid in ('base',) + VIDS:
        assert vid in vers, vid
        assert os.path.isfile(f'{ROOT}/versions/{vid}/team_code/sensor_agent.py'), vid

    n = 0
    with open(f'{ROOT}/jobs_base.jsonl', 'w') as f:
        for d in suite:                      # scenario-major, as the campaigns
            for r in range(N_BASE):
                f.write(json.dumps(make_job(d, r, 'base', 'base', vers['base'],
                                            'traces_base')) + '\n'); n += 1
    print('base jobs', n, '->', f'{ROOT}/jobs_base.jsonl')

    n = 0
    with open(f'{ROOT}/jobs_versions.jsonl', 'w') as f:
        for d in suite:
            for vid in VIDS:
                for r in range(N_VER):
                    f.write(json.dumps(make_job(d, r, f'rv_{vid}', vid, vers[vid],
                                                f'traces_{vid}')) + '\n'); n += 1
    print('version jobs', n, '->', f'{ROOT}/jobs_versions.jsonl')

    d = [x for x in suite if x['sid'] == SMOKE_SID][0]
    assert d['scenario_cls'] == 'ProxCutIn'
    n = 0
    with open(f'{ROOT}/jobs_smoke.jsonl', 'w') as f:
        for vid in ('base',) + VIDS:
            f.write(json.dumps(make_job(d, 0, f'smoke_{vid}', vid, vers[vid],
                                        'traces_smoke')) + '\n'); n += 1
    print('smoke jobs', n, '->', f'{ROOT}/jobs_smoke.jsonl')


if __name__ == '__main__':
    main()
