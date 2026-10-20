#!/usr/bin/env python3
"""
eval_satrp_frontier.py — the GAMMA-F1 frontier (RQ4).

The confirmation threshold GAMMA trades recall for precision: too high and SA-TRP
cannot accumulate enough evidence to confirm (recall/F1 collapse at low budget),
too low and it confirms baseline flakiness (false positives). Reporting a single
GAMMA can therefore under- or over-state SA-TRP. This driver sweeps GAMMA and, for
each SA-TRP variant, plots F1-AUC vs GAMMA against the GAMMA-independent baselines
(STRAP/uniform/random/oracle), and reports each variant at its best GAMMA.

Outputs (INJECT_OUT = results/<instance>):
  satrp_frontier.csv   gamma, method, f1_auc, recall_auc, fp_at_2x
  satrp_frontier.png   F1-AUC vs gamma (SA-TRP curves) with baseline reference lines
"""
import os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import eval_satrp as E

OUT  = os.path.expanduser(os.environ.get("INJECT_OUT", os.path.join(os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "results", "_unnamed"))); os.makedirs(OUT, exist_ok=True)
GRID = [float(x) for x in os.environ.get("SATRP_GAMMA_GRID",
        "0.55,0.6,0.65,0.7,0.75,0.8,0.85,0.9").split(",")]


def main():
    rows = []
    for g in GRID:
        summ = E.run(gamma=g, quiet=True)        # no files/plots; returns summary df
        if summ is None:
            print("no data / too few faults yet"); return
        s = summ[summ.subset == "all"].set_index("method")
        for m in E.METHODS:
            rows.append(dict(gamma=g, method=m, f1_auc=float(s.loc[m, "f1_auc"]),
                             recall_auc=float(s.loc[m, "auc"]), fp_at_2x=float(s.loc[m, "fp_at_2x"])))
    fr = pd.DataFrame(rows)
    fr.to_csv(f"{OUT}/satrp_frontier.csv", index=False)

    # GAMMA-independent baselines: take the mean across gamma (should be ~constant)
    base = {m: fr[fr.method == m]["f1_auc"].mean() for m in E.NAIVE}
    print(f"\nGAMMA-F1 frontier  (grid={GRID})")
    print(f"{'gamma':>6} " + " ".join(f"{m:>11}" for m in E.SATRP))
    for g in GRID:
        d = fr[fr.gamma == g].set_index("method")
        print(f"{g:>6.2f} " + " ".join(f"{d.loc[m,'f1_auc']:>11.3f}" for m in E.SATRP))
    print("\nGamma-independent baselines (F1-AUC): " +
          " | ".join(f"{m}={base[m]:.3f}" for m in E.NAIVE))
    print("\nBest gamma per SA-TRP variant:")
    for m in E.SATRP:
        sub = fr[fr.method == m]
        i = sub["f1_auc"].idxmax(); bg, bf = sub.loc[i, "gamma"], sub.loc[i, "f1_auc"]
        vs_strap = bf - base.get("strap", float("nan"))
        vs_unif  = bf - base.get("uniform", float("nan"))
        print(f"  {m:11s} best F1-AUC={bf:.3f} @ gamma={bg:.2f}  "
              f"(vs STRAP {vs_strap:+.3f} | vs Uniform {vs_unif:+.3f})")

    try:
        sty = {"satrp_cold": ("#8c564b", "SA-TRP (no history)"),
               "satrp_base": ("#2ca02c", "SA-TRP (baseline known)"),
               "satrp_warm": ("#17becf", "SA-TRP (full history)")}
        bsty = {"strap": ("#d62728", "STRAP"), "uniform": ("#9467bd", "Uniform"),
                "random": ("#bbbbbb", "Random"), "oracle": ("#1f77b4", "Oracle")}
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for m in E.SATRP:
            d = fr[fr.method == m]; col, lab = sty[m]
            ax.plot(d.gamma, d.f1_auc, "o-", color=col, label=lab, lw=2.3)
        for m in E.NAIVE:
            col, lab = bsty[m]
            ax.axhline(base[m], ls="--", color=col, lw=1.3, label=f"{lab} (γ-indep.)")
        ax.set_xlabel(r"confirmation threshold $\gamma$")
        ax.set_ylabel("F1-AUC (all faults, held-out)")
        ax.set_title(r"$\gamma$–F1 frontier: SA-TRP vs.\ baselines")
        ax.grid(alpha=.3); ax.legend(fontsize=7.5, ncol=2)
        fig.tight_layout(); fig.savefig(f"{OUT}/satrp_frontier.png", dpi=140)
        print(f"\nwrote {OUT}/satrp_frontier.png and {OUT}/satrp_frontier.csv")
    except Exception as e:
        print("figure skipped:", e)


if __name__ == "__main__":
    main()
