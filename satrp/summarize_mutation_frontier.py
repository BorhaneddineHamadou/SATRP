#!/usr/bin/env python3
"""Assemble the all-baselines summary table for the mutation instances from
results/mutation_<stack>/frontier_all_<gt>_best.csv. Prints markdown + writes
results/mutation_all_methods_<gt>.md"""
import os, sys, pandas as pd
ROOT = os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAB = {"strap":"STRAP one-verdict","random":"Random","uniform":"Uniform round-robin",
       "rerun_any":"Rerun-until-pass","rerun_maj":"k-rerun-majority","pfs":"PFS Beta (flat)",
       "eb_warm":"EB-PFS (warm prior)","twoprop":"Two-prop+BH","sprt":"SPRT (Wald)",
       "apt":"Thresholding bandit (APT)","satrp_cold":"SA-TRP cold","satrp_base":"SA-TRP base",
       "satrp_warm":"SA-TRP warm","oracle":"Oracle"}
for gt in sys.argv[1:] or ["split", "sig"]:
    d = {}
    for st in ["openpilot", "transfuser"]:
        p = f"{ROOT}/results/mutation_{st}/frontier_all_{gt}_best.csv"
        if os.path.exists(p): d[st] = pd.read_csv(p).set_index("method")
    if not d: continue
    lines = [f"### Mutation benchmark, GT={gt}, each method at its own best knob (F1-AUC), NBOOT=200", "",
             "| method | op F1-AUC | op recall" + ("@2x" if gt=="fisher" else "") + " | op FP@2x | op Top5-prec | TF F1-AUC | TF recall" + ("@2x" if gt=="fisher" else "") + " | TF FP@2x | TF Top5-prec | worst-case F1 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for m in LAB:
        row = [LAB[m]]; wc = []
        for st in ["openpilot", "transfuser"]:
            if st in d and m in d[st].index:
                r = d[st].loc[m]; wc.append(r.best_f1_auc)
                row += [f"{r.best_f1_auc:.3f} (γ/α {r.at_gamma:.2f}/{r.at_alpha:.2f})" if m in ("satrp_cold","satrp_base","satrp_warm","pfs","eb_warm","sprt","twoprop","apt") else f"{r.best_f1_auc:.3f}",
                        f"{(r.recall_auc if 'recall_auc' in r.index else r.recall_at_2x):.3f}", f"{r.fp_at_2x:.3f}", f"{r.topk5_prec:.2f}" if pd.notna(r.topk5_prec) else "–"]
            else: row += ["–"]*4
        row.append(f"{min(wc):.3f}" if wc else "–")
        lines.append("| " + " | ".join(row) + " |")
    txt = "\n".join(lines); print(txt); print()
    open(f"{ROOT}/results/mutation_all_methods_{gt}.md", "w").write(txt + "\n")
