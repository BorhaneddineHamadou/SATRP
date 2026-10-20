#!/usr/bin/env python3
"""Baseline-history depth sweep (Fisher GT): best F1-AUC per method vs the number of baseline
runs/scenario (h) available to baseline-aware methods. Reads results/mutation_<stack>/
frontier_all_fisher_h<h>_best.csv (+ frontier_all_fisher_best.csv as h=40 = full pool).
Writes results/mutation_history_depth.md"""
import os, pandas as pd
ROOT = os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HS = [2, 4, 8, 20, 40]
SHOW = ["uniform", "strap", "pfs", "eb_warm", "twoprop", "sprt", "apt", "satrp_cold", "satrp_base", "satrp_warm"]
LAB = {"uniform": "Uniform (no q)", "strap": "STRAP (no q)", "pfs": "PFS flat (no q)", "eb_warm": "EB-PFS",
       "twoprop": "Two-prop+BH", "sprt": "SPRT", "apt": "APT", "satrp_cold": "SA-TRP cold (pays for q)",
       "satrp_base": "SA-TRP base", "satrp_warm": "SA-TRP warm"}
out = []
for st in ["openpilot", "transfuser"]:
    d = {}
    for h in HS:
        p = f"{ROOT}/results/mutation_{st}/frontier_all_fisher{'' if h == 40 else f'_h{h}'}_best.csv"
        if os.path.exists(p): d[h] = pd.read_csv(p).set_index("method")
    if not d: continue
    hs = [h for h in HS if h in d]
    for metric, name in [("best_f1_auc", "F1-AUC"), ("fp_at_2x", "FP@2x")]:
        out += [f"### {st}: best {name} vs baseline-history depth h (runs/scenario), Fisher GT, NBOOT=200", "",
                "| method | " + " | ".join(f"h={h}" for h in hs) + " |", "|---|" + "---|" * len(hs)]
        for m in SHOW:
            vals = [f"{d[h].loc[m, metric]:.3f}" if m in d[h].index else "–" for h in hs]
            out.append(f"| {LAB[m]} | " + " | ".join(vals) + " |")
        out.append("")
txt = "\n".join(out); print(txt)
open(f"{ROOT}/results/mutation_history_depth.md", "w").write(txt + "\n")
