#!/bin/bash
# Step 2: screen analysis -> mutant selection -> matrix jobs (no submit unless --submit).
# usage: run_step2.sh <stack> [N=28] [SEEDS=12] [--submit]
set -euo pipefail
STACK=$1; N=${2:-28}; SEEDS=${3:-12}; SUBMIT=${4:-}
ADS=~/satrp_mutation/ads; cd $ADS
echo "== screen classes ($STACK)"; python3 analyze_screen.py $STACK
echo "== select";  python3 select_mutants.py $STACK $N
echo "== matrix jobs"; python3 pipeline.py matrix-jobs $STACK store/$STACK/selected.json $SEEDS
NJ=$(grep -c . store/$STACK/jobs_matrix.jsonl)
if [ "$SUBMIT" = "--submit" ]; then
  cd store/$STACK
  if [ "$STACK" = openpilot ]; then
    # slices <= 300 jobs (leak horizon): tasks = ceil(NJ/280)
    T=$(( (NJ + 279) / 280 )); JOBS_FILE=$PWD/jobs_matrix.jsonl DISPLAY_BASE=101 sbatch --export=ALL,JOBS_FILE,DISPLAY_BASE --array=0-$((T-1)) $ADS/slurm/op_campaign.slurm
  else
    T=$(( (NJ + 299) / 300 )); JOBS_FILE=$PWD/jobs_matrix.jsonl sbatch --export=ALL,JOBS_FILE --array=0-$((T-1)) $ADS/slurm/tf_campaign.slurm
  fi
  echo "submitted matrix ($NJ jobs, $T tasks) for $STACK"
fi
