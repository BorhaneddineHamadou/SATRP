#!/usr/bin/env python3
"""Compare a fresh run (results/) against the values the paper was typeset from (results/paper/).

Prints, per instance and ground-truth mode, the best F1-AUC / FP@2x / recall@2x / Top-5
precision of every method side by side with the paper's value and the absolute difference,
then the phenomenon statistics and the clustered-bootstrap CIs. Exit code 1 if any
best-F1-AUC differs by more than TOL (default 0.005; bootstrap resampling is seeded, so a
re-run on the same platform is expected to be bit-identical)."""
import os, sys, json, glob
import pandas as pd
ROOT = os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOL = float(os.environ.get("TOL", "0.005"))
NEW, REF = f"{ROOT}/results", f"{ROOT}/results/paper"
bad = 0
for ref in sorted(glob.glob(f"{REF}/*/frontier_all_*_best.csv")):
    inst = os.path.basename(os.path.dirname(ref)); tag = os.path.basename(ref)[len("frontier_all_"):-len("_best.csv")]
    new = f"{NEW}/{inst}/{os.path.basename(ref)}"
    if not os.path.exists(new):
        print(f"\n## {inst} / {tag}: NOT RUN"); continue
    a = pd.read_csv(ref).set_index("method"); b = pd.read_csv(new).set_index("method")
    print(f"\n## {inst} / {tag}   (paper | rerun | diff)")
    for m in a.index:
        if m not in b.index: print(f"  {m:12s} missing in rerun"); bad += 1; continue
        d = abs(a.loc[m, "best_f1_auc"] - b.loc[m, "best_f1_auc"])
        flag = "" if d <= TOL else "   <-- differs"
        if d > TOL: bad += 1
        rec = "recall_at_2x" if "recall_at_2x" in a.columns else "recall_auc"
        print(f"  {m:12s} F1-AUC {a.loc[m,'best_f1_auc']:.3f} | {b.loc[m,'best_f1_auc']:.3f} | {d:.3f}   "
              f"FP@2x {a.loc[m,'fp_at_2x']:.3f} | {b.loc[m,'fp_at_2x']:.3f}   R {a.loc[m,rec]:.3f} | {b.loc[m,rec]:.3f}   "
              f"Top5 {a.loc[m,'topk5_prec']:.2f} | {b.loc[m,'topk5_prec']:.2f}{flag}")
for inst in ("mutation_openpilot", "mutation_transfuser"):
    r, n = f"{REF}/{inst}/phenomenon.json", f"{NEW}/{inst}/phenomenon.json"
    if os.path.exists(r) and os.path.exists(n):
        A, B = json.load(open(r)), json.load(open(n))
        print(f"\n## phenomenon {inst}: GT full cells {A['gt_full']['cells']} | {B['gt_full']['cells']}, flaky {A['gt_full']['flaky']} | {B['gt_full']['flaky']}, "
              f"null {A['null']['full'][0]:.1f} | {B['null']['full'][0]:.1f}, self-disagree {A['cells_mut']['self_disagree']:.3f} | {B['cells_mut']['self_disagree']:.3f}")
    r, n = f"{REF}/extra_analysis_mut_{inst}.json", f"{NEW}/extra_analysis_mut_{inst}.json"
    if os.path.exists(r) and os.path.exists(n):
        A, B = json.load(open(r))["ci"][inst], json.load(open(n))["ci"][inst]
        print(f"## CI {inst}: dF1 warm-vs-strap {A['dF1']:+.3f} [{A['dF1_lo']:+.3f},{A['dF1_hi']:+.3f}] | {B['dF1']:+.3f} [{B['dF1_lo']:+.3f},{B['dF1_hi']:+.3f}]; "
              f"FPx {A['FPx']:.1f} | {B['FPx']:.1f}; base-vs-SPRT {A['vs_sprt']['dF1']:+.3f} | {B['vs_sprt']['dF1']:+.3f}")
print("\nRESULT:", "all best-F1-AUC values within tolerance" if bad == 0 else f"{bad} value(s) differ by more than {TOL}")
sys.exit(1 if bad else 0)
