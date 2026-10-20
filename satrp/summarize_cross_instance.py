#!/usr/bin/env python3
"""Cross-instance robustness table (paper: tab:rq2cross): mean and worst-case best F1-AUC
over the four instances -- openpilot and TransFuser mutants (full-pool Fisher GT), TF++ real
(full-pool), Pylot real (budget-separated GT, see RQ5). Writes results/mutation_cross_instance.md."""
import os, pandas as pd
ROOT = os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = [("mutation_openpilot", "fisher"), ("mutation_transfuser", "fisher"), ("real_tfpp", "fisher"), ("real_pylot", "fisher_sep")]
LAB = {"strap": "STRAP one-verdict", "uniform": "Uniform round-robin", "rerun_maj": "k-rerun-majority", "pfs": "PFS Beta (flat)",
       "eb_warm": "EB-PFS (warm prior)", "sprt": "SPRT (Wald)", "apt": "Thresholding bandit (APT)", "satrp_base": "SA-TRP base", "satrp_warm": "SA-TRP warm"}
D = {i: pd.read_csv(f"{ROOT}/results/{i}/frontier_all_{t}_best.csv").set_index("method") for i, t in SRC}
lines = ["### Cross-instance robustness: best F1-AUC per instance, mean and worst case (min)", "",
         "| method | " + " | ".join(i for i, _ in SRC) + " | mean | min |", "|---|" + "---|" * (len(SRC) + 2)]
for m, lab in LAB.items():
    v = [D[i].loc[m, "best_f1_auc"] for i, _ in SRC]
    lines.append(f"| {lab} | " + " | ".join(f"{x:.3f}" for x in v) + f" | {sum(v)/len(v):.3f} | {min(v):.3f} |")
txt = "\n".join(lines); print(txt)
open(f"{ROOT}/results/mutation_cross_instance.md", "w").write(txt + "\n")
