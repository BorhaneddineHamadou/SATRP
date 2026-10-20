#!/usr/bin/env python3
"""Real-fault validation anchor: per-cell effects, Fisher GT, null calibration,
mechanism tests, and SA-TRP-schema instances for Pylot (8 real versions) and
carla_garage TF++ (2 real versions). Campaign 2026-10-14..17, CARLA 0.9.10.1.

Trigger definitions
  straight block (TF++ host, 30 Prox scenarios): contact = max(crash)>0.5 in the npz
      trace (identical to the mutation-matrix builder adapter._mut_rows).
  leaderboard block (12 Town01 routes, both stacks): T1 = worker definition
      (any collision | red_light | outside_route_lanes | route_dev); blocked/timeout
      are separate outcomes.  T2 = T1 | blocked | timeout ("any failure"), reported
      as a sensitivity variant only.
GT rule = the mutation-matrix rule: one-sided Fisher exact p<=0.05 AND gap>=0.15,
  full pool (version 24 vs BASE 40) and budget-separated (even run_idx: 12 vs 20).
"""
import json, glob, os, sys, collections
import numpy as np, pandas as pd
from scipy.stats import fisher_exact
ROOT = os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
R = os.path.join(os.environ.get("SATRP_RAW", os.path.join(ROOT, "raw")), "realfaults")   # unpacked Zenodo archive
OUT = os.path.join(ROOT, "results", "realfaults"); os.makedirs(OUT, exist_ok=True)
DERIVED = os.path.join(ROOT, "data", "derived")
ALPHA, DELTA = 0.05, 0.15
rng = np.random.default_rng(20261017)

def jl(files):
    rows = []
    for f in files:
        for l in open(f):
            if l.strip(): rows.append(json.loads(l))
    return rows

def dedupe(rows, prefer):
    """last write wins, but rows from `prefer` files override (OOM rerun)."""
    d = {}
    for r in rows: d[r["job_id"]] = r
    for r in prefer: d[r["job_id"]] = r
    return list(d.values())

# ------------------------------------------------------------------ load
# TF++ straight: jobs give scenario_cls/sid/seed/run_idx/trace_out
tj = {j["job_id"]: j for j in jl([f"{R}/tfpp/jobs_base.jsonl", f"{R}/tfpp/jobs_versions.jsonl"])}
tr = dedupe(jl(sorted(glob.glob(f"{R}/tfpp/jobs_base_task*.results.jsonl")) +
              sorted(glob.glob(f"{R}/tfpp/jobs_versions_task*.results.jsonl"))), [])
recs = []   # unified: stack, block, vid, scen, run_idx, seed, trig(T1), trig_any(T2), status
agree = collections.Counter()
for r in tr:
    j = tj[r["job_id"]]
    if r.get("trace_exists") is False or str(r["outcome"]).startswith("error"):
        continue
    p = j["trace_out"]                       # campaign-time absolute path -> resolve inside the raw store
    if not os.path.exists(p) and not os.path.exists(p + ".npz"):
        p = os.path.join(R, "tfpp", os.path.basename(os.path.dirname(p)), os.path.basename(p))
    p = p if os.path.exists(p) else p + ".npz"
    z = np.load(p, allow_pickle=True); cols = [str(c) for c in z["columns"]]
    contact = bool(np.nanmax(z["data"][:, cols.index("crash")]) > 0.5)
    agree[(r["outcome"], contact)] += 1
    vid = j["mutant"]["mid"]
    recs.append(dict(stack="tfpp", block="straight", vid=vid, scen=f"{j['scenario_cls']}#{j['sid']}",
                     cls=j["scenario_cls"], run_idx=j["run_idx"], seed=j["seed"], trig=int(contact),
                     trig_any=int(contact), status=r["outcome"]))
print("TF++ straight outcome-vs-trace agreement:", dict(agree))

def lb_rows(stack):
    base = sorted(glob.glob(f"{R}/{stack}/jobs_lb_base_task*.results.jsonl"))
    vers = sorted(glob.glob(f"{R}/{stack}/jobs_lb_versions_task*.results.jsonl"))
    rer = sorted(glob.glob(f"{R}/{stack}/jobs_lb_oom_rerun_task*.results.jsonl"))
    rows = dedupe(jl(base + vers), jl(rer))
    out, drop = [], collections.Counter()
    for r in rows:
        if r.get("status") == "no_record" or r.get("trigger") is None:
            drop[r.get("outcome")] += 1; continue
        cls = r["job_id"].split("_")[-3]; rt = r["job_id"].split("_")[-2]
        t1 = int(r["trigger"]); t2 = int(t1 or r["blocked"] or r["timeout"])
        inf = r["infractions"]
        out.append(dict(stack=stack, block="lb", vid=r["vid"], scen=f"{cls}#{rt}", cls=cls,
                        run_idx=r["run_idx"], seed=r["seed"], trig=t1, trig_any=t2, status=r["status"],
                        collision=int(sum(inf[k] for k in ("collisions_pedestrian","collisions_vehicle","collisions_layout"))>0),
                        red_light=int(inf["red_light"]>0), ool=int(inf["outside_route_lanes"]>0),
                        route_dev=int(inf["route_dev"]>0), blocked=int(r["blocked"]), timeout=int(r["timeout"]),
                        proof_ok=bool(r.get("proof_ok")), dt=r.get("difftrace_lines")))
    print(f"{stack} lb rows kept {len(out)} dropped {dict(drop)}; proof_ok all: {all(x['proof_ok'] for x in out)}")
    return out
