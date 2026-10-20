#!/usr/bin/env python3
"""Classify screened mutants: stillborn / mass-fail / partial / silent, with trace
divergence vs the same-seed BASE run and the BASE-vs-BASE twin noise floor.
usage: analyze_screen.py <stack>  -> store/<stack>/screen_classes.json + table"""
import json, os, sys, glob, collections
import numpy as np
HOME = os.path.expanduser('~')
STORE = f'{HOME}/satrp_mutation/ads/store'
stack = sys.argv[1]
FAIL_OP = {'out_of_lane', 'collision'}


def load_results(pattern):
    rows = {}
    for f in glob.glob(pattern):
        for l in open(f):
            if l.strip():
                r = json.loads(l); rows[r['job_id']] = r
    return rows


def trace_xy(path):
    p = path if os.path.exists(path) else path + '.npz'
    if not os.path.exists(p):
        return None, None
    z = np.load(p, allow_pickle=True); cols = [str(c) for c in z['columns']]; d = z['data']
    if getattr(d, 'ndim', 0) != 2 or len(d) == 0 or 'ego_x' not in cols:
        return None, None            # empty / malformed trace (errored run)
    return d[:, cols.index('ego_x')], d[:, cols.index('ego_y')]


def divergence(a, b):
    """RMS ego-position gap over the common prefix (m)."""
    ax, ay = a; bx, by = b
    if ax is None or bx is None:
        return float('nan')
    n = min(len(ax), len(bx))
    if n < 5:
        return float('nan')
    return float(np.sqrt(np.mean((ax[:n] - bx[:n]) ** 2 + (ay[:n] - by[:n]) ** 2)))


def trigger(stack, r):
    if r is None:
        return None
    c = bool(r.get('contact'))
    if stack == 'openpilot':
        return c or r.get('outcome') in FAIL_OP
    return c


def outcome_of(stack, r, trace_path):
    """(valid, trigger) — valid=False for stillborn evidence"""
    if r is None:
        return False, None
    oc = str(r.get('outcome', ''))
    if stack == 'openpilot':
        if oc.startswith('error') or oc in ('no_engage', 'bridge_start_timeout', 'run_timeout') or not r.get('engaged', True):
            return False, None
    else:
        if oc.startswith('error') or oc in ('stall',) or not r.get('trace_exists', True):
            return False, None
        if r.get('contact') is None:  # TF results carry no contact: read the trace
            p = trace_path if os.path.exists(trace_path) else trace_path + '.npz'
            if not os.path.exists(p):
                return False, None
            z = np.load(p, allow_pickle=True); cols = [str(c) for c in z['columns']]; d = z['data']
            if getattr(d, 'ndim', 0) != 2 or len(d) == 0:
                return False, None
            r['contact'] = bool(np.nanmax(d[:, cols.index('crash')]) > 0.5)
    return True, trigger(stack, r)


def main():
    c = json.load(open(f'{STORE}/{stack}/candidates.json'))
    jobs = [json.loads(l) for l in open(f'{STORE}/{stack}/jobs_screen.jsonl') if l.strip()]
    if stack == 'openpilot':
        res = load_results(f'{STORE}/{stack}/results/jobs_screen*_task*.results.jsonl')
    else:
        res = load_results(f'{STORE}/{stack}/jobs_screen*_task*.results.jsonl')
    byjob = {j['job_id']: j for j in jobs}
    scen_sids = sorted({j['sid'] for j in jobs})
    base = {j['sid']: j for j in jobs if j['job_id'].startswith('screen_s')}
    twin = {j['sid']: j for j in jobs if j['job_id'].startswith('screentwin_s')}
    # noise floor
    floor = {}
    for sid in scen_sids:
        floor[sid] = divergence(trace_xy(base[sid]['trace_out']), trace_xy(twin[sid]['trace_out']))
    base_trig = {sid: outcome_of(stack, res.get(base[sid]['job_id']), base[sid]['trace_out'])[1] for sid in scen_sids}
    print('BASE twin noise floor RMS (m):', {sid: round(v, 2) for sid, v in floor.items()})
    print('BASE screen triggers:', base_trig)
    out = []
    for s in c['candidates']:
        mid = s['mid']; rows = []
        for sid in scen_sids:
            jid = f"screen_{mid}_s{sid}_r40"
            j = byjob.get(jid); r = res.get(jid)
            valid, trig = outcome_of(stack, r, j['trace_out'] if j else '')
            div = divergence(trace_xy(j['trace_out']), trace_xy(base[sid]['trace_out'])) if j else float('nan')
            rows.append(dict(sid=sid, valid=valid, trig=trig, div=div, base_trig=base_trig[sid],
                             above_floor=(div == div and floor[sid] == floor[sid] and div > 3 * max(floor[sid], 0.3))))
        n_run = sum(1 for x in rows if x['valid'])
        n_done = sum(1 for x in rows if x['sid'] in scen_sids and (x['sid'] and (f"screen_{mid}_s{x['sid']}_r40" in res)))
        if n_done == 0:
            cls = 'pending'
        elif n_run <= 2:
            cls = 'stillborn'
        else:
            t = sum(1 for x in rows if x['valid'] and x['trig'])
            bt = sum(1 for x in rows if x['valid'] and x['base_trig'])
            dv = sum(1 for x in rows if x['valid'] and x['above_floor'])
            if t >= n_run - 1 and t >= bt + 3:
                cls = 'mass-fail'
            elif t != bt or dv >= 2:
                cls = 'partial'
            else:
                cls = 'silent'
        out.append(dict(mid=mid, site=s['id'], op=s['op'], stratum=s['stratum'], cls=cls, n_done=n_done, n_valid=n_run,
                        triggers=sum(1 for x in rows if x['valid'] and x['trig']),
                        base_triggers=sum(1 for x in rows if x['valid'] and x['base_trig']),
                        divergent=sum(1 for x in rows if x['valid'] and x['above_floor']),
                        rows=rows))
    json.dump(dict(stack=stack, floor=floor, base_trig=base_trig, mutants=out), open(f'{STORE}/{stack}/screen_classes.json', 'w'), indent=1)
    cnt = collections.Counter(m['cls'] for m in out)
    print(stack, 'screen classes:', dict(cnt))
    byop = collections.defaultdict(collections.Counter)
    for m in out: byop[m['op']][m['cls']] += 1
    for op, cc in sorted(byop.items()): print('  ', op, dict(cc))
    for m in sorted(out, key=lambda m: (-m['triggers'], m['mid']))[:15]:
        print(f"  {m['mid']} {m['cls']:9s} trig {m['triggers']}/{m['n_valid']} (base {m['base_triggers']}) div {m['divergent']}  {m['site']}")


if __name__ == '__main__':
    main()
