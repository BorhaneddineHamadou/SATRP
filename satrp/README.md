# satrp/ -- the method and the evaluation harness

Pure Python (numpy, pandas, scipy, matplotlib). Offline: every script reads an instance
file `data/derived/<instance>/runs.jsonl` and writes under `results/<instance>/`.

## SA-TRP (in `eval_satrp.py`, `simulate_satrp`)

Per scenario `s`, two Beta-Bernoulli posteriors: the trigger probability of the version
under test `p_s` and of the baseline `q_s`. A scenario is *confirmed* as a regression when
`P[p_s - q_s >= delta] >= gamma` (delta = 0.15, the effect size of the ground-truth rule;
gamma = the confidence threshold, the method's precision knob), and *abandoned* when that
probability falls below `eta` after at least `N_MIN` runs. Each run of the budget goes to the
scenario drawn by baseline-aware Thompson sampling: sample `p_s`, `q_s` from the posteriors
and pick the unconfirmed scenario with the largest sampled `p_s - q_s`. The confirmed set is
the reduced suite; the confirmation order (then posterior rank) is the prioritization.

History axis: `satrp_cold` estimates `q_s` online from its own budget (`M_CAL` calibration
runs, charged); `satrp_base` has the amortized baseline pool (40 runs per scenario, not
charged); `satrp_warm` additionally sharpens the prior (`KAPPA`).

## Baselines (same budget, same draw stream)

`strap` (StRAP-style one-verdict selection), `random`, `uniform` (round-robin repetition),
`rerun_any` (rerun-until-pass), `rerun_maj` (k-rerun majority), `pfs` (flat Beta,
baseline-unaware), `eb_warm` (empirical-Bayes PFS), `twoprop` (two-proportion z-test with
Benjamini-Hochberg), `sprt` (Wald's SPRT per scenario), `apt` (thresholding bandit), and
`oracle` (knows every `p_s`, `q_s`). Thresholded methods are swept over their own knob
(gamma for SA-TRP/PFS, alpha for SPRT/two-prop, confidence radius for APT) and reported at
their best F1-AUC.

## Metrics

Recall, false-positive rate and F1 against the ground truth at a budget of `B` runs per
scenario; F1-AUC over the budget sweep; recall and FP at the matched `2x` budget; APFDc
and Top-K precision/recall of the prioritized list (`SATRP_TOPK=1,3,5`).

## Scripts

| script | what it produces |
|---|---|
| `run_altgt_mutation.py <instance> [h]` (`ALTGT_SEP=1`) | `results/<instance>/frontier_all_fisher[_h<h>][_sep]{,_best}.csv` -- all methods, all metrics, 8 knob levels; Fisher ground truth from the full pool or the separated protocol; `h` restricts the amortized baseline history |
| `eval_altgt.py` | the ground-truth rule and the driver `run_altgt(...)` used above |
| `extra_analysis_mut.py <instance>` | `results/extra_analysis_mut_<instance>.json`: clustered (by mutant) bootstrap CIs of the F1 gain and FP ratio vs StRAP, SPRT and APT at the 2x budget; held-out gamma selection to a 0.10 false-alarm budget |
| `phenomenon_stats.py <instance> [store]` | `results/<instance>/phenomenon.json` + a markdown summary (RQ1 table, instance table, null calibration) |
| `depth_decomp.py` (`DD_PAT`, `DD_GS`) | ground truth at depth 12 vs 24 and the methods' scores against each (RQ4 "Power") |
| `summarize_mutation_frontier.py fisher fisher_sep` | `results/mutation_all_methods_<gt>.md` (the main table) |
| `summarize_history_depth.py` | `results/mutation_history_depth.md` (history-depth table) |
| `make_fig_opcurve.py` | `results/fig_opcurve.pdf` (recall vs FP operating curves, four panels) |
| `eval_satrp.py`, `eval_satrp_frontier.py`, `satrp_roc.py` (`INJECT_GLOB`, `INJECT_OUT`) | SA-TRP budget curves, gamma frontier and ROC for one instance (supporting plots) |
| `adapter.py [openpilot\|transfuser] [--overwrite]` | rebuild `data/derived/mutation_*` from the raw record (`SATRP_RAW`) |
