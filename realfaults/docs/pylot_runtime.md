# Pylot leaderboard runtime (real-fault block, built 2026-10-13)

Files (all under `~/satrp_real/pylot/`): `lb_worker.py` (host python3 3.10, stdlib), `gen_jobs_lb.py`, `pylot_lb_campaign.slurm`,
`jobs_lb_{smoke_video,base,versions}.jsonl`, results in `lb_results_<tag>/`. Reused as-is: `~/satrp_real/tfpp/lb_run_eval.py`
(runpy evaluator + md5 proof lines), `~/satrp_real/tools/{chasecam.py,encode_videos.sh}`. Routes = carla_garage's shipped leaderboard-1.0
Town01 per-class files (`tfpp/carla_garage/leaderboard/data/training/{routes,scenarios}/s<N>/Town01_Scenario<N>.{xml,json}`, s1 s3 s4 s7 s8 s9);
the worker extracts a one-route XML per job. Nothing hand-written.

## How a run executes
1. Slurm task: CARLA 0.9.10.1 server restart loop from `~/sifs/carla09101.sif` (libnvidia-gpucomp bind, port probe
   `ss -ltn` + `pgrep`, several tasks per node), TM port = PORT+20, then `python3 lb_worker.py JOBS TASK NTASK`,
   then `encode_videos.sh` when `LB_VIDEO_DIR` is set. `--mem=48G --cpus-per-task=12`, gpuv100/gpup6000/classicgpu, `--exclude=node27`.
2. Worker (host): per job, run dir = `dirname(results_out)/<job_id>/` holding `<job_id>.xml` (one route), `<job_id>.pylot.conf`,
   Pylot's `.pylot.log/.csv/.profile.json`. One attempt = fresh
   `singularity exec --nv --cleanenv --bind $HOME --bind <versions/<vid>/pylot>:/workspace/team_code/pylot --pwd <run dir> ~/sifs/pylot_challenge.sif env ... python3 ~/satrp_real/tfpp/lb_run_eval.py /workspace/leaderboard/leaderboard/leaderboard_evaluator.py --routes --scenarios --repetitions=1 --track=MAP --checkpoint=<results_out> --agent=/workspace/team_code/pylot/simulation/challenge/ERDOSAgent.py --agent-config=<per-run conf> --debug=0 --port --trafficManagerPort --trafficManagerSeed=<seed> --timeout=600`
   (no `--resume`: argparse type=bool). stdout+stderr -> `<results_out>.log`. Timeout `LB_JOB_TIMEOUT` (default 3000 s; TF models
   load 1-2 min); on stall / rc!=0 / missing checkpoint: pkill the server by port, sleep 60, retry once (first log kept as `.log.attempt1`).
   Env passed into the image: `PROOF_MODULES=pylot.planning.{waypoints,world,cost_functions,planning_operator,behavior_planning_operator}`,
   `PYLOT_DIFFTRACE=1`, `PYTHONUNBUFFERED=1`, ROUTES/SCENARIOS/TEAM_AGENT/TEAM_CONFIG/CHECKPOINT_ENDPOINT, LEADERBOARD_ROOT etc.
3. Row -> `<results_out>.row.json` + `<jobs>_task<N>.results.jsonl` (skip when `.row.json` exists). TF++ schema (outcome, status,
   trigger, blocked, timeout, score_*, infractions, durations) plus vid, status_version, scenario_class, conf_path, proof fields below.

## The erdos / image_userlib fix
The image's `erdos` package and the leaderboard's deps (py_trees, xmlschema, dictor, tabulate, ...) were installed under `/root`
(unreadable). Fix: `--cleanenv` + `PYTHONPATH=~/satrp_real/pylot/image_userlib:/workspace/erdos/build/lib.linux-x86_64-3.7:<image default PYTHONPATH>`
(constant `PYTHONPATH` in lb_worker.py). `image_userlib` must NEVER get numpy (TF 1.15 needs the image's numpy 1.16.6).
Verified on the login node 2026-10-13: pylot, ERDOSAgent, leaderboard_evaluator, carla, cv2, numpy, erdos all import with the bind mount.

## Version selection + per-run conf
Only the package is bind-mounted (`versions/<vid>/pylot` -> `/workspace/team_code/pylot`), so `dependencies/models` stay from the image.
The agent config is a per-run copy of the VERSION tree's `pylot/simulation/challenge/challenge.conf` (v_speed7 differs only there:
`--target_speed=7`) with `--simulator_host/--simulator_port/--log_file_name/--csv_log_file_name/--profile_file_name` stripped and
re-appended (`localhost`, task port, absolute run-dir paths). Conf = default perception path (`conf/challenge_default.conf` == base conf).

