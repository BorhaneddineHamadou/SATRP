# TransFuser++ (carla_garage, leaderboard_1) in the Proxima CARLA host — Tier-1 setup

Date: 2026-10-13. Working dir: `~/satrp_real/` (`tfpp/`, `logs/`, `docs/`).
Nothing under `~/satrp_mutation` was modified. Host edits are backward-compatible
additions to `~/proxima/adapters/carla_transfuser/` (backups `*.bak_2026-10-13*`).

## 1. Repository

```
git clone -b leaderboard_1 https://github.com/autonomousvision/carla_garage.git ~/satrp_real/tfpp/carla_garage
```
Full history kept (56 commits). **HEAD = `4dd9a38a86f7078e0ba3a4a753462df8820276f7`**
("Update Papers with code badges.").
Target commits present: `d491088048378518ce553d83e6cfcb1e3c2593ce` (2024-04-26, LiDAR queue side)
and `cf590987985b1ec4f29124e47580271c2a2c4f70` (2023-08-17, camera-ready / longest6 bugfix).

## 2. Checkpoints

Source (README line 58): `https://s3.eu-central-1.amazonaws.com/avg-projects-2/jaeger2023arxiv/models/pretrained_models.zip`
(4,424,626,176 bytes, md5 `630faf427e88b35bd7343a18be57bcf8`, 71 files; kept at
`~/satrp_real/tfpp/ckpt/pretrained_models.zip`). Extracted only the TF++ dirs.

Campaign checkpoint: **`~/satrp_real/tfpp/ckpt/pretrained_models/longest6/tfpp_all_0`**
(one `model_0030.pth` + `config.pickle` + `args.txt`; the README's "longest6 model",
training id `secret_040_0`, `--setting all`, backbone transFuser regnety_032/regnety_032,
`use_controller_input_prediction 1`, `use_wp_gru 0`, `lidar_seq_len 1`, `num_repetitions 3`).
`sensor_agent.py` loads every `.pth` in the dir as an ensemble, so a single-seed dir =
single model. `tfpp_all_1/2` are the other two training seeds (same config); the
`leaderboard/tfpp_wp_all_*` dirs are the waypoint-head leaderboard models (need `DIRECT=0`) — not used.

| file | md5 |
|---|---|
| longest6/tfpp_all_0/model_0030.pth | `d85d6454358d65b56e6c9c2f074a7546` |
| longest6/tfpp_all_0/config.pickle | `e911fc2d991b17fe78e9adc99993b291` |
| longest6/tfpp_all_1/model_0030.pth | `8672db2530fc9bd63ad18d02187b4e9e` |
| longest6/tfpp_all_1/config.pickle | `a9e6773a6d1dc9869dda03e77ffb832c` |
| longest6/tfpp_all_2/model_0030.pth | `8124cfe4b0882e1506cc05c3673fd7a3` |
| longest6/tfpp_all_2/config.pickle | `70b5a8b901f4e9ad7215739c6efa234b` |
| leaderboard/tfpp_wp_all_0/model_0030.pth | `53fd3ad9f357b7920253cfd77fd5cd9f` |
| leaderboard/tfpp_wp_all_1/model_0030.pth | `c983099cf408869c298e9bbc6536c65d` |
| leaderboard/tfpp_wp_all_2/model_0030.pth | `f1af4e430babeb47c998a1447ab19b94` |

Effective config (GlobalConfig() updated with config.pickle, 76 pickled keys):
`backbone=transFuser, lidar_seq_len=1, data_save_freq=5 (not pickled; GlobalConfig default),
realign_lidar=1, use_ground_plane=0, carla_fps=20, carla_frame_rate=0.05, action_repeat=1,
inital_frames_delay=40 steps, target_speeds=[0,2,5,8] m/s, use_controller_input_prediction=1,
use_wp_gru=0, detect_boxes=1, sync_batch_norm=False, brake_uncertainty_threshold=0.5 (env
overrides to 0.33), stuck_threshold=1100, creep_duration=20, camera 1024x256 fov 110 at
(-1.5,0,2.0), lidar at (0,0,2.5) yaw -90, route_planner 7.5/50 m.`
Loading the state_dict on CPU: 0 missing / 0 unexpected keys (120.4 M params).

