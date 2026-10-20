#!/usr/bin/env python3
"""Tier-1 real-fault study, leaderboard block (TF++): one job = one leaderboard
route evaluated once. NO hand-built routes: uses carla_garage's shipped
per-scenario-class Town01 route XML + scenario JSON (leaderboard 1.0 format,
leaderboard/data/training/{routes,scenarios}/s<N>/Town01_Scenario<N>.{xml,json}):
  s1 control loss | s3 pedestrian crossing | s4 cyclist/vehicle crossing (straight road)
  s7 red-light crossing traffic | s8 unprotected left | s9 right turn w/ crossing (junctions)

Outputs (under ~/satrp_real/tfpp/):
  jobs_lb_smoke_video.jsonl  first route of EVERY class x 3 versions, run_idx 0 (video smoke)
  jobs_lb_base.jsonl         base, ROUTES_PER_CLASS routes per class, run_idx 0..N_BASE-1
  jobs_lb_versions.jsonl     2 versions x same routes x run_idx 0..N_VER-1
Seed = 20260806 + 1000*(1000 + 100*class_idx + route_pos) + run_idx  (disjoint
from the straight block: 20260806 + sid*1000 + run_idx, sid <= 149).
Job schema = lb_worker.py's.  Env: ROUTES_PER_CLASS (default 2).
"""
import json
import os
import sys
import xml.etree.ElementTree as ET

HOME = os.path.expanduser('~')
ROOT = f'{HOME}/satrp_real/tfpp'
DATA = f'{ROOT}/carla_garage/leaderboard/data/training'
CKPT = f'{ROOT}/ckpt/pretrained_models/longest6/tfpp_all_0'
VERSIONS = f'{ROOT}/versions.json'
GLOBAL_SEED = 20260806
N_BASE = 40
N_VER = 24
VIDS = ('v_lidar_stale', 'v_speed_offset')
BENCHMARK = 'longest6'
CLASSES = ('s1', 's3', 's4', 's7', 's8', 's9')
TOWN = 'Town01'
ROUTES_PER_CLASS = int(os.environ.get('ROUTES_PER_CLASS', 2))


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


def make_job(rt, run_idx, tag, vid, vinfo, res_dir):
    jid = f"{tag}_{rt['cls']}_rt{rt['route_id']}_r{run_idx}"
    return dict(
        job_id=jid, route_id=rt['route_id'], route_index=rt['route_pos'], scenario_class=rt['cls'],
        town=rt['town'], routes_xml=rt['routes_xml'], scenarios_json=rt['scenarios_json'],
        seed=GLOBAL_SEED + 1000 * (1000 + 100 * rt['class_idx'] + rt['route_pos']) + run_idx,
        team_code_dir=f"{ROOT}/versions/{vid}/team_code", ckpt_dir=CKPT,
        results_out=f"{ROOT}/{res_dir}/{jid}.json", run_idx=run_idx,
        mutant=dict(mid=vid, site=vinfo['site'], md5=vinfo['md5']),
        benchmark=BENCHMARK)


def main():
    vers = {d['vid']: d for d in json.load(open(VERSIONS))}
    per_class = {c: routes(c) for c in CLASSES}
    for c, r in per_class.items():
        print(c, len(r), 'routes, ids', [x['route_id'] for x in r][:8], '...')
    n = 0
    with open(f'{ROOT}/jobs_lb_smoke_video.jsonl', 'w') as f:
        for vid in ('base',) + VIDS:
            for c in CLASSES:
                f.write(json.dumps(make_job(per_class[c][0], 0, f'lbvsmoke_{vid}', vid, vers[vid], 'lb_results_smoke_video')) + '\n'); n += 1
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
            for vid in VIDS:
                for r in range(N_VER):
                    f.write(json.dumps(make_job(rt, r, f'lb_{vid}', vid, vers[vid], f'lb_results_{vid}')) + '\n'); n += 1
    print('lb version jobs', n)


if __name__ == '__main__':
    main()
