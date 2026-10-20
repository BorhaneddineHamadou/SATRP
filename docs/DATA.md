# The raw benchmark record (Zenodo)

Four archives; `bash tools/fetch_data.sh [name]` downloads, verifies and unpacks them into
`raw/`. They are needed only to rebuild `data/derived/` from scratch
(`docs/REPRODUCTION.md`) or to inspect individual runs; every paper number recomputes from
the shipped instances without them.

Record: Zenodo DOI `<DOI>` (to be filled at publication).

| archive | contents | size | sha256 |
|---|---|---|---|
| `satrp_raw_openpilot.zip` | openpilot clean rerun: jobs, outcome pools, 21,360 traces, mutant sources, suite/screen/selection | 176 MB | `135c15d8100cd9171fb2cf37bacb4ca775d18cd4729274497271c59d88a5f82a` |
| `satrp_raw_openpilot_first_campaign.zip` | openpilot screening campaign (100 candidates, twins, traces) + outcome pools of the discarded first campaign | 5 MB | `35737d1655be5bca19b8939c1f30e1d6ace6ac832bc20ea39f384f2baa2a30b1` |
| `satrp_raw_transfuser.zip` | TransFuser store: jobs, outcome pools, traces (base, matrix, nominal r0-4), 100 mutant team_code copies, suite/screen/selection | 450 MB | `f79f6296f89e01773b39b19ae2f088bcd9c472573ec9aed2d58a5dd438eb78df` |
| `satrp_raw_realfaults.zip` | Pylot and TF++: jobs, outcome pools, Leaderboard records and evaluator logs, TF++ traces, version trees and patches, difftrace variants, Pylot configs and detector weights | 771 MB | `02ac307481ed912baaba9ccb6147c036875337ba491b5b450386bc29019acac2` |

Checksums (sha256sum format):

```
135c15d8100cd9171fb2cf37bacb4ca775d18cd4729274497271c59d88a5f82a  satrp_raw_openpilot.zip
35737d1655be5bca19b8939c1f30e1d6ace6ac832bc20ea39f384f2baa2a30b1  satrp_raw_openpilot_first_campaign.zip
f79f6296f89e01773b39b19ae2f088bcd9c472573ec9aed2d58a5dd438eb78df  satrp_raw_transfuser.zip
02ac307481ed912baaba9ccb6147c036875337ba491b5b450386bc29019acac2  satrp_raw_realfaults.zip
```

## Layout after unpacking

```
raw/openpilot/                       the openpilot clean rerun (the paper's data)
  jobs_clean.jsonl                     21,360 jobs: 1,200 base_* (30 scenarios x r0-39) + 20,160 mx_<mid>_s<sid>_r<r> (28 x 30 x 24), shuffled
  results/jobs_clean_task<k>.results.jsonl   one row per attempt-completed job (last row per job_id wins): outcome, engaged, attempts,
                                       mutant_hook_hits, params_isolated, contact, trace_exists
  traces_base/, traces_mx_<mid>/        one .npz per run: data[T,16] (step, ego pose/speed, lead, commands, crash, ...), columns, meta (scenario, seed, params, engaged_step, done_info)
  mutants/<mid>/selfdrive/...          the mutated file(s) of each selected mutant
  suite.json, candidates.json, screen_classes.json, selected.json
raw/openpilot_screen/                screening campaign of the 100 candidates (+ 6 same-seed baseline twins)
  jobs_screen*.jsonl, results/jobs_screen*_task<k>.results.jsonl, traces_screen_<mid>/, traces_screentwin/
raw/openpilot_first_campaign_discarded/   outcome pools (no traces) of the first openpilot campaign, discarded because runs shared
                                       openpilot's persisted calibration state (paper, Threats); kept for transparency
raw/transfuser/                      the TransFuser store
  jobs_base.jsonl (r5-39), jobs_matrix.jsonl (r0-11), jobs_matrix_ext.jsonl (r12-23), jobs_matrix_redo.jsonl, jobs_screen.jsonl
  <jobs>_task<k>.results.jsonl, traces_base/, traces_mx_<mid>/, mutants/<mid>/team_code_transfuser/, suite/candidates/screen/selected json
  nominal/                             the Proxima nominal campaign rows and traces that supply baseline runs r0-4 of the 30 suite scenarios
raw/realfaults/pylot/                jobs_lb_*.jsonl + results; lb_results_<vid>/<job>.json (Leaderboard record), .row.json, .json.log,
                                       <job>/<job>.pylot.{conf,csv} and route .xml; versions/ (base tree, per-version trees, patches,
                                       versions.json), versions_dt/ (difftrace variants), conf/, models_fix/ (the detector weights the
                                       container needed); per-run stdout and profiler logs (28 GB) are omitted and available on request
raw/realfaults/tfpp/                 jobs_*.jsonl + results; traces_base/, traces_v_*/ (straight block); lb_results_<vid>/ (Leaderboard block);
                                       versions/{base,v_lidar_stale,v_speed_offset}/team_code, versions.json
```

Trace path fields inside the job files are the campaign-time absolute paths; the adapters
resolve them inside `raw/` (`satrp/adapter.py::_resolve_trace`).