## 3. Dependencies (`~/tfuse_venv`, python 3.7.17 inside `~/sifs/python37full.sif`)

`team_code/requirements.txt` vs venv. Exact matches for everything that matters:
torch 1.12.1+cu113, torchvision 0.13.1+cu113, timm 0.6.7, numpy 1.21.6, filterpy 1.4.5,
ujson 5.4.0, Shapely 1.8.4, scipy 1.7.3, scikit-image 0.19.3, Pillow 9.2.0, matplotlib 3.5.3,
imgaug 0.4.0, networkx 2.6.3, py-trees 0.8.3, pygame 2.1.2, dictor 0.1.10, ephem 4.1.3.
Minor version drift (unused by inference): imageio 2.31.2 (req 2.21.2), psutil 7.2.2 (5.9.1),
PyYAML 6.0.1 (6.0), requests 2.31.0 (2.28.1), six 1.17.0 (1.14.0), tabulate 0.9.0 (0.8.10),
tqdm 4.68.2 (4.64.1), opencv-python-headless 4.6.0.66 instead of opencv-python 4.6.0.66.

**Missing and installed** (`pip install --no-deps`, pinned to requirements.txt, all pure wheels,
no conflicts with the existing pins):
`laspy==2.2.0` (data.py top-level import), `rdp==0.8` (scenario_logger.py),
`scikit-learn==1.0.2` + `joblib==1.1.0` + `threadpoolctl==3.1.0` (data.py top-level
`sklearn.utils.class_weight`), `einops==0.4.1` (transfuser.py -> video_swin_transformer.py).
Not installed, not needed by sensor_agent: transformers/tokenizers (plant.py only), laszip
(only for reading .laz training data), open3d, wandb, jupyter stack.

The timm image backbone is created with `pretrained=True` (transfuser.py:25); the regnety_032
weights are already cached at `~/.cache/torch/hub/checkpoints/regnety_032_ra-7f2439f9.pth`
(used by the TF-2022 campaign), so compute nodes (no internet) construct the model fine.

