#!/usr/bin/env python3
"""
adapter.py -- build the evaluation instances (data/derived/<instance>/runs.jsonl) from the
raw benchmark record (the Zenodo archive, unpacked at $SATRP_RAW, default <repo>/raw).

One record per valid run, in the schema every evaluation script consumes:
  {commit, scenario, seed, engaged, outcome, min_ttc, fault_module, intended_scenarios,
   is_baseline, system, platform}
  commit   = "BASE" or "MUT:<mutant id>"      scenario = "<template>#<sid>"
  outcome  = "collision" if the run TRIGGERED (openpilot: contact or out_of_lane/collision
             outcome; TransFuser: contact read from the trace), else "completed".

Instances built here:
  mutation_openpilot   openpilot/MetaDrive, clean rerun 2026-10-16..20 (per-run isolated
                       params): raw/openpilot/jobs_clean.jsonl = BASE r0-39 (30 scen x 40) +
                       28 mutants x 30 scen x 24 draws, results last-write-wins per job id.
  mutation_transfuser  TransFuser/CARLA: BASE = 5 nominal runs per scenario from the Proxima
                       nominal campaign (raw/transfuser/nominal) + base r5-39, matrix =
                       jobs_matrix + jobs_matrix_ext (+ redo) results.
The real-fault instances (real_pylot, real_pylot_T2, real_tfpp, real_tfpp_straight) are
built by realfaults/analysis/real_numbers.py.

Dropped rows: outcome error*/no_engage/bridge_start_timeout/run_timeout/stall; openpilot
rows with engaged=False; TransFuser rows without a trace; openpilot mutant rows whose
import hook never fired (mutant_hook_hits==0).

usage: python3 adapter.py [openpilot|transfuser ...] [--overwrite]      (default: both; see _write)
"""
import os, sys, json, glob, collections
import numpy as np

ROOT = os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.environ.get("SATRP_RAW", os.path.join(ROOT, "raw"))
DERIVED = os.path.join(ROOT, "data", "derived")
FAIL_OP = {"out_of_lane", "collision"}


# ----------------------------------------------------------------------------- helpers
def _rec(commit, scenario, seed, trig, intended, is_base, system, platform,
         fault_module="none", min_ttc=None):
    return dict(commit=commit, scenario=scenario, seed=int(seed), engaged=True,
                outcome=("collision" if trig else "completed"), min_ttc=min_ttc,
                fault_module=fault_module, intended_scenarios=sorted(intended),
                is_baseline=is_base, system=system, platform=platform)


