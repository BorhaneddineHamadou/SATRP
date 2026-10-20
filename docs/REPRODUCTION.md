# Reproduction map and status

`bash tools/run_all.sh` runs everything below from `data/derived/` (CPU, ~1 h on 8 cores,
200 bootstrap reps as in the paper); `python3 tools/compare_with_paper.py` prints each
recomputed value next to the paper's. All bootstraps are seeded, so a re-run on the same
platform is expected to be bit-identical; across platforms, differences in the third
decimal can arise from BLAS summation order.

## Where each number comes from

| paper element | script | output |
|---|---|---|
| Abstract / Introduction: F1 gain over the one-verdict selector (+80 % TF, +9 % openpilot), false-positive ratios (16x, 6x), CIs | `satrp/extra_analysis_mut.py <instance>` | `results/extra_analysis_mut_<instance>.json` (`ci`) |
| Abstract: 48,336 runs; 173 certified regressions, a third flaky | `satrp/phenomenon_stats.py`; `realfaults/analysis/real_numbers.py` | `results/<instance>/phenomenon.json` (`runs`, `gt_full`), `results/realfaults/real_numbers.md` (2 x 21,360 + 5,616 runs; 118 + 55 certified cells, 44 + 14 flaky) |
| Study design, scenario suites and screening counts (stillborn / mass-fail / partial / silent; selected mutants by class, operator, file) | `satrp/phenomenon_stats.py <instance> <store>` | `phenomenon.json` (`screen`) ; `data/suites/<stack>/{screen_classes,selected}.json` |
| Study design, same-seed twins | `phenomenon_stats.py` with the raw screen store (`raw/openpilot_screen`, `raw/transfuser`) | `phenomenon.json` (`twins`) |
| Table "evaluation instances" (`tab:instances`) and Table "phenomenon" (`tab:phenomenon`) | `satrp/phenomenon_stats.py` | `phenomenon.json` (`base`, `cells_mut`, `gt_full`, `null`) |
| Ground truth: null calibration (parametric 5.6 +- 2.3 / 21.7 +- 4.5 cells, empirical odd-vs-even 0 / 2) | `satrp/phenomenon_stats.py` | `phenomenon.json` (`null`) |
| Ground-truth depth (52 vs 55 cells at depth 12 / 24, effects 0.77 / 0.36; openpilot 116 vs 118, 85 vs 119 separated) | `satrp/depth_decomp.py` (`DD_PAT`, `DD_GS`) | `results/logs/depth_<stack>.log` (`SEP GT cells`, blocks A-F) |
| Operating-point selection (held-out FP 0.043 at recall 0.873 TF; 0.100 at 0.487 openpilot) | `satrp/extra_analysis_mut.py` | `extra_analysis_mut_<instance>.json` (`opselect`) |
| Main table (`tab:main`): best F1-AUC, recall and FP at 2x, every method, both mutation instances | `satrp/run_altgt_mutation.py <instance>` (x8 knob levels) then `satrp/summarize_mutation_frontier.py fisher fisher_sep` | `results/<instance>/frontier_all_fisher_best.csv`; `results/mutation_all_methods_fisher.md` |
| Cross-instance table (`tab:rq2cross`) | `satrp/summarize_cross_instance.py` | `results/mutation_cross_instance.md` |
| Fig. operating curves (`fig:opcurve`) | `satrp/make_fig_opcurve.py` | `results/fig_opcurve.pdf` (from `frontier_all_fisher.csv` / `_sep.csv` of the four instances) |
| "Statistical uncertainty" paragraph: clustered CIs vs StRAP / SPRT / APT | `satrp/extra_analysis_mut.py` | `extra_analysis_mut_<instance>.json` (`ci`, `vs_sprt`, `vs_apt`) |
| RQ1 findings | `satrp/phenomenon_stats.py` | `phenomenon.json` |
| RQ2 findings (per-method F1-AUC, recall, FP; oracle fractions) | `run_altgt_mutation.py` | `frontier_all_fisher_best.csv` of `mutation_*`, `real_tfpp`, `real_pylot` (`_sep`) |
| RQ3 table (`tab:rq3prio`): APFDc and Top-5 precision | `run_altgt_mutation.py` | `frontier_all_fisher_best.csv` (`apfdc`, `topk5_prec`) |
| RQ3 mechanism: FP ratios with CIs | `satrp/extra_analysis_mut.py` | `extra_analysis_mut_<instance>.json` (`FPx`, `FPx_lo`, `FPx_hi`) |
| RQ4 ablation (PFS / EB-PFS vs SA-TRP base; SPRT / APT) | `run_altgt_mutation.py` | `frontier_all_fisher_best.csv` |
| RQ4 operating point (gamma sweep: FP, recall, F1-AUC per level; SPRT / APT collapse on openpilot) | `run_altgt_mutation.py` | `results/<instance>/frontier_all_fisher.csv` (one row per method x level) |
| RQ4 budget-separated protocol | `ALTGT_SEP=1 run_altgt_mutation.py <instance>` | `frontier_all_fisher_sep_best.csv`; `results/mutation_all_methods_fisher_sep.md` |
| RQ4 "Power" | `satrp/depth_decomp.py` | `results/logs/depth_<stack>.log` |
| RQ4 history table (`tab:rq5`): cold / base / warm and the history-depth sweep h = 2, 4, 8, 20, 40 | `run_altgt_mutation.py <instance> <h>` then `satrp/summarize_history_depth.py` | `frontier_all_fisher_h<h>_best.csv`; `results/mutation_history_depth.md` |
| RQ5 real-fault anchor: per-version rates, GT cells, null, mechanism tests (`tab:realanchor`) | `realfaults/analysis/real_numbers.py` (needs the raw archive) | `results/realfaults/real_numbers.md`, `cells.csv`, `all_runs.csv` (shipped copies in `results/paper/realfaults/`) |
| RQ5 method comparison on real faults (`tab:realmain`) | `run_altgt_mutation.py real_pylot` / `real_tfpp` / `real_tfpp_straight` / `real_pylot_T2` (+ `ALTGT_SEP=1`) | `results/real_*/frontier_all_fisher{,_sep}_best.csv` |
| Threats: Pylot port collisions, openpilot first campaign discarded | documented in `docs/CAMPAIGN.md`, `docs/BENCHMARK.md` sec. 5; outcome pools of the discarded campaign in `satrp_raw_openpilot_first_campaign.zip` | -- |

