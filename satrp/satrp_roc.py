#!/usr/bin/env python3
"""
satrp_roc.py — false-positive / recall operating-point view (ROC-style).

The baselines (STRAP, uniform, random) flag on a single trigger and therefore occupy a
SINGLE, high-false-positive operating point they cannot leave. SA-TRP, via its
confirmation threshold gamma, traces a whole recall-vs-FP curve. Comparing methods on a
single scalar (F1) hides this; here we plot the operating points directly and report:

  * recall@matched-FP  : SA-TRP's recall at the FP rate of each baseline (if reachable);
  * FP@matched-recall  : the FP each baseline pays to reach SA-TRP's recall (if reachable);
  * the lowest FP each method can operate at (baselines are stuck high; SA-TRP goes low).

All quantities are read at a fixed budget (2x runs/scenario) so (FP, recall) is a genuine
single-operating-point pair. Output (INJECT_OUT): satrp_roc.csv, satrp_roc.png
"""
import os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import eval_satrp as E

OUT  = os.path.expanduser(os.environ.get("INJECT_OUT", os.path.join(os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "results", "_unnamed"))); os.makedirs(OUT, exist_ok=True)
GRID = [float(x) for x in os.environ.get("SATRP_GAMMA_GRID",
        "0.55,0.6,0.65,0.7,0.75,0.8,0.85,0.9").split(",")]


def _interp(xs, ys, x0):
    """linear interpolation of y at x0 along the curve sorted by x; None if out of range."""
    pts = sorted(zip(xs, ys))
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    if x0 < xs[0] or x0 > xs[-1]:
        return None
    return float(np.interp(x0, xs, ys))


def main():
    rows = []
    for g in GRID:
        summ = E.run(gamma=g, quiet=True)
        if summ is None:
            print("no data / too few faults yet"); return
        s = summ[summ.subset == "all"].set_index("method")
        for m in E.METHODS:
            rows.append(dict(gamma=g, method=m,
                             fp=float(s.loc[m, "fp_at_2x"]), recall=float(s.loc[m, "recall_at_2x"])))
    roc = pd.DataFrame(rows)
    roc.to_csv(f"{OUT}/satrp_roc.csv", index=False)

    # baselines are gamma-independent -> one point each (mean over gamma)
    bpts = {m: (roc[roc.method == m]["fp"].mean(), roc[roc.method == m]["recall"].mean())
            for m in E.NAIVE}

    # --- headline: recall achievable within a practical false-alarm budget ---
    FP_BUDGETS = [float(x) for x in os.environ.get("SATRP_FP_BUDGETS", "0.05,0.1,0.2").split(",")]
    min_baseline_fp = min(fp for fp, _ in bpts.values())
    print(f"\nLowest FP any baseline can operate at: {min_baseline_fp:.3f}  "
          f"(no baseline has an operating point below this)")
    print("Recall within a practical false-alarm budget (SA-TRP only — baselines cannot reach it):")
    for budget in FP_BUDGETS:
        line = [f"FP<={budget:.2f}:"]
        for v in E.SATRP:
            d = roc[roc.method == v]
            reach = d[d["fp"] <= budget]
            r = reach["recall"].max() if len(reach) else 0.0
            line.append(f"{v.split('_')[1]}={r:.3f}")
        reachable = [m for m, (fp, _) in bpts.items() if fp <= budget]
        line.append(f"| baselines here: {reachable if reachable else 'NONE'}")
        print("   " + " ".join(line))
    print(f"\nOperating points @2x budget (grid={GRID})")
    print("baseline points (FP, recall): " + " | ".join(f"{m}=({fp:.3f},{r:.3f})" for m, (fp, r) in bpts.items()))
    print(f"{'variant':12s} {'min FP':>7} {'max recall':>10}  vs each baseline:")
    for v in E.SATRP:
        d = roc[roc.method == v]
        fps, recs = list(d["fp"]), list(d["recall"])
        print(f"{v:12s} {min(fps):>7.3f} {max(recs):>10.3f}")
        for m, (bfp, br) in bpts.items():
            r_at = _interp(fps, recs, bfp)        # SA-TRP recall at baseline's FP
            fp_at = _interp(recs, fps, br)        # SA-TRP FP at baseline's recall
            msg = []
            if r_at is not None:
                msg.append(f"recall@{m}-FP({bfp:.2f})={r_at:.3f} (vs {br:.3f})")
            else:
                msg.append(f"never reaches {m}'s FP={bfp:.2f} (SA-TRP stays below)")
            if fp_at is not None and fp_at > 0:
                msg.append(f"FP@{m}-recall={fp_at:.3f} (vs {bfp:.3f}, {bfp/max(fp_at,1e-9):.1f}x less)")
            print("      - " + "; ".join(msg))

    try:
        sty = {"satrp_cold": ("#8c564b", "SA-TRP (no history)"),
               "satrp_base": ("#2ca02c", "SA-TRP (baseline known)"),
               "satrp_warm": ("#17becf", "SA-TRP (full history)")}
        bsty = {"strap": ("#d62728", "STRAP", "X"), "uniform": ("#9467bd", "Uniform", "s"),
                "random": ("#bbbbbb", "Random", "^"), "oracle": ("#1f77b4", "Oracle", "*")}
        fig, ax = plt.subplots(figsize=(6.4, 5))
        for v in E.SATRP:
            d = roc[roc.method == v].sort_values("fp"); col, lab = sty[v]
            ax.plot(d["fp"], d["recall"], "o-", color=col, label=lab, lw=2.2, ms=4)
        for m in E.NAIVE + (["oracle"] if "oracle" not in E.NAIVE else []):
            if m not in bsty:
                continue
            sub = roc[roc.method == m]
            col, lab, mk = bsty[m]
            ax.scatter(sub["fp"].mean(), sub["recall"].mean(), color=col, marker=mk, s=90,
                       zorder=5, label=f"{lab} (fixed pt)")
        ax.set_xlabel("false-positive rate")
        ax.set_ylabel("recall (true regressions detected)")
        ax.set_title("Operating points: recall vs. false-positive rate\n(SA-TRP sweeps γ; baselines are stuck at one point)")
        ax.set_xlim(-0.02, 1.0); ax.set_ylim(0, 1.02); ax.grid(alpha=.3); ax.legend(fontsize=7.5, loc="lower right")
        fig.tight_layout(); fig.savefig(f"{OUT}/satrp_roc.png", dpi=140)
        print(f"\nwrote {OUT}/satrp_roc.png and {OUT}/satrp_roc.csv")
    except Exception as e:
        print("figure skipped:", e)


if __name__ == "__main__":
    main()
