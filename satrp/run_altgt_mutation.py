#!/usr/bin/env python3
"""Decoupled Fisher-exact GT evaluation for the ICST mutation instances.

Same fair protocol as run_frontier_mutation.py (every method swept over ITS OWN
lenient->strict knob ladder: gamma for satrp_*/pfs/eb_warm, alpha=beta for
sprt/twoprop, radius scale for apt) but the ground truth is eval_altgt.run_altgt's
"fisher" mode: a cell is a regression iff a one-sided Fisher exact test on the FULL
pool rejects at ALTGT_ALPHA (default 0.05) AND p_hat - q_hat >= DELTA.  Different
machinery from SA-TRP's Beta posterior, so the sig-GT circularity worry is answered.

  usage: run_altgt_mutation.py <instance>      (env NB = bootstrap reps, ALTGT_ALPHA)
Outputs results/<instance>/frontier_all_{TAG}.csv and frontier_all_{TAG}_best.csv.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import eval_satrp as E
import eval_altgt as A

ROOT = os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
inst = sys.argv[1]
HIST = int(sys.argv[2]) if len(sys.argv) > 2 else None   # baseline-history depth (runs/scenario); None = full pool
SEP = os.environ.get("ALTGT_SEP", "0") == "1"                 # budget-separated GT (GT seed half vs draw seed half)
TAG = ("fisher" if HIST is None else f"fisher_h{HIST}") + ("_sep" if SEP else "")
pattern = f"{ROOT}/data/derived/{inst}/runs.jsonl"
out = f"{ROOT}/results/{inst}"; os.makedirs(out, exist_ok=True)
GAMMA = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
ALPHA = [0.40, 0.30, 0.20, 0.12, 0.08, 0.05, 0.02, 0.01]
APT_C = [0.30, 0.50, 0.70, 0.90, 1.10, 1.30, 1.60, 2.00]
E.NBOOT = int(os.environ.get("NB", "200"))
ORDER = ["strap", "random", "uniform", "rerun_any", "rerun_maj", "pfs", "eb_warm", "twoprop",
         "sprt", "apt", "satrp_cold", "satrp_base", "satrp_warm", "oracle"]
rows, meta = [], None
for i in range(len(GAMMA)):
    E.ALPHA = ALPHA[i]; E.BETA = ALPHA[i]; E.APT_C = APT_C[i]
    r = A.run_altgt(pattern, "fisher", GAMMA[i], hist_n=HIST, separate=SEP)
    if r is None or r.get("_meta", {}).get("too_few"):
        print("no data / too few faults", r); sys.exit(1)
    meta = r["_meta"]
    for m in ORDER:
        if m not in r: continue
        row = {"level": i, "gamma": GAMMA[i], "alpha": ALPHA[i], "apt_c": APT_C[i], "method": m}
        row.update(r[m]); rows.append(row)
    print(f"[{inst}/{TAG}] level {i} done (gamma={GAMMA[i]} alpha={ALPHA[i]} apt_c={APT_C[i]}) "
          f"faults={meta['n_faults']} flaky={meta['n_flaky']}", flush=True)
fr = pd.DataFrame(rows)
fr.to_csv(f"{out}/frontier_all_{TAG}.csv", index=False)
best = []
for m in ORDER:
    sub = fr[fr.method == m]
    if sub.empty: continue
    ib = sub["f1_auc"].idxmax()
    best.append(dict(method=m, best_f1_auc=sub.loc[ib, "f1_auc"], at_gamma=sub.loc[ib, "gamma"],
                     at_alpha=sub.loc[ib, "alpha"], at_apt_c=sub.loc[ib, "apt_c"],
                     fp_at_2x=sub.loc[ib, "fp_at_2x"], recall_at_2x=sub.loc[ib, "recall_at_2x"],
                     f1_at_2x=sub.loc[ib, "f1_at_2x"], apfdc=sub.loc[ib, "apfdc"],
                     topk5_prec=sub.loc[ib, "topk5_prec"], topk5_rec=sub.loc[ib, "topk5_rec"]))
pd.DataFrame(best).to_csv(f"{out}/frontier_all_{TAG}_best.csv", index=False)
print(f"META faults={meta['n_faults']} flaky={meta['n_flaky']} configs={meta['configs']} scen={meta['scen']} "
      f"ALPHA={A.ALPHA} DELTA={E.DELTA} NBOOT={E.NBOOT}")
print(pd.DataFrame(best).to_string(index=False, float_format=lambda x: f"{x:.3f}"))