def _write(recs, out_path):
    """Write the instance in a canonical order (commit, scenario, seed).

    The shipped data/derived/<instance>/runs.jsonl files are the exact inputs the paper was
    computed from and are kept as they were written at campaign time (result files were then
    iterated in filesystem order). The evaluation harness consumes each cell's runs in file
    order as its common-random-number draw stream, so a differently ordered file is a
    different, equally valid realization of the budgeted draws (best F1-AUC moves by
    ~0.01-0.02). Therefore, when runs.jsonl already exists, the rebuild is written next to
    it as runs.rebuilt.jsonl and compared as a SET of records; pass --overwrite to replace."""
    recs = sorted(recs, key=lambda r: (r["commit"], r["scenario"], r["seed"]))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if os.path.exists(out_path) and "--overwrite" not in sys.argv:
        alt = out_path.replace("runs.jsonl", "runs.rebuilt.jsonl")
        with open(alt, "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
        shipped = sorted(open(out_path).read().splitlines())
        rebuilt = sorted(json.dumps(r) for r in recs)
        print(f"  shipped {out_path} exists -> wrote {alt}; same record set as shipped: {shipped == rebuilt} "
              f"({len(shipped)} vs {len(rebuilt)} records)")
        return alt
    with open(out_path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    return out_path


def _resolve_trace(path, store):
    """Job files record the campaign-time absolute trace path. Resolve it inside the
    unpacked raw store: <store>/<traces_dir>/<file>[.npz]."""
    for p in (path, path + ".npz"):
        if os.path.exists(p):
            return p
    rel = os.path.join(store, os.path.basename(os.path.dirname(path)), os.path.basename(path))
    for p in (rel, rel + ".npz"):
        if os.path.exists(p):
            return p
    return None


def _mut_rows(stack, results_glob, jobs_file, store):
    """Yield (job_id, job, result) for finished jobs; last write wins per job id across
    result files. Contact is read from the trace when the result row lacks it (TransFuser)."""
    jobs = {}
    jfs = [f for f in sorted(glob.glob(jobs_file)) if not f.endswith(".results.jsonl")] \
          if any(c in jobs_file for c in "*?[") else [jobs_file]
    for jf in jfs:
        for ln in open(jf):
            if ln.strip():
                j = json.loads(ln); jobs[j["job_id"]] = j
    res = {}
    for f in sorted(glob.glob(results_glob)):
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln); res[r["job_id"]] = r
    for jid, r in res.items():
        j = jobs.get(jid)
        if j is None:
            continue
        if r.get("contact") is None:
            p = _resolve_trace(j["trace_out"], store)
            if p is None:
                continue
            z = np.load(p, allow_pickle=True); cols = [str(c) for c in z["columns"]]
            r["contact"] = bool(np.nanmax(z["data"][:, cols.index("crash")]) > 0.5)
        yield jid, j, r


def _mut_valid_trig(stack, r):
    oc = str(r.get("outcome", ""))
    if oc.startswith("error") or oc in ("no_engage", "bridge_start_timeout", "run_timeout", "stall"):
        return False, 0
    if stack == "openpilot" and r.get("engaged") is False:
        return False, 0
    if stack == "transfuser" and r.get("trace_exists") is False:
        return False, 0
    trig = bool(r.get("contact"))
    if stack == "openpilot":
        trig = trig or oc in FAIL_OP
    return True, int(trig)


def _summary(tag, recs, nb, nm, cfgs, out_path):
    pool = collections.defaultdict(list)
    for r in recs:
        if r["is_baseline"]:
            pool[r["scenario"]].append(r["outcome"] == "collision")
    depth = sorted(len(v) for v in pool.values())
    qs = [float(np.mean(v)) for v in pool.values()]
    print(f"[{tag}] scenarios={len(pool)} BASE runs={nb} (min/med/max per scen "
          f"{depth[0]}/{depth[len(depth)//2]}/{depth[-1]}) mutant cfgs={len(cfgs)} mutant runs={nm} "
          f"records={len(recs)} -> {out_path}")
    print(f"  baseline q_s in [{min(qs):.2f},{max(qs):.2f}], mean {np.mean(qs):.3f}")


# ----------------------------------------------------------------------------- openpilot
def build_mutation_openpilot(out_path=None):
    """openpilot clean rerun: BASE and matrix come from ONE shuffled jobs file."""
    store = os.path.join(RAW, "openpilot")
    out_path = out_path or os.path.join(DERIVED, "mutation_openpilot", "runs.jsonl")
    recs, cfgs, nb, nm = [], set(), 0, 0
    depth_m, inv = collections.Counter(), collections.Counter()
    for jid, j, r in _mut_rows("openpilot", f"{store}/results/jobs_clean_task*.results.jsonl",
                               f"{store}/jobs_clean.jsonl", store):
        ok, t = _mut_valid_trig("openpilot", r)
        if not ok:
            inv[r.get("outcome")] += 1; continue
        key = f"{j['scenario_cls']}#{j['sid']}"
        if jid.startswith("base"):
            recs.append(_rec("BASE", key, j["seed"], t, set(), True, "openpilot", "MetaDrive")); nb += 1
        else:
            mid = j["mutant"]["mid"]
            if not r.get("mutant_hook_hits", 0):
                inv["hook0"] += 1; continue
            recs.append(_rec(f"MUT:{mid}", key, j["seed"], t, set(), False, "openpilot", "MetaDrive",
                             fault_module=j["mutant"]["site"].split(":")[0]))
            nm += 1; cfgs.add(mid); depth_m[(mid, key)] += 1
    _write(recs, out_path)
    dm = sorted(depth_m.values())
    _summary("mutation-openpilot", recs, nb, nm, cfgs, out_path)
    print(f"  cells={len(depth_m)} draws/cell min/med/max {dm[0]}/{dm[len(dm)//2]}/{dm[-1]}; dropped invalid={dict(inv)}")
    return out_path


# ----------------------------------------------------------------------------- transfuser
def build_mutation_transfuser(out_path=None):
    """TransFuser: BASE = nominal r0-r4 (Proxima nominal campaign, suite scenarios only) +
    base r5-r39; every mutant is a config."""
    store = os.path.join(RAW, "transfuser")
    out_path = out_path or os.path.join(DERIVED, "mutation_transfuser", "runs.jsonl")
    suite = {d["sid"] for d in json.load(open(f"{store}/suite.json"))["suite"]}
    recs, cfgs, nb, nm = [], set(), 0, 0
    inv = collections.Counter()
    def key(j): return f"{j['scenario_cls']}#{j['sid']}"
    nd = os.path.join(store, "nominal")
    for jid, j, r in _mut_rows("transfuser", f"{nd}/campaign_nominal_jobs_task*.results.jsonl",
                               f"{nd}/campaign_nominal_jobs.jsonl", nd):
        if j["sid"] not in suite:
            continue
        ok, t = _mut_valid_trig("transfuser", r)
        if ok:
            recs.append(_rec("BASE", key(j), j["seed"], t, set(), True, "transfuser", "CARLA")); nb += 1
        else:
            inv[r.get("outcome")] += 1
    for jid, j, r in _mut_rows("transfuser", f"{store}/jobs_base_task*.results.jsonl",
                               f"{store}/jobs_base.jsonl", store):
        ok, t = _mut_valid_trig("transfuser", r)
        if ok:
            recs.append(_rec("BASE", key(j), j["seed"], t, set(), True, "transfuser", "CARLA")); nb += 1
        else:
            inv[r.get("outcome")] += 1
    for jid, j, r in _mut_rows("transfuser", f"{store}/jobs_matrix*_task*.results.jsonl",
                               f"{store}/jobs_matrix*.jsonl", store):
        ok, t = _mut_valid_trig("transfuser", r)
        if not ok:
            inv[r.get("outcome")] += 1; continue
        mid = (j.get("mutant") or {}).get("mid") or j["job_id"].split("_")[1]
        recs.append(_rec(f"MUT:{mid}", key(j), j["seed"], t, set(), False, "transfuser", "CARLA",
                         fault_module=(j.get("mutant") or {}).get("site", "?").split(":")[0]))
        nm += 1; cfgs.add(mid)
    _write(recs, out_path)
    _summary("mutation-transfuser", recs, nb, nm, cfgs, out_path)
    print(f"  dropped invalid={dict(inv)}")
    return out_path


BUILDERS = {"openpilot": build_mutation_openpilot, "transfuser": build_mutation_transfuser}

if __name__ == "__main__":
    for stack in ([a for a in sys.argv[1:] if not a.startswith("--")] or ["openpilot", "transfuser"]):
        BUILDERS[stack]()