## Deployment proof (row fields)
`proof{file: expect_md5 (versions.json md5_version), host_md5 (deployed tree), seen_file, seen_md5, ok}` for the version's changed files
and the 5 PROOF modules; `proof_ok` = every changed file (all 5 for base) seen from `/workspace/team_code/pylot/...` with md5 == host
md5 == md5_version, AND `conf_ok` (v_speed7: per-run conf has `--target_speed=7`), AND `difftrace_lines>0` when `difftrace_required`.
`difftrace_lines` = count of `[difftrace <vid>]` lines in the log. CAVEAT: the version trees are NOT difftrace-instrumented (the
`<vid>.difftrace.patch` files are separate; md5_version is the un-instrumented md5), so `difftrace_instrumented=False`,
`difftrace_required=False` and difftrace_lines will be 0 for now. To enforce it: apply the difftrace patch to a COPY of the tree, point
`job.pylot_dir` at it (the worker then checks seen md5 == host md5 of that tree and skips the md5_version equality).

## Video sidecar
`LB_VIDEO_DIR` set -> right after the evaluator starts, `chasecam.py <LB_VIDEO_DIR>/<job_id> --port P --wait <timeout>` runs inside the
same image (`--cleanenv --bind $HOME`, same PYTHONPATH; carla egg + cv2 + numpy are in the image), log `<job_id>.chasecam.log`;
waited 30 s after the evaluator exits, then terminate/kill. The slurm epilogue encodes `<LB_VIDEO_DIR>/../videos/<job_id>.mp4`.

## Submitting / resubmitting
Smoke (54 jobs, 3 tasks): `cd ~/satrp_real/pylot && mkdir -p lb_smoke_video/frames logs && sbatch --export=ALL,JOBS_FILE=$PWD/jobs_lb_smoke_video.jsonl,LB_VIDEO_DIR=$PWD/lb_smoke_video/frames --array=0-2 --time=08:00:00 --job-name=satrp_pylot_lbvsmoke pylot_lb_campaign.slurm`
Campaign: `JOBS_FILE=$PWD/jobs_lb_base.jsonl sbatch --array=0-7 pylot_lb_campaign.slurm` (same for jobs_lb_versions.jsonl). Finished
jobs are skipped via `.row.json`; a PARTIAL resubmit of some tasks must set `NTASK_OVERRIDE=<original array size>` (stride).
Regenerate jobs with `python3 gen_jobs_lb.py` (asserts tree md5s == versions.json). Seeds: TF++ formula + 500000.

## What to check in the smoke logs
`logs/pylot_lb_<A>_<a>.out`: port line, `[lb_worker] <job>: ok status=Completed ... proof_ok=True difftrace=0`.
`lb_results_smoke_video/<job>.json.log`: the `singularity exec` cmd, no `ModuleNotFoundError`, Pylot's TF model load, leaderboard
"Registering the route statistics", the 5 `[team_code] pylot.planning.<m> from /workspace/team_code/pylot/... md5=` lines,
`[lb_eval] evaluator finished rc=0`. `logs/server_lb_<A>_<a>.log`: server not restarting mid-route. `lb_smoke_video/frames/<job>.chasecam.log`:
`hero id=` found and `frames written > 0`; `lb_smoke_video/videos/*.mp4` after the task ends. Row sanity: `score_route` > 0, `duration_game` plausible, v_speed7 rows `conf_target_speed == "7"`, GPU memory (two TF sessions at 0.4 each + server) not OOM.

## Instrumented trees (2026-10-13 evening)
`versions_dt/<vid>/` = `versions/<vid>/` + its `<vid>.difftrace.patch` (base carries ALL 8 traces, all apply cleanly,
every instrumented file py-compiles). `gen_jobs_lb.py` deploys `versions_dt` by default (DIFFTRACE_TREES=0 → pristine
`versions/`). With an instrumented tree the worker requires seen md5 == host md5 of the deployed file and
`difftrace_lines > 0` for versions with status "ready"; `versions.json md5_version` (pristine md5) is waived.

## 2026-10-14 — erdos dataflow port race (fixed)
`ERDOSAgent.py` started the dataflow with `erdos.run_async()` = default `start_port=9000`. The 11 erdos node processes bind
127.0.0.1:9000–9021 only while they shake hands; two Pylot runs that *start* within the same few seconds on the same host collide
(`Address already in use` in one, `early eof` in the other, then an endless `could not connect ... retrying` loop until the worker's
stall limit). Smoke 765378 lost `v_overtake s3/s4` this way (tasks 1+2 in lockstep on node30, twice). Reproduced on the login node
with a toy 11-node graph (same port: 2/2 hang; distinct ports: 2/2 fine).
Fix (harness-only, identical in every version tree, proof md5s untouched): `ERDOSAgent.py` reads `ERDOS_START_PORT`
(default 9000); `lb_worker.py` assigns each attempt a free 32-port block `20000 + ((SLURM_JOB_ID + task) % 300) * 32`
(probed with `ss -ltn`) and forwards it through the `--cleanenv` image env. Backups: `*.bak_2026-10-14_erdosport`.
Memory note: a healthy Pylot leaderboard run peaks at ~12.3 GB RSS (sacct 765378_0); the 48 GB request in
`pylot_lb_campaign.slurm` prevents two tasks from sharing a node with free GPUs — 24 GB is enough.
