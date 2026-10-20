# benchmark/ -- constructing the mutation benchmark

Campaign-time code, as it ran (see `docs/BENCHMARK.md` for the design and
`docs/CAMPAIGN.md` for how to run it on a cluster).

| file | role |
|---|---|
| `mutgen2.py` | the ten single-site AST mutation operators (AOR, ROR, COR, CRP, CSC, SGN, CLR, NEG, SDL, IDX); enumerates sites in a file and materializes one mutant per site |
| `coverage_lines.py` | collects the lines exercised by one run per scenario template (coverage.py) -> `covered_lines.json`; only covered sites are candidates |
| `pipeline.py` | `sample` (100 candidates per stack, stratified over files/operators, covered sites only), `materialize` (patched file / `team_code` copy per mutant, with the import-hook `file_map`), `screen-jobs`, `matrix-jobs` |
| `gen_jobs.py` | suite and baseline job files (`suite`, `base`); seed = `GS + sid*1000 + r` |
| `analyze_screen.py` | classifies the 100 screened candidates (stillborn / mass-fail / partial / silent) from trace distance to the same-seed baseline twin and outcomes |
| `select_mutants.py` | picks the 28 benchmark mutants per stack under per-operator / per-file quotas |
| `op_mutant_hook.py`, `hook/a2_op_mutant.pth` | run-time deployment of an openpilot mutant: a `MetaPathFinder` installed through a `.pth` file in the stack's virtualenv, driven by `OP_MUTANT_FILE="<module>=<path>;..."`; counts hook hits per process |
| `adapters/metadrive_openpilot/worker.py` | the openpilot/MetaDrive campaign worker (Proxima bridge): per-job mutant deployment, per-run isolated params, retries, Xvfb hygiene, result rows |
| `adapters/carla_transfuser/run_one.py`, `agent_host.py` | the TransFuser/CARLA host: `TF_TEAM_CODE_DIR` mutant deployment and the agent-md5 provenance line |
| `adapters/proxima_adapters_mutation.patch` | the same changes as a diff against the public Proxima adapters (base commit in `proxima_base_commit.txt`) |
| `slurm/op_campaign.slurm`, `slurm/tf_campaign.slurm` | SLURM array scripts (jobs-file slicing, `NTASK_OVERRIDE`, `DISPLAY_BASE`, retries) |
| `run_step1.sh`, `run_step2.sh`, `status.sh` | the two chained stages (sample -> screen; select -> matrix) and a progress counter |

Paths inside these scripts point at the cluster layout they ran on (`~/satrp_mutation/ads`,
`~/proxima`, `~/openpilot`); adapt them to your installation.
