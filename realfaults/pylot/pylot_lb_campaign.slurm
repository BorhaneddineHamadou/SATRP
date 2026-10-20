#!/bin/bash
#SBATCH --job-name=satrp_pylot_lb
#SBATCH --partition=gpuv100,gpup6000,classicgpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=12
#SBATCH --mem=24G
#SBATCH --time=48:00:00
#SBATCH --exclude=node27
#SBATCH --output=/home/users/bhamadou/satrp_real/pylot/logs/pylot_lb_%A_%a.out

# Tier-2 real-fault study, Pylot leaderboard block: Pylot (ERDOSAgent) run
# through the leaderboard 1.0 evaluator SHIPPED IN ~/sifs/pylot_challenge.sif
# by lb_worker.py (host python3; it launches `singularity exec` itself), one
# route per job, fresh evaluator process per run, against this task's external
# CARLA 0.9.10.1 server.  Same server loop + port probe as
# tfpp_lb_campaign.slurm.  Pylot's faster-rcnn shares the GPU with the server.
# Submit: JOBS_FILE=... sbatch --array=0-3 pylot_lb_campaign.slurm
#   video smoke: sbatch --export=ALL,JOBS_FILE=...,LB_VIDEO_DIR=... --array=0-2 ...
#   partial resubmits MUST set NTASK_OVERRIDE=<original array size>.
set -u
: "${JOBS_FILE:?set JOBS_FILE=<path to jobs jsonl>}"
TASK=${SLURM_ARRAY_TASK_ID:-0}
NTASK=${NTASK_OVERRIDE:-${SLURM_ARRAY_TASK_COUNT:-1}}
PORT_SLOT=$((SLURM_JOB_ID % 120))
for k in $(seq 0 119); do
  P=$((2000 + ((PORT_SLOT + k) % 120) * 50))
  if ! ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE ":($P|$((P+1))|$((P+20)))$" \
     && ! pgrep -u $USER -f "carla-rpc-port=$P\b" >/dev/null; then PORT=$P; break; fi
done
: "${PORT:?no free CARLA port found}"
TM_PORT=$((PORT + 20))

PYLOT=~/satrp_real/pylot
LOGS=/home/users/bhamadou/satrp_real/pylot/logs
PYLOT_SIF=${PYLOT_SIF:-$HOME/sifs/pylot_challenge.sif}
mkdir -p "$LOGS"

GPUCOMP=$(ls /usr/lib64/libnvidia-gpucomp.so.* | head -1)
echo "=== pylot lb task $TASK/$NTASK port $PORT tm $TM_PORT (gpucomp: $GPUCOMP) sif $PYLOT_SIF jobs $JOBS_FILE ==="
(while true; do
  singularity exec --nv \
    --bind "$GPUCOMP":/nvidia_extra/$(basename "$GPUCOMP") \
    ~/sifs/carla09101.sif /bin/bash -c \
    "export LD_LIBRARY_PATH=/nvidia_extra:/.singularity.d/libs:\$LD_LIBRARY_PATH
     DISPLAY= SDL_VIDEODRIVER=offscreen /home/carla/CarlaUE4.sh -opengl \
     -nosound -carla-rpc-port=$PORT -quality-level=Epic"
  echo "[server-loop] CARLA exited $? -- restarting in 5s"
  sleep 5
done) > $LOGS/server_lb_${SLURM_ARRAY_JOB_ID:-0}_${TASK}.log 2>&1 &
sleep 45

# The worker runs on the HOST python3 (stdlib only) and starts the evaluator
# (and the chase-camera sidecar when LB_VIDEO_DIR is set) inside
# pylot_challenge.sif via `singularity exec --nv --cleanenv --bind $HOME
# --bind <version>/pylot:/workspace/team_code/pylot`; nested singularity is
# not available, so the worker itself must stay outside the image.
PYLOT_SIF=$PYLOT_SIF \
LB_JOB_TIMEOUT=${LB_JOB_TIMEOUT:-3000} \
LB_CLIENT_TIMEOUT=${LB_CLIENT_TIMEOUT:-600} \
CARLA_PORT=$PORT LB_TM_PORT=$TM_PORT \
CARLA_EXTERNAL=1 \
LB_VIDEO_DIR=${LB_VIDEO_DIR:-} \
PYTHONUNBUFFERED=1 \
python3 $PYLOT/lb_worker.py $JOBS_FILE $TASK $NTASK
pkill -u $USER -f "carla-rpc-port=$PORT" 2>/dev/null || true
if [ -n "${LB_VIDEO_DIR:-}" ]; then ~/satrp_real/tools/encode_videos.sh "$LB_VIDEO_DIR" "$LB_VIDEO_DIR/../videos"; fi
echo "=== pylot lb task $TASK done ==="