recs += lb_rows("tfpp") + lb_rows("pylot")
df = pd.DataFrame(recs)
assert (df.seed % 2 == df.run_idx % 2).all(), "seed parity must equal run_idx parity (sep protocol)"
df.to_csv(f"{OUT}/all_runs.csv", index=False)
print(df.groupby(["stack","block","vid"]).size().to_string())

# ------------------------------------------------------------------ per-cell table
def fisher(kp, n_p, kq, n_q):
    if n_p == 0 or n_q == 0: return 1.0
    return fisher_exact([[kp, n_p-kp],[kq, n_q-kq]], alternative="greater")[1]

tv = json.load(open(f"{R}/tfpp/versions.json"))
tcov = {v["vid"]: (set(v["covering_scenarios"]), set(v["negative_control_scenarios"])) for v in tv}
pv = json.load(open(f"{R}/pylot/versions/versions.json"))["versions"]
pstatus = {v["vid"]: v["status"] for v in pv}

cells = []
for (stack, block), g in df.groupby(["stack","block"]):
    base = g[g.vid=="base"]
    for vid, gv in g[g.vid!="base"].groupby("vid"):
        for scen, gs in gv.groupby("scen"):
            gb = base[base.scen==scen]
            for tcol, tag in (("trig","T1"),("trig_any","T2")):
                kp, n_p = int(gs[tcol].sum()), len(gs); kq, n_q = int(gb[tcol].sum()), len(gb)
                p, q = kp/n_p, kq/n_q; pval = fisher(kp,n_p,kq,n_q)
                gt_full = (p-q >= DELTA) and pval <= ALPHA
                ge, be = gs[gs.run_idx%2==0], gb[gb.run_idx%2==0]
                kpe, kqe = int(ge[tcol].sum()), int(be[tcol].sum())
                pe, qe = kpe/len(ge), kqe/len(be); pvale = fisher(kpe,len(ge),kqe,len(be))
                gt_sep = (pe-qe >= DELTA) and pvale <= ALPHA
                cls = gs.cls.iloc[0]
                role = ""
                if stack=="tfpp" and block=="straight":
                    cov, neg = tcov[vid]; role = "covering" if cls in cov else ("neg_control" if cls in neg else "")
                cells.append(dict(stack=stack, block=block, vid=vid, scen=scen, cls=cls, trig=tag, role=role,
                                  n_p=n_p, k_p=kp, p=round(p,3), n_q=n_q, k_q=kq, q=round(q,3), gap=round(p-q,3),
                                  fisher_p=pval, gt_full=gt_full, n_p_even=len(ge), k_p_even=kpe, k_q_even=kqe,
                                  gap_even=round(pe-qe,3), fisher_p_even=pvale, gt_sep=gt_sep))
C = pd.DataFrame(cells); C.to_csv(f"{OUT}/cells.csv", index=False)

