# realfaults/ -- the real-fault validation anchor

See `docs/REALFAULTS.md` for the design. Campaign-time code, as it ran.

```
pylot/      gen_jobs_lb.py (jobs), lb_worker.py (one Leaderboard route per job, in the Pylot container),
            pylot_host.py (drives the stack), pylot_lb_campaign.slurm, conf/ (challenge configurations),
            versions.json (the 8 reverted fixes: commit, mechanism, prediction, a-priori status),
            patches/<vid>.patch (the revert) and <vid>.difftrace.patch (the deployment-proof trace statement)
tfpp/       gen_jobs_tfpp.py (straight block), gen_jobs_lb.py (Leaderboard block), lb_worker.py, lb_run_eval.py,
            tfpp_campaign.slurm, tfpp_lb_campaign.slurm, versions.json (the 2 reverted fixes with hunks and md5)
analysis/   real_numbers.py: raw record -> results/realfaults/{all_runs.csv, cells.csv, real_numbers.md}
            + data/derived/real_{pylot,pylot_T2,tfpp,tfpp_straight}/runs.jsonl
docs/       pylot_versions.md (full version audit), pylot_runtime.md, tfpp_setup.md
```

`python3 realfaults/analysis/real_numbers.py` needs the raw archive unpacked at
`$SATRP_RAW/realfaults` (`tools/fetch_data.sh realfaults`); it reproduces the shipped
instance files bit for bit.