Supporting plots (not in the paper): `satrp/eval_satrp.py`, `eval_satrp_frontier.py`,
`satrp_roc.py` write `results/<instance>/satrp_{summary,curves,frontier,roc}.*`.

## Rebuilding the instances from the raw record

```bash
bash tools/fetch_data.sh                       # Zenodo archives -> raw/
python3 satrp/adapter.py                       # mutation_openpilot, mutation_transfuser -> data/derived/*/runs.rebuilt.jsonl + set check
python3 realfaults/analysis/real_numbers.py    # real_* instances (+ results/realfaults/*)
```

The real-fault instances are reproduced bit for bit. The two mutation instances are
reproduced as the same *set* of 21,360 records each; their line order differs from the
shipped files because the campaign-time build iterated result files in filesystem order.
The harness consumes each cell's runs in file order as its common-random-number draw
stream, so a re-ordered file is a different, equally valid realization of the budgeted
draws (best F1-AUC moves by about 0.01-0.02; the ranking is unaffected). The shipped
`runs.jsonl` files are therefore the paper's exact inputs, and `adapter.py` writes the
rebuild next to them as `runs.rebuilt.jsonl` unless `--overwrite` is given.

## Reproduction status

Full re-run of `tools/run_all.sh` on 2026-10-20 (Python 3.10.19, numpy 2.2.6, pandas 2.3.3,
scipy 1.15.3; 200 bootstrap reps, 100 for the depth decomposition as in the paper), compared
with `results/paper/`:

| item | status |
|---|---|
| 40 frontier files (`frontier_all_*{,_best}.csv`, six instances, both protocols, four history depths) | byte-identical |
| summary tables (`mutation_all_methods_fisher.md`, `_fisher_sep.md`, `mutation_history_depth.md`, `mutation_cross_instance.md`) | identical |
| clustered bootstrap CIs and held-out gamma (`extra_analysis_mut_*.json`) | identical to 1e-16 (two standard-deviation fields differ in the last floating-point digit) |
| phenomenon statistics (`phenomenon.json`, both instances) | identical; the same-seed twin counts require the raw screening stores (`raw/openpilot_screen`, `raw/transfuser`), otherwise that row is empty |
| ground-truth-depth decomposition (`depth_*.log`) | identical |
| operating-curve figure (`fig_opcurve.pdf`) | identical |
| real-fault analysis (`real_numbers.md`, `cells.csv`, `all_runs.csv`) and the four real-fault instance files, rebuilt from the raw archive | byte-identical |
| mutation instance files rebuilt from the raw archive | same record set (21,360 each); line order differs, see above |

`python3 tools/compare_with_paper.py` ends with `all best-F1-AUC values within tolerance`.