# ------------------------------------------------------------------ null calibration
def null_counts(stack, block, tcol, n_versions, reps=2000):
    """Parametric null: every version == BASE. Draw k_p~Bin(24,q), k_q~Bin(40,q) per cell
    (full) / Bin(12,q),Bin(20,q) (sep); count GT cells over n_versions versions."""
    g = df[(df["stack"]==stack)&(df.block==block)&(df.vid=="base")]
    qs = g.groupby("scen")[tcol].mean().values
    nv = df[(df["stack"]==stack)&(df.block==block)&(df.vid!="base")].groupby(["vid","scen"]).size().median()
    nb = g.groupby("scen").size().median()
    out = {}
    for name, (npv, nbv) in {"full": (int(nv), int(nb)), "sep": (int(nv)//2, int(nb)//2)}.items():
        cnt = []
        for _ in range(reps):
            c = 0
            for q in qs:
                for _v in range(n_versions):
                    kp = rng.binomial(npv, q); kq = rng.binomial(nbv, q)
                    if kp/npv - kq/nbv >= DELTA and fisher(kp,npv,kq,nbv) <= ALPHA: c += 1
            cnt.append(c)
        out[name] = (float(np.mean(cnt)), float(np.std(cnt)))
    # empirical: even-BASE vs odd-BASE as a pseudo-version (20 vs 20), T1
    emp = 0
    for scen, gs in g.groupby("scen"):
        a, b = gs[gs.run_idx%2==1][tcol], gs[gs.run_idx%2==0][tcol]
        if a.mean()-b.mean() >= DELTA and fisher(int(a.sum()),len(a),int(b.sum()),len(b)) <= ALPHA: emp += 1
    out["empirical_odd_vs_even_base"] = emp
    return out

lines = ["# Real-fault validation anchor — numbers (generated %s)" % pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"), ""]
lines += ["Trigger T1 = straight: trace contact; leaderboard: collision|red_light|outside_route_lanes|route_dev (blocked/timeout separate).",
          "T2 = T1|blocked|timeout (sensitivity). GT = one-sided Fisher p<=0.05 AND gap>=0.15 (same rule as the mutation matrices).", ""]
for (stack, block), g in df.groupby(["stack","block"]):
    nvers = g[g.vid!="base"].vid.nunique()
    lines.append(f"## {stack} / {block} block — {g[g.vid=='base'].shape[0]} BASE runs, {nvers} versions, {g.scen.nunique()} scenarios")
    base = g[g.vid=="base"]
    bq = base.groupby("scen").trig.mean()
    lines.append(f"BASE trigger rate: mean {base.trig.mean():.3f}; cells with q>=0.85 (saturated, undetectable): {(bq>=0.85).sum()}/{len(bq)}; q==0: {(bq==0).sum()}")
    if block=="lb":
        lines.append("BASE outcome mix: " + ", ".join(f"{k} {base[k].mean():.3f}" for k in ("collision","red_light","ool","route_dev","blocked","timeout")))
    lines.append("")
    lines.append("| version | n | T1 rate | base T1 | pooled gap | pooled Fisher p | GT cells full (T1) | GT cells sep (T1) | GT full (T2) | T2 rate | base T2 |" + (" collision | red | ool | blocked | timeout |" if block=="lb" else ""))
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|" + ("---|---|---|---|---|" if block=="lb" else ""))
    for vid, gv in g[g.vid!="base"].groupby("vid"):
        cc = C[(C["stack"]==stack)&(C.block==block)&(C.vid==vid)]
        c1, c2 = cc[cc.trig=="T1"], cc[cc.trig=="T2"]
        pp = fisher(int(gv.trig.sum()), len(gv), int(base.trig.sum()), len(base))
        extra = ""
        if block=="lb":
            extra = " " + " | ".join(f"{gv[k].mean():.3f}/{base[k].mean():.3f}" for k in ("collision","red_light","ool","blocked","timeout")) + " |"
        lines.append(f"| {vid}{' ('+pstatus[vid]+')' if vid in pstatus else ''} | {len(gv)} | {gv.trig.mean():.3f} | {base.trig.mean():.3f} | {gv.trig.mean()-base.trig.mean():+.3f} | {pp:.2g} | "
                     f"{int(c1.gt_full.sum())}/{len(c1)} | {int(c1.gt_sep.sum())}/{len(c1)} | {int(c2.gt_full.sum())}/{len(c2)} | {gv.trig_any.mean():.3f} | {base.trig_any.mean():.3f} |{extra}")
    lines.append("")
    nc = null_counts(stack, block, "trig", nvers)
    lines.append(f"Null calibration (all versions == BASE), expected GT cells over {nvers} versions: full {nc['full'][0]:.1f}±{nc['full'][1]:.1f}, sep {nc['sep'][0]:.1f}±{nc['sep'][1]:.1f}; "
                 f"empirical odd-vs-even BASE pseudo-version: {nc['empirical_odd_vs_even_base']} GT cells / {g.scen.nunique()}")
    obs_full = int(C[(C["stack"]==stack)&(C.block==block)&(C.trig=='T1')].gt_full.sum()); obs_sep = int(C[(C["stack"]==stack)&(C.block==block)&(C.trig=='T1')].gt_sep.sum())
    lines.append(f"OBSERVED GT cells (T1): full {obs_full}, sep {obs_sep}")
    lines.append("")
    # per-cell GT list
    gtc = C[(C["stack"]==stack)&(C.block==block)&(C.trig=="T1")&(C.gt_full)]
    if len(gtc):
        lines.append("GT cells (full, T1): " + "; ".join(f"{r.vid}×{r.scen} p={r.p:.2f} q={r.q:.2f} (P={r.fisher_p:.1e}{', sep' if r.gt_sep else ''})" for r in gtc.itertuples()))
    gtc2 = C[(C["stack"]==stack)&(C.block==block)&(C.trig=="T2")&(C.gt_full)]
    gtc2 = gtc2[~gtc2.set_index(["vid","scen"]).index.isin(gtc.set_index(["vid","scen"]).index)]
    if len(gtc2):
        lines.append("Additional GT cells under T2 only (blocked/timeout driven): " + "; ".join(f"{r.vid}×{r.scen} p={r.p:.2f} q={r.q:.2f}" for r in gtc2.itertuples()))
    lines.append("")

# ------------------------------------------------------------------ mechanism tests (pre-registered, TF++ straight)
lines.append("## Pre-registered mechanism tests — TF++ straight block (versions.json covering vs negative-control classes)")
lines.append("| version | class | role | n | p | q | gap | Fisher p |"); lines.append("|---|---|---|---|---|---|---|---|")
g = df[(df["stack"]=="tfpp")&(df.block=="straight")]; base = g[g.vid=="base"]
for vid in ("v_lidar_stale","v_speed_offset"):
    gv = g[g.vid==vid]; cov, neg = tcov[vid]
    for cls, gc in gv.groupby("cls"):
        gb = base[base.cls==cls]; role = "covering" if cls in cov else ("NEG-CONTROL" if cls in neg else "-")
        lines.append(f"| {vid} | {cls} | {role} | {len(gc)} | {gc.trig.mean():.3f} | {gb.trig.mean():.3f} | {gc.trig.mean()-gb.trig.mean():+.3f} | {fisher(int(gc.trig.sum()),len(gc),int(gb.trig.sum()),len(gb)):.2g} |")
    pc = gv[gv.cls.isin(cov)]; bc = base[base.cls.isin(cov)]
    lines.append(f"| {vid} | ALL covering | pooled | {len(pc)} | {pc.trig.mean():.3f} | {bc.trig.mean():.3f} | {pc.trig.mean()-bc.trig.mean():+.3f} | {fisher(int(pc.trig.sum()),len(pc),int(bc.trig.sum()),len(bc)):.2g} |")
lines.append("")
lines.append("## Per-class rates — leaderboard block (post-hoc mapping; Pylot pre-registration used the Prox templates which Pylot did not run)")
for stack in ("tfpp","pylot"):
    g = df[(df["stack"]==stack)&(df.block=="lb")]; base = g[g.vid=="base"]
    clss = sorted(g.cls.unique())
    lines.append(f"### {stack}: T1 rate per class (version / base), n per class = 48 version / 80 base")
    lines.append("| version | " + " | ".join(clss) + " | any-failure T2 |"); lines.append("|---|" + "---|"*(len(clss)+1))
    lines.append("| base | " + " | ".join(f"{base[base.cls==c].trig.mean():.2f}" for c in clss) + f" | {base.trig_any.mean():.2f} |")
    for vid, gv in g[g.vid!="base"].groupby("vid"):
        lines.append(f"| {vid} | " + " | ".join(f"{gv[gv.cls==c].trig.mean():.2f}" + ("**" if fisher(int(gv[gv.cls==c].trig.sum()),len(gv[gv.cls==c]),int(base[base.cls==c].trig.sum()),len(base[base.cls==c]))<=0.05 else "") for c in clss) + f" | {gv.trig_any.mean():.2f} |")
    lines.append("(** = one-sided Fisher p<=0.05 vs base at class level)"); lines.append("")

open(f"{OUT}/real_numbers.md","w").write("\n".join(lines)); print("\n".join(lines))

# ------------------------------------------------------------------ SA-TRP instances (inject schema, _rec convention)
def rec(commit, scen, seed, trig, is_base, system, platform):
    return dict(commit=commit, scenario=scen, seed=int(seed), engaged=True,
                outcome=("collision" if trig else "completed"), min_ttc=None, fault_module="real",
                intended_scenarios=[], is_baseline=is_base, system=system, platform=platform)
def write_inst(name, sub, tcol="trig"):
    os.makedirs(f"{DERIVED}/{name}", exist_ok=True)
    with open(f"{DERIVED}/{name}/runs.jsonl","w") as f:
        for r in sub.itertuples():
            f.write(json.dumps(rec("BASE" if r.vid=="base" else f"REAL:{r.vid}", r.scen, r.seed, getattr(r,tcol), r.vid=="base", r.stack, "CARLA"))+"\n")
    print(f"wrote {name}: {len(sub)} records, {sub.scen.nunique()} scenarios, {sub.vid.nunique()-1} versions")
write_inst("real_tfpp", df[df["stack"]=="tfpp"])
write_inst("real_tfpp_straight", df[(df["stack"]=="tfpp")&(df.block=="straight")])
write_inst("real_pylot", df[df["stack"]=="pylot"])
write_inst("real_pylot_T2", df[df["stack"]=="pylot"], "trig_any")