CPU test on visu01 (egg + transfuser_repo leaderboard/scenario_runner + versions/base/team_code on
PYTHONPATH, `LD_LIBRARY_PATH=~/carla_libs` for the egg's libjpeg.so.8):
`import sensor_agent` OK (9.3 s), entry point `SensorAgent`, `model/config/data` resolve to the
carla_garage tree; `LidarCenterNet(config)` builds on CPU (1.7 s); `SensorAgent(ckpt_dir)` runs
setup() up to `torch.load(..., map_location='cuda:0')` and fails there (expected on CPU).
Backward-compat check: with the stock PYTHONPATH the stock `submission_agent` still imports and
`agent_host` resolves the default module `submission_agent`.

## 4. Host integration (`~/proxima/adapters/carla_transfuser/`)

Findings from `team_code/sensor_agent.py` (HEAD):
- entry point `get_entry_point() -> 'SensorAgent'`; `setup(self, path_to_conf_file, route_index=None)`.
  carla_garage's leaderboard base class has `__init__(path_to_conf_file, route_index=None)`;
  the TF-2022 leaderboard on our PYTHONPATH has `__init__(path_to_conf_file)` and calls
  `self.setup(path_to_conf_file)` — works unchanged because `route_index` defaults to None
  (route_index only matters with SAVE_PATH logging). The two base classes differ in nothing else
  except `__call__(sensors=None)`, which our host never calls.
- config: `GlobalConfig()` then `__dict__.update(pickle.load(config.pickle).__dict__)`.
- env read in setup(): `DIRECT` (default 1 -> `inference_direct_controller`), `UNCERTAINTY_WEIGHT`
  (1), `DEBUG_CHALLENGE` (0), `UNCERTAINTY_THRESHOLD` (config 0.5; README: 0.33 for longest6),
  `SLOWER` (1: target_speeds[2],[3] -= 2.0), `TP_STATS` (0), `STOP_CONTROL` (0), `SAVE_PATH`
  (None). With SAVE_PATH set, `_init()` imports `srunner...CarlaDataProvider` and calls
  `get_map()/get_hero_actor()` which our host never populates -> must stay unset.
- `sensors()`: rgb_front (1024x256, fov 110, x=-1.5 z=2.0), imu (sensor_tick 0.05), gps
  (sensor_tick 0.01), speedometer, lidar (x=0 z=2.5 yaw=-90). All five types are supported by
  `SensorRig` (camera width/height/fov applied; IMU sensor_tick forced to 0.0 = every tick; GNSS
  sensor_tick ignored = every tick; speedometer virtual). Data formats match: rgb `(h,w,4)` uint8
  (agent takes `[:, :, :3]`), gps `[lat,lon,alt]` (agent takes `[:2]`), imu 7-vector (agent takes
  `[-1]` = compass), lidar `(N,4)` float32 (agent takes `[1][:, :3]`), speed `{'speed': v}`.
- `set_global_plan(global_plan_gps, global_plan_world_coord)` = base-class downsample (50 m),
  consumed in `_init()` via `RoutePlanner.set_route(self._global_plan, gps=True)`; identical to
  the 2022 fork's signature, so `load_agent()`'s existing call works.
- `run_step(input_data, timestamp, sensors=None)`: no GameTime/CarlaDataProvider use outside the
  SAVE_PATH branch. Step 0 returns brake (init), steps 1..4 return brake while `lidar_buffer`
  fills (maxlen 5), then drives; `inital_frames_delay=40` only affects the UKF's assumed control.
- **LiDAR mechanism (d491088)**: `lidar_buffer = deque(maxlen=lidar_seq_len*data_save_freq = 5)`
  gets one full cloud appended per `run_step` (current sweep + previous sweep aligned into the
  current frame). `lidar_indices=[0]`. HEAD reads `lidar_buffer[-(0+1)] = [-1]` = newest; the
  pre-fix code reads `lidar_buffer[0]` = oldest = **4 ticks = 200 ms stale at 20 FPS** (the commit
  message says 100 ms; with action_repeat=1 the buffer advances every tick, so in this host it
  is 4 ticks). `realign_lidar` is skipped for `lidar_seq_len == 1`, so the stale cloud is used in the
  ego frame of 4 ticks ago. This is ACTIVE in our host for either lidar spec because the buffer
  fills per tick regardless of sweep fraction.
- **Lidar spec to use: `TF_LIDAR_LEADERBOARD=1`.** carla_garage's `agent_wrapper.py` sets
  `rotation_frequency=10, points_per_second=600000, channels=64, range=85, upper_fov=10,
  lower_fov=-30, atmosphere_attenuation_rate=0.004, dropoff_general_rate=0.45,
  dropoff_intensity_limit=0.8, dropoff_zero_intensity=0.4` — exactly what `SensorRig` applies
  under `TF_LIDAR_LEADERBOARD=1`. At 20 FPS sync that is the half-sweep-per-tick regime that
  `run_step` explicitly assumes ("We only get half a LiDAR at every time step") and that the TF++
  training data (data_agent.py via the same wrapper) contains. The adapter default
  (`rotation_frequency=20`, no dropoff) would feed two full sweeps per step at ~2x training
  density. The TF-2022 campaign keeps its default for reproducibility; this is a new campaign.

Edits (minimal, backward compatible):
- `agent_host.py` (backup `agent_host.py.bak_2026-10-13`): `load_agent()` imports
  `os.environ.get("TF_AGENT_MODULE", "submission_agent")` instead of the literal; the
  `[team_code] <module> from <file> md5=` proof line now names the module. Default behaviour unchanged.
- `run_one.py`: `meta["agent"] = os.environ.get("TF_AGENT_NAME", "transfuser_2022")`. This exact
  line was already present when I got there (a concurrent Tier-2 edit today, backup
  `run_one.py.bak_2026-10-13b`, which also added an optional `CH_AGENT_HOST` hook); I made no
  further change to run_one.py.

## 5. Versions (`~/satrp_real/tfpp/versions/<vid>/team_code`, full copies of `team_code` at HEAD)

| vid | change vs base | sensor_agent.py md5 |
|---|---|---|
| base | none (HEAD 4dd9a38) | `5109444fe39fb4cbde5f6e15bfc20055` |
| v_lidar_stale | revert d491088: line 409 `lidar_buffer[-(i+1)]` -> `lidar_buffer[i]` | `a2c179bd0988c3800e51afb4e09292a9` |
| v_speed_offset | revert cf59098 (sensor_agent.py hunk only): lines 92-94 SLOWER offset 2.0 -> 1.0 m/s | `51d20255e4f5d3aec624b8f8854a6438` |

`diff -r` confirms base == HEAD team_code and each version differs from base by exactly its hunk
(no `.orig/.rej`). Details, unified hunks, mechanism, expected pre-fix behaviour and covering /
negative-control scenarios are in `~/satrp_real/tfpp/versions.json`:
- v_lidar_stale: covering = CutIn, CrossingTraffic, OncomingDrift, LeadDecel (moving actors);
  negative control = LeadStopped (static target; a 200 ms stale cloud shifts it by <=1.6 m).
- v_speed_offset: covering = all five templates (cruise speed ~7 vs ~6 m/s, longer stopping
  distance everywhere); no negative control.

## 6. Jobs (`~/satrp_real/tfpp/gen_jobs_tfpp.py`)

Suite = the 30 scenarios of `~/satrp_mutation/ads/store/transfuser/suite.json`; seed =
`20260806 + sid*1000 + run_idx`; duration 40; perturb null; schema = jobs_matrix.jsonl
(`mutant{mid,site,md5}` + `team_code_dir`).
- `jobs_base.jsonl`: 1,200 (30 x run_idx 0..39), `base_s<sid>_r<r>`, traces `traces_base/`.
- `jobs_versions.jsonl`: 1,440 (30 x 2 versions x run_idx 0..23), `rv_<vid>_s<sid>_r<r>`,
  traces `traces_<vid>/`; scenario-major order (sid, vid, r).
- `jobs_smoke.jsonl`: 3 (sid 81 ProxCutIn, TF-2022 nominal 5/5 contacts, run_idx 0, seed
  20341806, one per version), traces `traces_smoke/`.

## 7. SLURM (`~/satrp_real/tfpp/tfpp_campaign.slurm`)

Copy of `tf_campaign.slurm` (port-probe loop, server restart loop, worker slicing
`jobs[task::ntask]`, `NTASK_OVERRIDE`) with: output `~/satrp_real/tfpp/logs/tfpp_%A_%a.out`
and `server_<A>_<task>.log`; `TF_CKPT=$TFPP_CKPT` (default the longest6/tfpp_all_0 dir);
`TF_AGENT_MODULE=sensor_agent TF_AGENT_NAME=tfpp_lb1 TF_LIDAR_LEADERBOARD=1`;
`SLOWER=1 DIRECT=1 UNCERTAINTY_WEIGHT=1 UNCERTAINTY_THRESHOLD=0.33 STOP_CONTROL=0 TP_STATS=0
DEBUG_CHALLENGE=0`; `env -u SAVE_PATH`; PYTHONPATH unchanged (egg, PythonAPI/carla for
`agents.navigation`, transfuser_repo leaderboard/scenario_runner/team_code_transfuser, adapter) —
the per-job `team_code_dir` is inserted at `sys.path[0]` by `load_agent`, so carla_garage's
`model/config/data` shadow the TF-2022 ones inside each fresh run_one.py subprocess.

## 8. Smoke

SMOKE_RESULTS_PLACEHOLDER

## 9. Launch commands (full campaign)

```
# base: 1,200 jobs, 4 tasks x 300 jobs (~5 min/job -> ~25 h/task, inside the 48 h cap)
cd ~/satrp_real/tfpp
JOBS_FILE=~/satrp_real/tfpp/jobs_base.jsonl     sbatch --array=0-3 tfpp_campaign.slurm
# versions: 1,440 jobs, 5 tasks x 288 jobs
JOBS_FILE=~/satrp_real/tfpp/jobs_versions.jsonl sbatch --array=0-4 tfpp_campaign.slurm
```
Partial resubmits must keep the stride: `NTASK_OVERRIDE=4` (base) / `NTASK_OVERRIDE=5`
(versions) with `--array=<missing tasks>`. The worker skips jobs whose `trace_out` exists, so a
resubmit resumes. Results per task: `jobs_<x>_task<N>.results.jsonl` next to the jobs file.

## 10. Junction block through carla_garage's vendored leaderboard evaluator (scope extension 2026-10-13)

Files (all `~/satrp_real/tfpp/`):
- `lb_run_eval.py` — runs `carla_garage/leaderboard/leaderboard/leaderboard_evaluator_local.py`
  (the evaluator `leaderboard/scripts/local_evaluation.sh` uses: `route_scenario_local`,
  `scenario_manager_local`, `agent_wrapper_local`, `statistics_manager_local`) in-process via
  `runpy`, and on exit prints the deployment proof from `sys.modules`:
  `[team_code] sensor_agent from <file> md5=<md5>` (+ model, config). The evaluator itself never
  prints the agent path; it does `sys.path.insert(0, dirname(--agent))` and imports
  `sensor_agent`, so the team_code_dir's model/config/data shadow everything else.
- `lb_worker.py JOBS_FILE [TASK NTASK]` — per job: extracts a ONE-ROUTE XML
  (`<results dir>/routes/<job_id>.xml`; the fork has no `--routes-subset`), removes any stale
  checkpoint, runs `lb_run_eval.py` in a fresh subprocess with stdout/stderr captured to
  `<results_out>.log`, hard wall-clock cap (`LB_JOB_TIMEOUT`, default 2400 s) -> kill process
  group, pkill the CARLA server by port (slurm loop reboots it), retry once. Evaluator args:
  `--routes <one-route xml> --scenarios <json> --repetitions=1 --track=SENSORS
  --checkpoint <results_out> --agent <team_code_dir>/sensor_agent.py --agent-config <ckpt_dir>
  --debug=0 --port $CARLA_PORT --trafficManagerPort $LB_TM_PORT (=port+20)
  --trafficManagerSeed <job seed> --timeout 600`; `--resume` is omitted on purpose (argparse
  `type=bool`: any string is True). Env: `ROUTES` (the one-route xml; the fork derives
  `route_date_string` from its stem), `SCENARIOS`, `CHALLENGE_TRACK_CODENAME=SENSORS`,
  `REPETITIONS=1 RESUME=0 DATAGEN=0 DEBUG_CHALLENGE=0`, `TEAM_AGENT/TEAM_CONFIG/CHECKPOINT_ENDPOINT`,
  `BENCHMARK=<job.benchmark | LB_BENCHMARK | longest6>`, `SAVE_PATH` removed, and the sensor_agent
  env inherited from the slurm script (`SLOWER=1 DIRECT=1 UNCERTAINTY_WEIGHT=1
  UNCERTAINTY_THRESHOLD=0.33 STOP_CONTROL=0 TP_STATS=0`).
  Deployment proof = md5(team_code_dir/sensor_agent.py) computed by the worker must equal the
  md5 in the `[team_code] sensor_agent from` log line AND that file must lie under team_code_dir
  -> `proof_ok`. Results: the `--checkpoint` JSON (`_checkpoint.records[-1]`) is parsed with
  `~/satrp_real/routes/parse_lb_results.py` if present (tries `parse_checkpoint`,
  `parse_lb_results`, `parse_results`, `parse`), else the built-in mapping: `trigger = 1` if any of
  collisions_pedestrian/vehicle/layout, red_light, outside_route_lanes, route_dev is non-empty;
  `blocked = vehicle_blocked` non-empty; `timeout = route_timeout` non-empty; `status`,
  `score_composed`, `score_route` (RC), `score_penalty`, per-infraction counts + messages,
  `duration_game/system`, `route_length` kept. One row per run -> `<jobs>_task<N>.results.jsonl`
  and `<results_out>.row.json` (the worker skips a job only when both the checkpoint and the row
  exist, so a resubmit resumes).
- `tfpp_lb_campaign.slurm` — same server loop + port probe as `tfpp_campaign.slurm` (probe also
  checks the TM port `P+20`), PYTHONPATH = egg : PythonAPI/carla :
  **carla_garage/leaderboard : carla_garage/scenario_runner** (not transfuser_repo's), worker =
  `lb_worker.py`. Logs `~/satrp_real/tfpp/logs/tfpp_lb_%A_%a.out`, `server_lb_<A>_<task>.log`.
- `gen_jobs_lb.py` — when `~/satrp_real/routes/junction_routes_town01.xml` +
  `junction_scenarios_town01.json` exist: `jobs_lb_base.jsonl` (base, every route, run_idx 0..39),
  `jobs_lb_versions.jsonl` (2 versions x routes x run_idx 0..23), `jobs_lb_smoke.jsonl` (first
  route, base, run_idx 0). Seed = `20260806 + 1000*(1000+route_index) + run_idx`
  (route_index = 0-based position in the XML), disjoint from the straight-block seeds.
  `results_out = ~/satrp_real/tfpp/lb_results_<vid>/<job_id>.json` (`lb_results_smoke/` for the
  smoke). Exits 2 with `MISSING ...` while the route files are absent.

Determinism caveats found in the fork (not changed — the evaluator is the SUT's own harness):
- `leaderboard_evaluator_local.py` seeds `CarlaDataProvider._rng = RandomState(config.index)`;
  with a one-route XML `config.index == 0` for every job, so scenario-actor/background-spawn
  randomness is identical across runs and routes; **only `--trafficManagerSeed` (= job seed)
  varies with run_idx.** If per-run variation of the scenario actors is wanted, the run_idx must
  be folded in some other way (e.g. a routes XML with the route repeated N times so that
  `config.index` differs; or a backward-compatible env override in the vendored evaluator).
- `route_scenario_local._initialize_actors`: `BENCHMARK=longest6` -> 500 background vehicles
  (deterministic, the README eval setting; used by default); `BENCHMARK` unset ->
  `random.randint(130, 260)` from Python's unseeded `random` -> nondeterministic. `BENCHMARK=empty`
  -> 0. Blocked criterion threshold `BLOCKED_THRESHOLD` env (default 180 s).
- The evaluator calls `client.load_world('Town01')` at construction and `load_world(config.town)`
  per route (both wrapped in try/except RuntimeError -> `get_world()`).

CPU checks (visu01): `tfpp_lb_campaign.slurm` passes `bash -n`; `lb_worker.py`, `lb_run_eval.py`,
`gen_jobs_lb.py` compile; the fork's `leaderboard_evaluator_local.py` imports with the garage
leaderboard/scenario_runner on PYTHONPATH (`leaderboard`/`srunner` resolve to the carla_garage copies).

LB launch (after the route files exist and the lb smoke passes):
```
cd ~/satrp_real/tfpp && python3 gen_jobs_lb.py
JOBS_FILE=~/satrp_real/tfpp/jobs_lb_smoke.jsonl    sbatch --array=0 --time=00:45:00 tfpp_lb_campaign.slurm
JOBS_FILE=~/satrp_real/tfpp/jobs_lb_base.jsonl     sbatch --array=0-3 tfpp_lb_campaign.slurm
JOBS_FILE=~/satrp_real/tfpp/jobs_lb_versions.jsonl sbatch --array=0-4 tfpp_lb_campaign.slurm
```
(array sizes to be set from the route count: jobs/task should stay <= ~300 at ~5-8 min per
evaluator run incl. agent load; partial resubmits need `NTASK_OVERRIDE=<original count>`).

LB_SMOKE_PLACEHOLDER
