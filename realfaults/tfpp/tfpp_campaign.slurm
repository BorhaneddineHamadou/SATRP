#!/bin/bash
#SBATCH --job-name=satrp_tfpp
#SBATCH --partition=gpuv100,gpup6000,classicgpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=48:00:00
#SBATCH --exclude=node27
#SBATCH --output=/home/users/bhamadou/satrp_real/tfpp/logs/tfpp_%A_%a.out

# Tier-1 real-fault study: carla_garage TransFuser++ (leaderboard_1) in the
# Proxima in-process CARLA host. Copy of
# ~/satrp_mutation/ads/slurm/tf_campaign.slurm (2026-10-13) with: logs under
# ~/satrp_real/tfpp/logs, the TF++ Longest6 checkpoint, TF_AGENT_MODULE=
# sensor_agent, TF_AGENT_NAME=tfpp_lb1, the leaderboard lidar spec, and the
# sensor_agent inference env (README defaults for the longest6 model).
# Array task N runs its slice of $JOBS_FILE against its own CARLA server
# (port spaced by 50 so tasks can share a node). The per-job team_code_dir
# in the jobs file selects the version (base / v_lidar_stale / v_speed_offset).
# Submit: JOBS_FILE=... sbatch --array=0-3 tfpp_campaign.slurm
set -u
: "${JOBS_FILE:?set JOBS_FILE=<path to jobs jsonl>}"
TASK=${SLURM_ARRAY_TASK_ID:-0}
# NTASK_OVERRIDE lets a partial resubmission (e.g. --array=23-28) keep the
# original slice stride instead of SLURM_ARRAY_TASK_COUNT of the new array.
NTASK=${NTASK_OVERRIDE:-${SLURM_ARRAY_TASK_COUNT:-1}}
# Port: hash the job id for a starting slot, then probe forward until a slot whose
# rpc port AND streaming port (+1) are both free on this node (2026-10-02: two
# tasks whose job ids differed by exactly 120 hashed to the same port and
# shared one CARLA server for 15 h -> 431 error rows).
PORT_SLOT=$((SLURM_JOB_ID % 120))
for k in $(seq 0 119); do
  P=$((2000 + ((PORT_SLOT + k) % 120) * 50))
  if ! ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE ":($P|$((P+1)))$" \
     && ! pgrep -u $USER -f "carla-rpc-port=$P\b" >/dev/null; then PORT=$P; break; fi
done
: "${PORT:?no free CARLA port found}"

ADAPTER=~/proxima/adapters/carla_transfuser
CARLA_ROOT=~/carla_09101
VENV=~/tfuse_venv
SIF=~/sifs/python37full.sif
EGG=$(ls $CARLA_ROOT/PythonAPI/carla/dist/carla-*-py3.7-linux-x86_64.egg)
LOGS=/home/users/bhamadou/satrp_real/tfpp/logs
TFPP_CKPT=${TFPP_CKPT:-/home/users/bhamadou/satrp_real/tfpp/ckpt/pretrained_models/longest6/tfpp_all_0}

# CARLA server with the libnvidia-gpucomp --nv workaround + restart loop
GPUCOMP=$(ls /usr/lib64/libnvidia-gpucomp.so.* | head -1)
echo "=== task $TASK/$NTASK port $PORT (gpucomp: $GPUCOMP) ckpt $TFPP_CKPT ==="
(while true; do
  singularity exec --nv \
    --bind "$GPUCOMP":/nvidia_extra/$(basename "$GPUCOMP") \
    ~/sifs/carla09101.sif /bin/bash -c \
    "export LD_LIBRARY_PATH=/nvidia_extra:/.singularity.d/libs:\$LD_LIBRARY_PATH
     DISPLAY= SDL_VIDEODRIVER=offscreen /home/carla/CarlaUE4.sh -opengl \
     -nosound -carla-rpc-port=$PORT -quality-level=Epic"
  echo "[server-loop] CARLA exited $? -- restarting in 5s"
  sleep 5
done) > $LOGS/server_${SLURM_ARRAY_JOB_ID:-0}_${TASK}.log 2>&1 &
sleep 45

# sensor_agent.py inference env (carla_garage README: longest6 model needs
# UNCERTAINTY_THRESHOLD=0.33; "other options are correctly set by default":
# SLOWER=1 DIRECT=1 UNCERTAINTY_WEIGHT=1 STOP_CONTROL=0 TP_STATS=0
# DEBUG_CHALLENGE=0). SAVE_PATH must be UNSET: when set, _init() reaches for
# CarlaDataProvider, which our host never populates. TF_LIDAR_LEADERBOARD=1
# gives the leaderboard lidar spec (rotation_frequency 10 = half sweep per
# 20 FPS tick + dropoff attrs) that TF++ was trained on and whose half-sweep
# concatenation sensor_agent.run_step assumes.
singularity exec --nv \
  --bind /scratch,$CARLA_ROOT,$HOME \
  $SIF env -u SAVE_PATH \
  PYTHONPATH=$EGG:$CARLA_ROOT/PythonAPI/carla:~/transfuser_repo/leaderboard:~/transfuser_repo/scenario_runner:~/transfuser_repo/team_code_transfuser:$ADAPTER \
  LD_LIBRARY_PATH=$HOME/carla_libs:/.singularity.d/libs \
  CARLA_ROOT=$CARLA_ROOT \
  TF_CKPT=$TFPP_CKPT \
  TF_AGENT_MODULE=sensor_agent \
  TF_AGENT_NAME=tfpp_lb1 \
  TF_LIDAR_LEADERBOARD=1 \
  SLOWER=1 DIRECT=1 UNCERTAINTY_WEIGHT=1 UNCERTAINTY_THRESHOLD=0.33 \
  STOP_CONTROL=0 TP_STATS=0 DEBUG_CHALLENGE=0 \
  CARLA_PORT=$PORT \
  CARLA_EXTERNAL=1 \
  CH_VIDEO_DIR=${CH_VIDEO_DIR:-} \
  PROXIMA_ABORT_MUTANT=${PROXIMA_ABORT_MUTANT:-0} \
  $VENV/bin/python $ADAPTER/worker.py $JOBS_FILE $TASK $NTASK
pkill -u $USER -f "carla-rpc-port=$PORT" 2>/dev/null || true
if [ -n "${CH_VIDEO_DIR:-}" ]; then ~/satrp_real/tools/encode_videos.sh "$CH_VIDEO_DIR" "$CH_VIDEO_DIR/../videos"; fi
echo "=== task $TASK done ==="
