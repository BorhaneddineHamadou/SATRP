#!/bin/bash
# Recompute every number in the paper from the shipped instances (data/derived/*/runs.jsonl).
# CPU only. Needs the requirements.txt packages. Outputs land in results/<instance>/ and
# results/*.md; results/paper/ holds the values the paper was typeset from, for comparison
# (python3 tools/compare_with_paper.py).
#
#   bash tools/run_all.sh            # full run: 8 parallel workers, ~1 h on a 32-core node
#   QUICK=1 bash tools/run_all.sh    # 10-minute smoke run with 10 bootstrap reps (numbers approximate)
#
# Every script is also runnable on its own; see docs/REPRODUCTION.md for the table -> script map.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export SATRP_ROOT="$ROOT"
cd "$ROOT/satrp"
PY=${PYTHON:-python3}
if [ "${QUICK:-0}" = "1" ]; then export NB=10 SATRP_NBOOT=10; else export NB=${NB:-200} SATRP_NBOOT=${SATRP_NBOOT:-200}; fi
L="$ROOT/results/logs"; mkdir -p "$L"
run() { local name=$1; shift; echo "[$(date +%H:%M:%S)] start $name"; ( "$@" > "$L/$name.log" 2>&1 && echo "[$(date +%H:%M:%S)] done  $name" ) || { echo "[$(date +%H:%M:%S)] FAILED $name (see results/logs/$name.log)"; exit 1; }; }

# ---- 1. Fisher ground truth, all methods, every instance (Table 2, 4, 5, 6, 7; Fig. 2) ----
for inst in mutation_openpilot mutation_transfuser; do
  run altgt_${inst}_full $PY run_altgt_mutation.py $inst &
  ALTGT_SEP=1 run altgt_${inst}_sep $PY run_altgt_mutation.py $inst &
  for h in 2 4 8 20; do run altgt_${inst}_h$h $PY run_altgt_mutation.py $inst $h & done
done
wait
for inst in real_pylot real_pylot_T2 real_tfpp real_tfpp_straight; do
  run altgt_${inst}_full $PY run_altgt_mutation.py $inst &
  ALTGT_SEP=1 run altgt_${inst}_sep $PY run_altgt_mutation.py $inst &
done
wait

# ---- 2. SA-TRP-only budget curves, gamma frontier and ROC per mutation instance (supporting plots) ----
for inst in mutation_openpilot mutation_transfuser; do
  ( export INJECT_GLOB="$ROOT/data/derived/$inst/runs.jsonl" INJECT_OUT="$ROOT/results/$inst"
    run curves_$inst bash -c "$PY eval_satrp.py && $PY eval_satrp_frontier.py && $PY satrp_roc.py" ) &
done

# ---- 3. Clustered bootstrap CIs + held-out gamma selection (Sec. "Statistical uncertainty", Sec. opselect) ----
for inst in mutation_openpilot mutation_transfuser; do run extra_$inst $PY extra_analysis_mut.py $inst & done

# ---- 4. Ground-truth-depth decomposition (RQ4 "Power") ----
( export DD_PAT="$ROOT/data/derived/mutation_transfuser/runs.jsonl" DD_GS=20260806 NB=100; run depth_transfuser $PY depth_decomp.py ) &   # NB=100 as in the paper
( export DD_PAT="$ROOT/data/derived/mutation_openpilot/runs.jsonl"  DD_GS=20260722 NB=100; run depth_openpilot  $PY depth_decomp.py ) &
wait

# ---- 5. Phenomenon statistics (RQ1, Table 1/3). The raw store adds the same-seed twin pairs; data/suites gives everything else ----
RAW=${SATRP_RAW:-$ROOT/raw}
OP_STORE="$RAW/openpilot_screen"; [ -d "$OP_STORE" ] || OP_STORE="$ROOT/data/suites/openpilot"
TF_STORE="$RAW/transfuser";       [ -d "$TF_STORE" ] || TF_STORE="$ROOT/data/suites/transfuser"
run phenomenon_openpilot  $PY phenomenon_stats.py mutation_openpilot  "$OP_STORE"
run phenomenon_transfuser $PY phenomenon_stats.py mutation_transfuser "$TF_STORE"

# ---- 6. Summary tables and the operating-curve figure ----
run summarize $PY summarize_mutation_frontier.py fisher fisher_sep
run cross     $PY summarize_cross_instance.py
run history   $PY summarize_history_depth.py
run figure    $PY make_fig_opcurve.py
echo "ALL DONE $(date)  -> results/   (compare: python3 tools/compare_with_paper.py)"
