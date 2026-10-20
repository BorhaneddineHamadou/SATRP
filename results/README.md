# results/

`paper/` holds the result files the paper was typeset from (kept under version control,
never overwritten by the scripts):

```
paper/mutation_openpilot/, paper/mutation_transfuser/   frontier_all_fisher[_sep|_h2|_h4|_h8|_h20]{,_best}.csv, phenomenon.json,
                                                        satrp_{summary,curves,frontier,roc}.{csv,png}
paper/real_pylot/, real_pylot_T2/, real_tfpp/, real_tfpp_straight/   frontier_all_fisher{,_sep}{,_best}.csv
paper/extra_analysis_mut_mutation_{openpilot,transfuser}.json         clustered bootstrap CIs + held-out gamma
paper/mutation_all_methods_fisher.md, _fisher_sep.md, mutation_history_depth.md   the summary tables
paper/realfaults/{real_numbers.md, all_runs.csv, cells.csv}           the real-fault analysis
paper/depth_decomp_{openpilot,transfuser}.log                         ground-truth-depth decomposition output
paper/fig_opcurve.pdf                                                 the operating-curve figure
```

`tools/run_all.sh` writes a fresh copy of all of the above directly under `results/`
(ignored by git); `tools/compare_with_paper.py` diffs the two.
