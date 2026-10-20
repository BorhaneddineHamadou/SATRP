#!/usr/bin/env python3
"""Fig: recall vs FP operating curves at the matched 2x budget, from frontier_all_<tag>.csv."""
import os, pandas as pd, matplotlib
matplotlib.use("pdf"); import matplotlib.pyplot as plt
H = os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PANELS = [("mutation_openpilot", "fisher", "openpilot mutants (28)"),
          ("mutation_transfuser", "fisher", "TransFuser mutants (28)"),
          ("real_tfpp", "fisher", "TF++ real (2 commits)"),
          ("real_pylot", "fisher_sep", "Pylot real (8, separated GT)")]
plt.rcParams.update({"font.size": 8, "axes.grid": True, "grid.alpha": .3, "pdf.fonttype": 42})
fig, axes = plt.subplots(1, 4, figsize=(8.4, 2.5), sharey=True)
CURVES = [("satrp_warm", "SA-TRP-warm ($\\gamma$)", "#1f77b4", "o", "-"), ("satrp_base", "SA-TRP-base ($\\gamma$)", "#2ca02c", "s", "-"),
          ("sprt", "SPRT ($\\alpha$)", "#9467bd", "^", "--"), ("apt", "APT (radius)", "#ff7f0e", "v", "--")]
POINTS = [("strap", "StRAP one-verdict", "#d62728", "X"), ("uniform", "uniform repetition", "#7f7f7f", "P"), ("rerun_maj", "$k$-rerun majority", "#8c564b", "D")]
for ax, (inst, tag, title) in zip(axes, PANELS):
    d = pd.read_csv(f"{H}/results/{inst}/frontier_all_{tag}.csv")
    for m, lab, col, mk, ls in CURVES:
        s = d[d.method == m].sort_values("fp_at_2x")
        ax.plot(s.fp_at_2x, s.recall_at_2x, ls=ls, marker=mk, ms=3, color=col, lw=1.3, label=lab)
    for m, lab, col, mk in POINTS:
        s = d[d.method == m]
        ax.plot([s.fp_at_2x.mean()], [s.recall_at_2x.mean()], mk, color=col, ms=6, label=lab)
    ax.plot([0], [1], "*", color="k", ms=8, label="oracle")
    ax.axvline(0.10, ls=":", color="k", lw=.8)
    ax.set_title(title, fontsize=7.5); ax.set_xlabel("FP rate @ 2$\\times$ budget"); ax.set_xlim(-0.01, 0.70); ax.set_ylim(0, 1.02)
axes[0].set_ylabel("recall @ 2$\\times$ budget")
axes[3].legend(loc="lower right", fontsize=5.5, ncol=1, framealpha=.9)
fig.tight_layout(); fig.savefig(f"{H}/results/fig_opcurve.pdf"); print("wrote results/fig_opcurve.pdf")
