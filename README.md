# SA-TRP: Stochasticity-Aware Test Reduction and Prioritization for ADS

Replication package for **"Stochasticity-Aware Test Reduction and Prioritization for
Autonomous Driving Systems"** (ICST 2027 submission).

The paper (i) shows that code-level regressions of a driving stack are *stochastic* (a
genuine regression surfaces in only a fraction of runs), (ii) proposes **SA-TRP**, which
selects and orders scenarios by allocating a run budget over repeated executions with
Beta-Bernoulli posteriors for the version under test and the baseline, and (iii) builds the
first benchmark of version-introduced ADS regressions with repeated executions: 56
mutation-seeded versions of two driving stacks (**openpilot** in MetaDrive, **TransFuser**
in CARLA) on 1,680 (version, scenario) cells under 24 seeds each against a 40-seed baseline
pool, anchored by ten reverted historical fixes of two further stacks (**Pylot**, **TF++**)
on CARLA Leaderboard routes. 48,336 recorded runs in all.

This repository holds the method, the evaluation harness with its ten baselines, the
benchmark construction tooling (mutation operators, run-time mutant deployment, screening,
campaign workers), the real-fault harnesses, the six evaluation instances the paper was
computed from, and one command that recomputes every number in the paper on a CPU. The raw
record (outcome pools, traces, mutant sources, Leaderboard records, version trees) is on
Zenodo (see `docs/DATA.md`); it is needed only to rebuild the instances from scratch or to
re-run the simulations.

## Quick start

```bash
pip install -r requirements.txt            # numpy, pandas, scipy, matplotlib, joblib (Python >= 3.10)
python3 tests/test_smoke.py                # 30 s: instances load, label rule and harness run
QUICK=1 bash tools/run_all.sh              # ~10 min smoke of the whole pipeline (10 bootstrap reps)
bash tools/run_all.sh                      # ~1 h on 8 cores: every table and figure, 200 bootstrap reps
python3 tools/compare_with_paper.py        # side-by-side with the values the paper was typeset from
```

Outputs land in `results/<instance>/` and `results/*.md`; `results/paper/` holds the values
the paper was typeset from (never overwritten). `docs/REPRODUCTION.md` maps every table,
figure and in-text number to the script and output file that produces it, and records the
reproduction status.

## Layout

```
satrp/            method + evaluation harness (pure Python, offline)
  eval_satrp.py       SA-TRP (cold/base/warm) and the ten baselines on a common budgeted draw stream; F1-AUC, recall/FP at 2x, APFDc, Top-K
  eval_altgt.py       ground truth: one-sided Fisher exact test vs the baseline pool (full-pool and budget-separated protocols)
  run_altgt_mutation.py   one instance x one GT protocol x the 8-level knob sweep  -> results/<instance>/frontier_all_<tag>{,_best}.csv
  extra_analysis_mut.py   clustered bootstrap CIs (by mutant) + held-out gamma selection
  phenomenon_stats.py     RQ1 statistics (cell spectrum, self-disagreement, null calibration, screen classes, same-seed twins)
  depth_decomp.py         ground-truth-depth decomposition (RQ4 "Power")
  summarize_*.py, make_fig_opcurve.py, satrp_roc.py, eval_satrp_frontier.py   tables and figures
  adapter.py          builds data/derived/mutation_* from the raw record (Zenodo)
benchmark/        benchmark construction: mutation operators (mutgen2.py), import-hook deployment (op_mutant_hook.py),
                  candidate sampling/screening/selection (pipeline.py, analyze_screen.py, select_mutants.py), campaign
                  workers (adapters/), SLURM scripts   -> docs/BENCHMARK.md, docs/CAMPAIGN.md
realfaults/       Pylot and TF++ harnesses, version patches, and the analysis that builds the real-fault instances -> docs/REALFAULTS.md
data/derived/     the six evaluation instances (runs.jsonl), exactly as the paper used them
data/suites/      scenario suites, candidate mutants, screen classes and the selected 28 mutants per stack
results/paper/    the paper's result files (frontier CSVs, phenomenon.json, CIs, tables, figure, real-fault tables)
docs/             REPRODUCTION.md (number -> script map + status), BENCHMARK.md, CAMPAIGN.md, REALFAULTS.md, DATA.md
tools/            run_all.sh, compare_with_paper.py, fetch_data.sh (Zenodo), pack_zenodo.sh (authors)
tests/            smoke tests
```

## The evaluation instances

| instance | stack / simulator | versions | cells | runs per cell (baseline) | records |
|---|---|---|---|---|---|
| `mutation_openpilot` | openpilot 0.9 (modular, L2) / MetaDrive | 28 mutants | 840 | 24 (40) | 21,360 |
| `mutation_transfuser` | TransFuser (end-to-end) / CARLA 0.9.10.1 | 28 mutants | 840 | 24 (40) | 21,360 |
| `real_pylot` | Pylot (modular) / CARLA Leaderboard 1.0 | 8 reverted fixes | 96 | 24 (40) | 2,784 |
| `real_pylot_T2` | same, "any-failure" trigger (sensitivity) | 8 | 96 | 24 (40) | 2,784 |
| `real_tfpp` | TF++ / CARLA Leaderboard 1.0 (30 scenarios + 12 routes) | 2 | 84 | 24 (40) | 3,696 |
| `real_tfpp_straight` | TF++ / the 30-scenario block only | 2 | 60 | 24 (40) | 2,640 |

Record schema (`data/derived/<instance>/runs.jsonl`, one line per valid run):
`commit` (`BASE` or `MUT:<id>` / version id), `scenario` (`<template>#<sid>`), `seed`,
`outcome` (`collision` = the run triggered, `completed` otherwise), `is_baseline`,
`fault_module`, `system`, `platform`. Methods never see the trigger probabilities; they
draw runs from these pools under a budget, and ground truth is computed from the full pool
(`eval_altgt.py`).

## Environment variables

`SATRP_ROOT` (repository root; default: inferred), `SATRP_RAW` (unpacked Zenodo archive;
default `raw/`), `NB` / `SATRP_NBOOT` (bootstrap reps, 200 in the paper), `ALTGT_SEP=1`
(budget-separated ground truth), `SATRP_DELTA` (0.15), `SATRP_GAMMA`, `SATRP_ETA`,
`SATRP_KAPPA`, `SATRP_KP`, `SATRP_MCAL` (method knobs, paper defaults in `satrp/eval_satrp.py`).

## License

MIT (see `LICENSE`). The driving stacks, simulators and checkpoints are third-party
software under their own licenses and are not redistributed here.
