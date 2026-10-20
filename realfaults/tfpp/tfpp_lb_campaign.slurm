#!/bin/bash
#SBATCH --job-name=satrp_tfpp_lb
#SBATCH --partition=gpuv100,gpup6000,classicgpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=48:00:00
#SBATCH --exclude=node27
#SBATCH --output=/home/users/bhamadou/satrp_real/tfpp/logs/tfpp_lb_%A_%a.out

# Tier-1 real-fault study, JUNCTION block: carla_garage TransFuser++ run
# through carla_garage's OWN vendored leaderboard evaluator
# (leaderboard_evaluator_local.py) by lb_worker.py, one route per job, fresh
# evaluator process per run, against this task's external CARLA server.
# Same server loop + port probe as tfpp_campaign.slurm; PYTHONPATH uses the
# carla_garage leaderboard/scenario_runner INSTEAD of ~/transfuser_repo's.
# Submit: JOBS_FILE=... sbatch --array=0-3 tfpp_lb_campaign.slurm
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

TFPP=~/satrp_real/tfpp
GARAGE=$TFPP/carla_garage
CARLA_ROOT=~/carla_09101
VENV=~/tfuse_venv
SIF=~/sifs/python37full.sif
EGG=$(ls $CARLA_ROOT/PythonAPI/carla/dist/carla-*-py3.7-linux-x86_64.egg)
LOGS=/home/users/bhamadou/satrp_real/tfpp/logs
TFPP_CKPT=${TFPP_CKPT:-/home/users/bhamadou/satrp_real/tfpp/ckpt/pretrained_models/longest6/tfpp_all_0}

GPUCOMP=$(ls /usr/lib64/libnvidia-gpucomp.so.* | head -1)
echo "=== lb task $TASK/$NTASK port $PORT tm $TM_PORT (gpucomp: $GPUCOMP) ckpt $TFPP_CKPT ==="
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

# sensor_agent inference env as in the host smoke (README longest6 defaults);
# SAVE_PATH unset; BENCHMARK=longest6 -> deterministic 500 background
# vehicles (unset = unseeded random.randint(130,260) in the fork).
# TF_LIDAR_LEADERBOARD is irrelevant here: the evaluator's own agent_wrapper
# builds the leaderboard sensors.
singularity exec --nv \
  --bind /scratch,$CARLA_ROOT,$HOME \
  $SIF env -u SAVE_PATH \
  PYTHONPATH=$EGG:$CARLA_ROOT/PythonAPI/carla:$GARAGE/leaderboard:$GARAGE/scenario_runner \
  LD_LIBRARY_PATH=$HOME/carla_libs:/.singularity.d/libs \
  CARLA_ROOT=$CARLA_ROOT \
  SCENARIO_RUNNER_ROOT=$GARAGE/scenario_runner LEADERBOARD_ROOT=$GARAGE/leaderboard \
  TF_CKPT=$TFPP_CKPT TF_AGENT_NAME=tfpp_lb1 \
  SLOWER=1 DIRECT=1 UNCERTAINTY_WEIGHT=1 UNCERTAINTY_THRESHOLD=0.33 \
  STOP_CONTROL=0 TP_STATS=0 DEBUG_CHALLENGE=0 \
  LB_BENCHMARK=${LB_BENCHMARK:-longest6} \
  LB_JOB_TIMEOUT=${LB_JOB_TIMEOUT:-2400} \
  LB_MIN_ROUTE_TIMEOUT=${LB_MIN_ROUTE_TIMEOUT:-} \
  CARLA_PORT=$PORT LB_TM_PORT=$TM_PORT \
  CARLA_EXTERNAL=1 \
  LB_VIDEO_DIR=${LB_VIDEO_DIR:-} \
  $VENV/bin/python $TFPP/lb_worker.py $JOBS_FILE $TASK $NTASK
pkill -u $USER -f "carla-rpc-port=$PORT" 2>/dev/null || true
if [ -n "${LB_VIDEO_DIR:-}" ]; then ~/satrp_real/tools/encode_videos.sh "$LB_VIDEO_DIR" "$LB_VIDEO_DIR/../videos"; fi
echo "=== lb task $TASK done ==="
