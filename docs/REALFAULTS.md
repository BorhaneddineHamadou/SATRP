# The real-fault validation anchor (RQ5)

Ten historical single-hunk fixes of two further stacks are reverted one at a time and
executed under the benchmark's protocol (24 runs per version cell, 40 for the baseline,
same label rule). Everything is in `realfaults/`; the instances it produces are
`data/derived/real_{pylot,pylot_T2,tfpp,tfpp_straight}/runs.jsonl`.

## Pylot (modular pipeline, CARLA Leaderboard 1.0, CARLA 0.9.10.1)

* Base = Pylot challenge branch head `8218ca9`; the eight versions are patches on it
  (`realfaults/pylot/patches/<vid>.patch`; the raw archive carries the full per-version
  trees under `realfaults/pylot/versions/`). `realfaults/pylot/versions.json` records, for
  every version, the fix commit, the mechanism, the predicted effect and its a-priori status
  (`ready` / `likely_inert`), written before execution; `realfaults/docs/pylot_versions.md`
  is the full audit.
* Deployment proof: each version also carries a `.difftrace.patch` that inserts one guarded
  trace statement at a location shared by base and version; a run's result row stores
  `proof_ok` (md5 of the changed files + the difftrace lines) and `difftrace_lines`.
* Harness: `realfaults/pylot/lb_worker.py` runs one Leaderboard route per job inside the
  Pylot container (`pylot_host.py` drives the stack; `conf/*.conf` are the challenge
  configurations; `pylot_lb_campaign.slurm` is the array script; `gen_jobs_lb.py` writes the
  jobs). Routes: twelve public Leaderboard 1.0 training routes in Town01, two per scenario
  class. Each job writes the Leaderboard record (`lb_results_<vid>/<job>.json`), a
  one-line summary (`.row.json`) and the evaluator log (`.json.log`).
* Trigger T1 = any collision, red-light infraction, outside-route-lanes or route deviation
  recorded by the evaluator; a blocked or timed-out run is a separate status. T2 ("any
  failure", T1 or blocked or timeout) is the sensitivity variant (`real_pylot_T2`).

## TF++ (end-to-end, carla_garage)

* Base = carla_garage `leaderboard_1` head `4dd9a38` with the authors' released checkpoint
  (`tfpp_all_0`); the two versions revert the fixes `d491088` (`v_lidar_stale`) and the
  target-speed-offset fix (`v_speed_offset`) in `team_code/sensor_agent.py`
  (`realfaults/tfpp/versions.json` holds the hunks, the mechanism, the covering and
  negative-control scenario classes, and the md5 of the deployed agent file).
* Two blocks: the *straight block* (the 30-scenario TransFuser suite in the Proxima CARLA
  host; `gen_jobs_tfpp.py`, `tfpp_campaign.slurm`; trigger = contact in the trace) and the
  *Leaderboard block* (the same twelve routes as Pylot; `gen_jobs_lb.py`, `lb_worker.py`,
  `lb_run_eval.py`, `tfpp_lb_campaign.slurm`).

## Analysis

`realfaults/analysis/real_numbers.py` reads the raw jobs/results (`$SATRP_RAW/realfaults`),
dedupes rows (an OOM rerun overrides), verifies seed parity, writes
`results/realfaults/{all_runs.csv, cells.csv, real_numbers.md}` (per-version rates,
per-cell Fisher labels under both protocols, parametric and empirical null calibration, the
pre-registered mechanism tests on the TF++ straight block) and the four instance files.
The method comparison on these instances is `satrp/run_altgt_mutation.py real_<...>`
(`tools/run_all.sh` runs all of it).

Not redistributed: the Pylot container image and models, the CARLA server, the carla_garage
checkpoint (public), and the per-run stdout/profiler logs (28 GB; available on request).
