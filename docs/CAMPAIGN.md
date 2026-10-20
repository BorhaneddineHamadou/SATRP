# Re-running the simulation campaigns

The campaigns ran on a SLURM cluster (NVIDIA A100/V100/P6000 nodes, Singularity
containers, no internet on compute nodes). Nothing below is needed to reproduce the paper's
numbers; it documents how the raw record was produced and what is required to extend it.

## Software

| component | version / source |
|---|---|
| openpilot | comma.ai openpilot, nested checkout pinned in the Proxima bridge; MetaDrive 0.4 with the Proxima scenario templates |
| TransFuser | github.com/autonomousvision/transfuser (`team_code_transfuser`, checkpoint `model_seed1`), CARLA 0.9.10.1 |
| harness | Proxima adapters (public: github.com/BorhaneddineHamadou/counterfactual-harm-oracle, `adapters/`), patched as in `benchmark/adapters/proxima_adapters_mutation.patch` (base commit in `proxima_base_commit.txt`) |
| mutation hook | `benchmark/hook/a2_op_mutant.pth` copied into the openpilot virtualenv `site-packages/` (edit the path inside to point at `benchmark/`) |

The patch adds to the workers: per-job mutant deployment (`job["mutant"]["file_map"]` ->
`OP_MUTANT_FILE`; `job["team_code_dir"]` -> `TF_TEAM_CODE_DIR`), hook-hit counting and the
agent-md5 provenance line, per-run isolated openpilot params (`PROXIMA_PARAMS_ISOLATE=1`),
and worker hygiene for day-long array tasks (Xvfb restart, child reaping).

## Steps (per stack)

```bash
cd benchmark
python3 coverage_lines.py <stack>                     # covered lines -> coverage/<stack>/covered_lines.json
python3 pipeline.py sample <stack> --covered 100      # candidates.json
python3 pipeline.py materialize <stack>               # store/<stack>/mutants/<mid>/...
python3 gen_jobs.py base <stack>                      # jobs_base.jsonl   (30 scenarios x r5..r39)
python3 pipeline.py screen-jobs <stack>               # jobs_screen.jsonl (100 candidates x 6 scenarios + twins)
sbatch --array=0-3 slurm/op_campaign.slurm            # (JOBS_FILE=..., OUTDIR=..., DISPLAY_BASE=...)  or tf_campaign.slurm
python3 analyze_screen.py <stack>                     # screen_classes.json
python3 select_mutants.py <stack> 28                  # selected.json
python3 pipeline.py matrix-jobs <stack> selected.json 12   # jobs_matrix.jsonl (and _ext for the second 12)
sbatch --array=0-35 slurm/op_campaign.slurm ...
```

`run_step1.sh` / `run_step2.sh` chain these; `status.sh` counts rows. The SLURM scripts
slice the jobs file across array tasks (`NTASK_OVERRIDE` keeps the stride on partial
resubmits; `DISPLAY_BASE` must differ between arrays sharing a node), and the workers skip
any job whose trace already exists, so a resubmitted array redoes only unfinished or failed
jobs. Results are appended per task (`<jobs>_task<k>.results.jsonl`); the adapters take the
last row per `job_id`.

The openpilot clean rerun (the one in the paper) used a single shuffled jobs file
(`jobs_clean.jsonl` = baseline r0-39 + matrix) with `PROXIMA_PARAMS_ISOLATE=1`, 36 tasks,
and two short tail passes (`--array=<slices>`, `PROXIMA_RETRIES=10`) for 13 jobs that had
failed to start five times.

## Cost

About 1,000 GPU-hours per mutation stack (12 concurrent slots, 3.5 days) and 450 for the
real-fault anchor.
