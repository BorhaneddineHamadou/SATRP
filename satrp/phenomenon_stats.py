#!/usr/bin/env python3
"""RQ1 phenomenon statistics for a mutation (or real-fault) instance under the Fisher GT.
usage: phenomenon_stats.py <instance> [<store dir with screen_classes.json/selected.json/jobs_screen*>]
Writes results/<instance>/phenomenon.json and prints a markdown summary."""
import os, sys, json, glob, collections
import numpy as np
from scipy.stats import fisher_exact
H = os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); inst = sys.argv[1]; store = sys.argv[2] if len(sys.argv) > 2 else None
ALPHA, DELTA, FL, FH = 0.05, 0.15, 0.2, 0.8
rng = np.random.default_rng(1)
rows = [json.loads(l) for l in open(f"{H}/data/derived/{inst}/runs.jsonl") if l.strip()]
pool = collections.defaultdict(list)   # (cfg, scen) -> [(seed, trig)]
for d in rows:
    pool[(d["commit"], d["scenario"])].append((d["seed"], int(d["outcome"] == "collision")))
cfgs = sorted({c for c, _ in pool if c != "BASE"}); scen = sorted({s for _, s in pool})
def fisher(kp, n_p, kq, n_q):
    return fisher_exact([[kp, n_p-kp], [kq, n_q-kq]], alternative="greater")[1] if n_p and n_q else 1.0
def gt(c, s, even_only):
    P = [t for sd, t in pool[(c, s)] if (not even_only) or sd % 2 == 0]
    Q = [t for sd, t in pool[("BASE", s)] if (not even_only) or sd % 2 == 0]
    if not P or not Q: return False, None
    p, q = np.mean(P), np.mean(Q)
    return (p - q >= DELTA) and fisher(sum(P), len(P), sum(Q), len(Q)) <= ALPHA, p
out = dict(instance=inst, runs=len(rows), configs=len(cfgs), scenarios=len(scen), cells=len(cfgs)*len(scen),
           seeds_per_cell=int(np.median([len(pool[(c, s)]) for c in cfgs for s in scen])),
           base_seeds=int(np.median([len(pool[("BASE", s)]) for s in scen])))
# baseline
q = {s: np.mean([t for _, t in pool[("BASE", s)]]) for s in scen}
out["base"] = dict(mean_q=float(np.mean(list(q.values()))), q0=sum(v == 0 for v in q.values()),
                   q_intermediate=sum(0 < v < 1 for v in q.values()), q_flaky=sum(FL <= v <= FH for v in q.values()),
                   q_ge85=sum(v >= .85 for v in q.values()), self_disagree=float(np.mean([2*v*(1-v) for v in q.values()])))
# mutant cells
ph = {(c, s): np.mean([t for _, t in pool[(c, s)]]) for c in cfgs for s in scen}
pv = np.array(list(ph.values()))
out["cells_mut"] = dict(intermediate=int(((pv > 0) & (pv < 1)).sum()), flaky=int(((pv >= FL) & (pv <= FH)).sum()),
                        always_pass=int((pv == 0).sum()), always_fail=int((pv == 1).sum()),
                        self_disagree=float(np.mean(2*pv*(1-pv))), self_disagree_gt_0=float(np.mean(2*pv*(1-pv) > 0)))
# GT
for tag, ev in (("full", False), ("sep", True)):
    T = {c: {s: p for s in scen for ok, p in [gt(c, s, ev)] if ok} for c in cfgs}
    cells = [(c, s, p) for c in T for s, p in T[c].items()]
    flaky = [1 for _, _, p in cells if FL <= p <= FH]
    per = {c: len(T[c]) for c in cfgs}
    reg = [c for c in cfgs if per[c] > 0]
    out[f"gt_{tag}"] = dict(cells=len(cells), flaky=len(flaky), regressing_cfgs=len(reg), zero_cfgs=len(cfgs)-len(reg),
                            cells_per_regressing_cfg_min=min([per[c] for c in reg], default=0),
                            cells_per_regressing_cfg_max=max([per[c] for c in reg], default=0),
                            cells_per_regressing_cfg_median=float(np.median([per[c] for c in reg])) if reg else 0,
                            mean_effect=float(np.mean([p - q[s] for _, s, p in cells])) if cells else 0,
                            per_config=per, deterministic_cells=sum(1 for _, _, p in cells if p > FH),
                            weak_cells=sum(1 for _, _, p in cells if p < FL))
# null calibration (parametric, every version == BASE) + empirical odd-vs-even BASE
def null(npv, nbv, reps=1000):
    cnt = []
    for _ in range(reps):
        c = 0
        for s in scen:
            for _v in cfgs:
                kp = rng.binomial(npv, q[s]); kq = rng.binomial(nbv, q[s])
                if kp/npv - kq/nbv >= DELTA and fisher(kp, npv, kq, nbv) <= ALPHA: c += 1
        cnt.append(c)
    return float(np.mean(cnt)), float(np.std(cnt))
