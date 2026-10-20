# The mutation benchmark: how it was built

Everything below is implemented in `benchmark/` and was executed on a SLURM cluster
(`docs/CAMPAIGN.md`). The outputs are the raw record on Zenodo (`docs/DATA.md`); the
instances in `data/derived/` are built from it by `satrp/adapter.py`.

## 1. Subject stacks and scenario suites

| | openpilot | TransFuser |
|---|---|---|
| stack | comma.ai openpilot (modular L2: modeld / radard / planner / controls), run on a software panda in MetaDrive | TransFuser (end-to-end camera+LiDAR imitation agent), CARLA 0.9.10.1 |
| harness | Proxima MetaDrive bridge (`benchmark/adapters/metadrive_openpilot/worker.py`) | Proxima CARLA host (`benchmark/adapters/carla_transfuser/run_one.py`, `agent_host.py`) |
| templates | ProxLeadDecel, ProxLeadStopped, ProxCutIn, ProxOncomingDrift, ProxCrossingTraffic | the same five |
| suite | 30 scenarios (`data/suites/<stack>/suite.json`), 6 per template, stratified on the nominal trigger rate | 30 scenarios, 4/4/8/8/6 per template |
| trigger | contact, or an out-of-lane / collision outcome | contact (`crash` column of the trace) |

A *scenario* is one template instantiated with fixed parameters (`params` in
`suite.json`); a *seed* fixes the simulator's random stream (`seed = GS + sid*1000 + r`,
`r` = run index, `GS` = 20260722 for openpilot and 20260806 for TransFuser, so even seeds
are even run indices and the budget-separated protocol can split on seed parity).

## 2. Mutable surface and operators

Only code that is *exercised* in the harness is mutated (line coverage collected with
`benchmark/coverage_lines.py` from one run per template): openpilot `selfdrive/controls/*`,
`selfdrive/controls/lib/*` and the model-output handling in `selfdrive/modeld/`; TransFuser
`team_code_transfuser/{submission_agent,model,config}.py`. Training code, data loaders and
unused backbones are excluded.

`benchmark/mutgen2.py` applies ten single-site AST operators (one site per mutant):

| op | effect | op | effect |
|---|---|---|---|
| AOR | arithmetic operator replacement | CSC | constant scaling (x0.5 / x2) |
| ROR | relational operator replacement | SGN | sign flip |
| COR | logical operator replacement | CLR | clamp / limiter removal |
| CRP | constant replacement | NEG | negate a boolean condition |
| SDL | statement deletion | IDX | index +-1 |

## 3. Candidates, screening, selection

1. `benchmark/pipeline.py sample --covered` draws 100 candidate sites per stack from the
   covered lines (`data/suites/<stack>/candidates.json`) and `materialize` writes each
   mutant as a patched copy of the touched file (openpilot: `mutants/<mid>/selfdrive/...`;
   TransFuser: a full `team_code_transfuser/` copy per mutant).
2. **Screen**: every candidate runs once on 6 scenarios (one per template plus one),
   alongside a baseline *twin* at the same seed. `benchmark/analyze_screen.py` classifies
   each candidate from the trace distance to its twin and its outcomes:
   `stillborn` (no engagement / crash at start), `mass-fail` (fails everywhere),
   `partial` (behaviour diverges from the twin on some scenarios), `silent` (indistinguishable
   from the twin). Classes and distances are in `data/suites/<stack>/screen_classes.json`.
3. **Select** (`benchmark/select_mutants.py`): 28 mutants per stack, stratified over
   operators and files with quotas, preferring `partial`, keeping a few `silent` and
   `mass-fail` so that the benchmark contains negligible, flaky and deterministic effects
   without the authors choosing effect sizes (`data/suites/<stack>/selected.json`).

## 4. Run-time deployment of a mutant

* **openpilot** runs its daemons as separate processes that import the stack's modules, so
  mutants are deployed with an import hook: `benchmark/hook/a2_op_mutant.pth` (installed in
  the stack's virtualenv `site-packages/`) loads `benchmark/op_mutant_hook.py`, a
  `MetaPathFinder` that redirects the modules named in `OP_MUTANT_FILE="<module>=<path>;..."`
  to the mutant's file (both the `openpilot.selfdrive...` and the bare `selfdrive...` names,
  because daemons are launched unprefixed). Every result row records `mutant_hook_hits`,
  the number of processes in which the hook fired; rows with zero hits are invalid.
* **TransFuser** loads its agent from a directory: the campaign host sets
  `TF_TEAM_CODE_DIR` to the mutant's `team_code_transfuser/` copy, and every run logs the
  md5 of the loaded agent file (`[team_code] ... md5=` line) as a deployment proof.

## 5. Executions

* Baseline: 40 runs per scenario (openpilot: `base_*` jobs in the clean rerun; TransFuser:
  the first five from the Proxima nominal campaign, `raw/transfuser/nominal`, plus `jobs_base`).
* Matrix: 28 mutants x 30 scenarios x 24 runs (`jobs_clean.jsonl` for openpilot, one shuffled
  file; `jobs_matrix.jsonl` + `jobs_matrix_ext.jsonl` for TransFuser, depth 12 + 12).
* Validity: a run is valid when the vehicle engaged (openpilot) / a trace was written
  (TransFuser) and the outcome is not an infrastructure failure (`no_engage`,
  `bridge_start_timeout`, `error*`, `run_timeout`); the worker retries such runs with a
  shifted seed (`attempts` in the row). Every openpilot run of the clean rerun executed with
  a private parameter directory (`params_isolated: true`): the first openpilot campaign was
  found to couple consecutive runs through openpilot's persisted calibration state and was
  discarded (its outcome pools are archived in `satrp_raw_openpilot_first_campaign.zip`).

## 6. Ground truth and instance files

`satrp/adapter.py` turns the raw record into `data/derived/mutation_<stack>/runs.jsonl`
(one record per valid run; see the README for the schema). Ground truth is *not* stored: it
is recomputed by `satrp/eval_altgt.py` from the full pool with the one-sided Fisher exact
test (alpha = 0.05) and a minimum effect of 0.15, under the full-pool and the
budget-separated (even seeds define truth, methods draw odd seeds) protocols. The
healthy-vs-healthy null calibration is in `satrp/phenomenon_stats.py`.
