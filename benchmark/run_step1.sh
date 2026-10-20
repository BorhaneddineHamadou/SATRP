#!/bin/bash
# Step 1: coverage lines -> covered candidate sample -> materialize -> screen jobs -> submit screen.
# usage: run_step1.sh <stack> [K=100] [--submit]
set -euo pipefail
STACK=$1; K=${2:-100}; SUBMIT=${3:-}
ADS=~/satrp_mutation/ads
cd $ADS
echo "== coverage lines ($STACK)"; python3 coverage_lines.py $STACK | tail -25
echo "== sample";      python3 pipeline.py sample $STACK --covered $K | tail -4
echo "== materialize"; python3 pipeline.py materialize $STACK
echo "== screen jobs"; python3 pipeline.py screen-jobs $STACK
N=$(grep -c . store/$STACK/jobs_screen.jsonl)
if [ "$SUBMIT" = "--submit" ]; then
  cd store/$STACK
  if [ "$STACK" = openpilot ]; then
    # 4 tasks x ~150 jobs (< 300-job leak horizon), displays 81+
    JOBS_FILE=$PWD/jobs_screen.jsonl DISPLAY_BASE=81 sbatch --export=ALL,JOBS_FILE,DISPLAY_BASE --array=0-3 $ADS/slurm/op_campaign.slurm
  else
    JOBS_FILE=$PWD/jobs_screen.jsonl sbatch --export=ALL,JOBS_FILE --array=0-5 $ADS/slurm/tf_campaign.slurm
  fi
  echo "submitted screen ($N jobs) for $STACK"
fi