nv, nb = out["seeds_per_cell"], out["base_seeds"]
emp = 0
for s in scen:
    a = [t for sd, t in pool[("BASE", s)] if sd % 2]; b = [t for sd, t in pool[("BASE", s)] if not sd % 2]
    if np.mean(a) - np.mean(b) >= DELTA and fisher(sum(a), len(a), sum(b), len(b)) <= ALPHA: emp += 1
out["null"] = dict(full=null(nv, nb), sep=null(nv//2, nb//2), empirical_odd_vs_even=emp,
                   full_rate=None)
out["null"]["full_rate"] = out["null"]["full"][0] / out["cells"]; out["null"]["sep_rate"] = out["null"]["sep"][0] / out["cells"]
# screening / twins
if store:
    sc = json.load(open(f"{store}/screen_classes.json")); sel = json.load(open(f"{store}/selected.json"))
    out["screen"] = dict(candidates=len(sc["mutants"]), classes=dict(collections.Counter(m["cls"] for m in sc["mutants"])),
                         selected=sel["N"], selected_counts=sel["counts"], per_op=sel["per_op"], per_file=sel["per_file"])
    selected_ids = set(sel["selected"]); cls_of = {m["mid"]: m["cls"] for m in sc["mutants"]}
    selcls = collections.Counter(cls_of.get(m, "?") for m in selected_ids)
    out["screen"]["selected_by_screen_class"] = dict(selcls)
    # GT zero configs by screen class
    z = [c.split(":", 1)[1] for c in cfgs if out["gt_full"]["per_config"][c] == 0]
    out["screen"]["zero_gt_by_class"] = dict(collections.Counter(cls_of.get(m, "?") for m in z))
    res = {}
    for f in glob.glob(f"{store}/jobs_screen*_task*.results.jsonl") + glob.glob(f"{store}/results/jobs_screen*_task*.results.jsonl"):
        for l in open(f):
            if l.strip():
                r = json.loads(l); res[r["job_id"]] = r
    twins = []
    for jid, r in res.items():
        if jid.startswith("screen_s"):
            tw = res.get(jid.replace("screen_s", "screentwin_s"))
            ok = ("completed", "collision", "out_of_lane")          # valid driving verdicts (out_of_lane = openpilot trigger)
            if tw and r["outcome"] in ok and tw["outcome"] in ok:
                fail = lambda o: o in ("collision", "out_of_lane")
                twins.append(int(fail(r["outcome"]) != fail(tw["outcome"])))   # binary-verdict flip
    out["twins"] = dict(pairs=len(twins), disagree=int(sum(twins)), rate=float(np.mean(twins)) if twins else None,
                        trace_floor_median=float(np.median(list(sc["floor"].values()))))
os.makedirs(f"{H}/results/{inst}", exist_ok=True)
json.dump(out, open(f"{H}/results/{inst}/phenomenon.json", "w"), indent=1, default=str)
o = out
print(f"## {inst}: runs {o['runs']}, cfgs {o['configs']}, scen {o['scenarios']}, cells {o['cells']}, seeds/cell {o['seeds_per_cell']} (base {o['base_seeds']})")
print(f"BASE mean q {o['base']['mean_q']:.3f}; q=0 {o['base']['q0']}, intermediate {o['base']['q_intermediate']}, flaky-band {o['base']['q_flaky']}, q>=.85 {o['base']['q_ge85']}; base self-disagree {o['base']['self_disagree']:.3f}")
print(f"MUT cells: intermediate {o['cells_mut']['intermediate']}, flaky-band {o['cells_mut']['flaky']}, always-pass {o['cells_mut']['always_pass']}, always-fail {o['cells_mut']['always_fail']}; self-disagree {o['cells_mut']['self_disagree']:.3f}")
for t in ("full", "sep"):
    g = o[f"gt_{t}"]; print(f"GT {t}: cells {g['cells']} (flaky {g['flaky']}, deterministic>{FH} {g['deterministic_cells']}, weak<{FL} {g['weak_cells']}); regressing cfgs {g['regressing_cfgs']} / zero {g['zero_cfgs']}; cells per regressing cfg {g['cells_per_regressing_cfg_min']}-{g['cells_per_regressing_cfg_max']} (med {g['cells_per_regressing_cfg_median']}); mean effect {g['mean_effect']:.2f}")
print(f"NULL: full {o['null']['full'][0]:.1f}±{o['null']['full'][1]:.1f} ({100*o['null']['full_rate']:.2f}% of cells), sep {o['null']['sep'][0]:.1f}±{o['null']['sep'][1]:.1f}, empirical odd-vs-even {o['null']['empirical_odd_vs_even']}")
if "screen" in o: print("SCREEN:", o["screen"]); print("TWINS:", o["twins"])
