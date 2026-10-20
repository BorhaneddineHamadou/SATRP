#!/usr/bin/env python3
"""Leaderboard-evaluator worker for the Pylot real-fault block (host python3).

Adapted from ~/satrp_real/tfpp/lb_worker.py.  Runs its slice of a jobs file;
each job = ONE route of a leaderboard-1.0 routes XML evaluated once with the
leaderboard evaluator SHIPPED IN THE PYLOT IMAGE
(~/sifs/pylot_challenge.sif: /workspace/leaderboard/leaderboard/leaderboard_evaluator.py)
against the EXTERNAL CARLA 0.9.10.1 server of this task (same server loop as
the TF++ block), in a fresh `singularity exec` subprocess running
~/satrp_real/tfpp/lb_run_eval.py (reused as-is: it runs the evaluator via
runpy and prints "[team_code] <module> from <file> md5=<m>" proof lines for
the modules in env PROOF_MODULES at exit).  stdout+stderr -> <results_out>.log.

Job line (gen_jobs_lb.py): {job_id, route_id, route_index, scenario_class,
  town, routes_xml, scenarios_json, seed, run_idx, vid, status, pylot_dir,
  conf, proof_files{file: md5_version}, difftrace_required, results_out}

Version selection = bind-mount the version's PACKAGE over the image's:
  --bind <pylot_dir>:/workspace/team_code/pylot   (models/deps stay from image)
Agent = /workspace/team_code/pylot/simulation/challenge/ERDOSAgent.py;
agent-config = per-run copy of <conf> (= the VERSION tree's challenge.conf;
v_speed7 differs only there) with --simulator_host/--simulator_port stripped
and re-appended for this task's port, and ABSOLUTE --log_file_name /
--csv_log_file_name / --profile_file_name inside the run dir
(dirname(results_out)/<job_id>/, also the container cwd).

Deployment proof (row fields):
  proof        {file: {expect_md5 (versions.json), host_md5 (deployed tree),
                       seen_file, seen_md5, ok}} for each PROOF module file
               + the version's changed files; v_speed7's changed file is the
               conf -> conf_target_speed / conf_ok (--target_speed=7 in the
               per-run conf) instead of a module line.
  difftrace_lines   count of "[difftrace <vid>]" lines in the log
  difftrace_instrumented  the deployed tree contains "[difftrace" (host grep)
  difftrace_required      job.difftrace_required (status == ready) AND instrumented
  proof_ok     every changed file: seen path under /workspace/team_code/pylot/,
               seen md5 == host md5 of the deployed file, and (unless the tree
               is instrumented, which changes the file) == versions.json
               md5_version; AND conf_ok; AND (difftrace_lines > 0 if required).
  NOTE 2026-10-13: the version trees are NOT difftrace-instrumented (the
  .difftrace.patch files are shipped separately; md5_version is the md5 of the
  un-instrumented file), so difftrace_required is False everywhere for now and
  difftrace_lines is recorded only.  Apply the difftrace patches to a copy of
  the tree and point job.pylot_dir at it to turn the requirement on.

Results: --checkpoint JSON at results_out, parsed by builtin_parse (same
mapping as the TF++ worker: trigger = any collision OR red_light OR
outside_route_lanes OR route_dev; blocked / timeout separate; scores, RC and
infraction counts kept).  One row per run -> <results_out>.row.json and
appended to <jobs>_task<N>.results.jsonl.  A job is skipped when
<results_out>.row.json exists.

Usage: lb_worker.py JOBS_FILE [TASK NTASK]
Env: CARLA_PORT (default 2000+task*50), LB_TM_PORT (default CARLA_PORT+20),
LB_JOB_TIMEOUT s per attempt (default 3000; Pylot loads its TF models for
1-2 min), LB_CLIENT_TIMEOUT (default 600), CARLA_EXTERNAL=1 (server managed
by the slurm restart loop; recycling = pkill by port), LB_VIDEO_DIR (chase-
camera sidecar, run inside the pylot image too), PYLOT_SIF (image path).
"""
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
SIF = os.environ.get("PYLOT_SIF", f"{HOME}/sifs/pylot_challenge.sif")
RUN_EVAL = f"{HOME}/satrp_real/tfpp/lb_run_eval.py"          # reused as-is
CHASECAM = f"{HOME}/satrp_real/tools/chasecam.py"
USERLIB = f"{HOME}/satrp_real/pylot/image_userlib"
EVALUATOR = "/workspace/leaderboard/leaderboard/leaderboard_evaluator.py"
TEAM_PKG = "/workspace/team_code/pylot"                      # bind target
AGENT = f"{TEAM_PKG}/simulation/challenge/ERDOSAgent.py"
IMAGE_PYTHONPATH = ("/workspace/team_code/:/workspace/team_code/dependencies/:"
                    "/workspace/CARLA/PythonAPI/carla/dist/carla-leaderboard-py3x.egg:"
                    "/workspace/scenario_runner:/workspace/CARLA/PythonAPI/carla:"
                    "/workspace/leaderboard")
# image_userlib (py_trees, xmlschema, ... NO numpy) + the image's erdos build
# tree first: the image's own copies live under unreadable /root.
PYTHONPATH = f"{USERLIB}:/workspace/erdos/build/lib.linux-x86_64-3.7:{IMAGE_PYTHONPATH}"
PROOF_MODULES = ("pylot.planning.waypoints,pylot.planning.world,"
                 "pylot.planning.cost_functions,pylot.planning.planning_operator,"
                 "pylot.planning.behavior_planning_operator")
TRIGGER_KEYS = ("collisions_pedestrian", "collisions_vehicle",
                "collisions_layout", "red_light", "outside_route_lanes",
                "route_dev")
INFRACTION_KEYS = TRIGGER_KEYS + ("stop_infraction", "route_timeout",
                                  "vehicle_blocked")


def md5_file(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def one_route_xml(routes_xml, route_id, out_path):
    tree = ET.parse(routes_xml)
    root = tree.getroot()
    keep = [r for r in root.findall("route") if r.attrib.get("id") == str(route_id)]
    if len(keep) != 1:
        raise RuntimeError(f"route id {route_id!r} not unique/found in {routes_xml}: {len(keep)}")
    new_root = ET.Element("routes")
    new_root.append(keep[0])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    ET.ElementTree(new_root).write(out_path, encoding="UTF-8", xml_declaration=True)
    return out_path


def per_run_conf(base_conf, port, run_dir, job_id):
    """Copy the version's flagfile; strip host/port + log-path lines; append
    this run's port/host and ABSOLUTE log paths (Pylot writes them relative to
    cwd otherwise).  Returns the per-run conf path (host path == container path
    thanks to --bind $HOME)."""
    prefix = os.path.join(run_dir, job_id)
    out = prefix + ".pylot.conf"
    with open(base_conf) as f:
        lines = [l for l in f.read().splitlines()
                 if not l.startswith(("--simulator_port", "--simulator_host",
                                      "--log_file_name", "--csv_log_file_name",
                                      "--profile_file_name"))]
    lines += ["--simulator_host=localhost",
              "--simulator_port=%d" % port,
              "--log_file_name=%s.pylot.log" % prefix,
              "--csv_log_file_name=%s.pylot.csv" % prefix,
              "--profile_file_name=%s.pylot.profile.json" % prefix]
    os.makedirs(run_dir, exist_ok=True)
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    return out


def conf_target_speed(conf_path):
    ts = None
    for l in open(conf_path):
        l = l.strip()
        if l.startswith("--target_speed="):
            ts = l.split("=", 1)[1]
    return ts


def _kill_external(port):
    subprocess.call(["pkill", "-u", os.environ.get("USER", ""),
                     "-f", f"carla-rpc-port={port}"])


def builtin_parse(checkpoint_json):
    """Same mapping as the TF++ worker (leaderboard 1.0 checkpoint JSON)."""
    data = json.load(open(checkpoint_json))
    recs = (data.get("_checkpoint") or {}).get("records") or []
    if not recs:
        return dict(status="no_record", trigger=None, blocked=None, timeout=None)
    r = recs[-1]
    inf = r.get("infractions") or {}
    counts = {k: len(inf.get(k) or []) for k in INFRACTION_KEYS}
    sc = r.get("scores") or {}
    meta = r.get("meta") or {}
    return dict(
        status=r.get("status"),
        trigger=int(any(counts[k] > 0 for k in TRIGGER_KEYS)),
        blocked=int(counts["vehicle_blocked"] > 0),
        timeout=int(counts["route_timeout"] > 0),
        score_composed=sc.get("score_composed"),
        score_route=sc.get("score_route"),          # RC
        score_penalty=sc.get("score_penalty"),
        infractions=counts,
        infraction_msgs={k: inf.get(k) or [] for k in INFRACTION_KEYS if inf.get(k)},
        duration_game=meta.get("duration_game"),
        duration_system=meta.get("duration_system"),
        route_length=meta.get("route_length"),
        parser="builtin")


def tree_instrumented(pylot_dir):
    """True if any .py under the deployed package contains '[difftrace'."""
    for dp, _, fns in os.walk(pylot_dir):
        for fn in fns:
            if fn.endswith(".py"):
                try:
                    if b"[difftrace" in open(os.path.join(dp, fn), "rb").read():
                        return True
                except OSError:
                    pass
    return False


def file_to_module(rel):                 # pylot/planning/waypoints.py -> pylot.planning.waypoints
    return rel[:-3].replace("/", ".") if rel.endswith(".py") else None


def scan_log(log_path, vid):
    """-> ({module: (file, md5)}, difftrace_lines)."""
    pat = re.compile(r"\[team_code\] (\S+) from (\S+) md5=([0-9a-f]{32})")
    seen, n_dt = {}, 0
    tag = f"[difftrace {vid}]" if vid != "base" else "[difftrace "
    try:
        for line in open(log_path, errors="replace"):
            if tag in line:
                n_dt += 1
            m = pat.search(line)
            if m:
                seen[m.group(1)] = (m.group(2), m.group(3))
    except FileNotFoundError:
        pass
    return seen, n_dt


def check_proof(job, log_path, run_conf):
    vid = job["vid"]
    pylot_dir = job["pylot_dir"]
    pkg_root = os.path.dirname(pylot_dir.rstrip("/"))      # <version tree>/
    instrumented = tree_instrumented(pylot_dir)
    seen, n_dt = scan_log(log_path, vid)
    proof = {}
    changed = dict(job.get("proof_files") or {})
    files = list(changed)
    for mod in PROOF_MODULES.split(","):                   # always prove the 5 planning modules
        rel = mod.replace(".", "/") + ".py"
        if rel not in files:
            files.append(rel)
    ok_all = True
    for rel in files:
        mod = file_to_module(rel)
        host_p = os.path.join(pkg_root, rel)
        host_md5 = md5_file(host_p) if os.path.exists(host_p) else None
        expect = changed.get(rel)
        if mod is None or not rel.startswith("pylot/"):     # conf (v_speed7): checked below
            proof[rel] = dict(expect_md5=expect, host_md5=host_md5, kind="conf",
                              ok=(expect is None or expect == host_md5))
            if rel in changed and not proof[rel]["ok"]:
                ok_all = False
            continue
        sf, sm = seen.get(mod, (None, None))
        ok = (sf is not None and sf.startswith(TEAM_PKG + "/")
              and sf == f"/workspace/team_code/{rel}" and sm == host_md5
              and (instrumented or expect is None or sm == expect))
        proof[rel] = dict(module=mod, expect_md5=expect, host_md5=host_md5,
                          seen_file=sf, seen_md5=sm, ok=bool(ok))
        if rel in changed or job.get("vid") == "base":
            ok_all = ok_all and ok
    ts = conf_target_speed(run_conf) if os.path.exists(run_conf) else None
    conf_ok = (ts == "7") if vid == "v_speed7" else True
    required = bool(job.get("difftrace_required")) and instrumented
    proof_ok = ok_all and conf_ok and (n_dt > 0 if required else True)
    return dict(proof=proof, proof_ok=bool(proof_ok), conf_target_speed=ts,
                conf_ok=bool(conf_ok), difftrace_lines=n_dt,
                difftrace_instrumented=instrumented, difftrace_required=required,
                proof_modules_seen=sorted(seen))


# 2026-10-14: every obstacle_detection/*.pb inside pylot_challenge.sif is
# root-only (mode 600/700) -> the faster-rcnn DetectionOperator died with
# PermissionDenied at agent setup and every run stalled (OOM after 3000 s).
# The graph was recovered from the image's squashfs (unsquashfs, md5
# d5a3daff9b013f16aadfcd6d966df134) into models_fix/ and is bind-mounted over
# the unreadable directory.  Override with PYLOT_MODELS_FIX=<dir> or disable
# with PYLOT_MODELS_FIX=none.
MODELS_FIX = os.environ.get("PYLOT_MODELS_FIX",
                            f"{HOME}/satrp_real/pylot/models_fix/obstacle_detection/faster-rcnn")
MODELS_FIX_TARGET = "/workspace/team_code/dependencies/models/obstacle_detection/faster-rcnn"



# 2026-10-14: erdos.run_async() binds 127.0.0.1:<start_port>.. (11 nodes ->
# 22 ports, default block 9000) while the dataflow nodes shake hands; the
# listeners are dropped afterwards, so only two runs STARTING together on one
# host collide (smoke 765378: tasks 1+2 in lockstep on node30 -> "Address
# already in use"/"early eof", evaluator hung to the stall limit, twice).
# Every attempt now gets its own block, keyed on the raw SLURM job id and
# probed against current listeners; ERDOS_START_PORT=<n> forces a value.
ERDOS_PORT_BASE = int(os.environ.get("ERDOS_PORT_BASE", 20000))
ERDOS_PORT_STRIDE = 32
ERDOS_PORT_SLOTS = 300


def _listening_ports():
    try:
        out = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, timeout=10).stdout
    except Exception:                                   # noqa: BLE001
        return set()
    ports = set()
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4 and ":" in parts[3]:
            try:
                ports.add(int(parts[3].rsplit(":", 1)[1]))
            except ValueError:
                pass
    return ports


def erdos_start_port(task):
    forced = os.environ.get("ERDOS_START_PORT")
    if forced:
        return int(forced)
    busy = _listening_ports()
    # SLURM_ARRAY_JOB_ID is constant across an array; SLURM_JOB_ID is NOT monotone
    # in task order (task 0 may get id+1 and task 1 id), so JOB_ID+task collided.
    key = int(os.environ.get("SLURM_ARRAY_JOB_ID") or os.environ.get("SLURM_JOB_ID") or 0) + task
    for k in range(ERDOS_PORT_SLOTS):
        p = ERDOS_PORT_BASE + ((key + k) % ERDOS_PORT_SLOTS) * ERDOS_PORT_STRIDE
        if not any(q in busy for q in range(p, p + ERDOS_PORT_STRIDE)):
            return p
    return ERDOS_PORT_BASE + (key % ERDOS_PORT_SLOTS) * ERDOS_PORT_STRIDE

def _popen_in_image(cmd_in_image, pylot_dir, cwd, env_kv, logf, nv):
    extra_binds = []
    if MODELS_FIX and MODELS_FIX != "none" and os.path.isdir(MODELS_FIX):
        extra_binds = ["--bind", f"{MODELS_FIX}:{MODELS_FIX_TARGET}"]
    cmd = ["singularity", "exec"] + (["--nv"] if nv else []) + [
        "--cleanenv", "--bind", HOME, "--bind", f"{pylot_dir}:{TEAM_PKG}"] + extra_binds + [
        "--pwd", cwd, SIF, "env"] + [f"{k}={v}" for k, v in env_kv.items()] + cmd_in_image
    logf.write("[lb_worker] cmd: " + " ".join(cmd) + "\n")
    logf.flush()
    return subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT,
                            preexec_fn=os.setsid), cmd


def _killpg(proc):
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def attempt(job, port, tm_port, timeout, log_path):
    results_out = job["results_out"]
    run_dir = os.path.join(os.path.dirname(results_out), job["job_id"])
    os.makedirs(run_dir, exist_ok=True)
    if os.path.exists(results_out):
        os.remove(results_out)
    route_xml = one_route_xml(job["routes_xml"], job["route_id"],
                              os.path.join(run_dir, f"{job['job_id']}.xml"))
    run_conf = per_run_conf(job["conf"], port, run_dir, job["job_id"])
    env_kv = dict(
        PYTHONPATH=PYTHONPATH, PYTHONUNBUFFERED="1", PROOF_MODULES=PROOF_MODULES,
        PYLOT_DIFFTRACE="1", ROUTES=route_xml, SCENARIOS=job["scenarios_json"],
        ERDOS_START_PORT=str(erdos_start_port(int(os.environ.get("SLURM_ARRAY_TASK_ID", "0") or 0))),
        TEAM_AGENT=AGENT, TEAM_CONFIG=run_conf, CHECKPOINT_ENDPOINT=results_out,
        CHALLENGE_TRACK_CODENAME="MAP", REPETITIONS="1",
        LEADERBOARD_ROOT="/workspace/leaderboard",
        SCENARIO_RUNNER_ROOT="/workspace/scenario_runner", CARLA_ROOT="/workspace/CARLA",
        # forwarded to lb_run_eval.py (--cleanenv drops the host env); empty = stock timeout
        LB_MIN_ROUTE_TIMEOUT=os.environ.get("LB_MIN_ROUTE_TIMEOUT", ""))
    ev = ["python3", RUN_EVAL, EVALUATOR,
          f"--routes={route_xml}", f"--scenarios={job['scenarios_json']}",
          "--repetitions=1", "--track=MAP", f"--checkpoint={results_out}",
          f"--agent={AGENT}", f"--agent-config={run_conf}",
          "--debug=0", f"--port={port}", f"--trafficManagerPort={tm_port}",
          f"--trafficManagerSeed={int(job['seed'])}",
          f"--timeout={os.environ.get('LB_CLIENT_TIMEOUT', '600')}"]
    # NOTE: --resume is argparse type=bool -> ANY string is True; omitted on
    # purpose (default False) and the checkpoint is removed above.
    with open(log_path, "w") as lf:
        lf.write(f"[lb_worker] job {job['job_id']} vid={job['vid']} pylot_dir={job['pylot_dir']} "
                 f"conf={job['conf']} run_conf={run_conf} target_speed={conf_target_speed(run_conf)} "
                 f"expect={json.dumps(job.get('proof_files') or {})}\n")
        proc, _ = _popen_in_image(ev, job["pylot_dir"], run_dir, env_kv, lf, nv=True)
        cam = None
        vid_dir = os.environ.get("LB_VIDEO_DIR")
        if vid_dir:                                   # chase-camera sidecar (2nd client)
            os.makedirs(vid_dir, exist_ok=True)
            cam_out = os.path.join(vid_dir, job["job_id"])
            cam_log = open(cam_out + ".chasecam.log", "w")
            cam, _ = _popen_in_image(
                ["python3", CHASECAM, cam_out, "--port", str(port), "--wait", str(int(timeout))],
                job["pylot_dir"], run_dir, dict(PYTHONPATH=PYTHONPATH, PYTHONUNBUFFERED="1"),
                cam_log, nv=False)
        stalled = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _killpg(proc)
            proc.wait()
            lf.write("[lb_worker] STALL: killed after %.0fs\n" % timeout)
            stalled = True
        finally:
            _killpg(proc)                             # reap stray erdos operator processes
            subprocess.call(["pkill", "-u", os.environ.get("USER", ""), "-f", run_conf])
            if cam is not None:
                try:
                    cam.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    cam.terminate()
                    try:
                        cam.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        cam.kill()
                cam_log.close()
    return (None if stalled else proc.returncode), run_conf


def main():
    print("[lb_worker pylot build 2026-10-13 one-route-per-job, fresh evaluator "
          "process inside pylot_challenge.sif]", flush=True)
    jobs_file = sys.argv[1]
    task = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    ntask = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    port = int(os.environ.get("CARLA_PORT", 2000 + task * 50))
    tm_port = int(os.environ.get("LB_TM_PORT", port + 20))
    timeout = float(os.environ.get("LB_JOB_TIMEOUT", 3000))
    jobs = [json.loads(l) for l in open(jobs_file) if l.strip()]
    mine = jobs[task::ntask]
    res_path = jobs_file.replace(".jsonl", f"_task{task}.results.jsonl")
    external = bool(os.environ.get("CARLA_EXTERNAL"))
    for p in (SIF, RUN_EVAL, USERLIB):
        if not os.path.exists(p):
            sys.exit(f"[lb_worker] missing {p}")
    print(f"[lb_worker] task {task}/{ntask}: {len(mine)} jobs, port {port}, tm {tm_port}, "
          f"sif {SIF}, video={os.environ.get('LB_VIDEO_DIR') or '-'}", flush=True)

    def recycle():
        if external:
            _kill_external(port)
            time.sleep(60.0)
        else:
            print("[lb_worker] no external server loop; cannot recycle", flush=True)

    for job in mine:
        results_out = job["results_out"]
        if os.path.exists(results_out + ".row.json"):
            continue
        if not os.path.isdir(job["pylot_dir"]) or not os.path.isfile(job["conf"]):
            print(f"[lb_worker] {job['job_id']}: missing pylot_dir/conf; skipped", flush=True)
            continue
        t0 = time.time()
        log_path = results_out + ".log"
        os.makedirs(os.path.dirname(results_out), exist_ok=True)
        rc, run_conf = attempt(job, port, tm_port, timeout, log_path)
        if rc is None or rc != 0 or not os.path.exists(results_out):
            print(f"[lb_worker] {job['job_id']} "
                  f"{'stalled' if rc is None else f'rc={rc} ckpt_exists={os.path.exists(results_out)}'}"
                  "; recycling server and retrying once", flush=True)
            recycle()
            shutil.copy(log_path, log_path + ".attempt1")
            rc, run_conf = attempt(job, port, tm_port, timeout, log_path)
            if rc is None:
                recycle()
        outcome = "stall" if rc is None else ("ok" if rc == 0 else f"error:exit{rc}")
        pr = check_proof(job, log_path, run_conf)
        row = dict(job_id=job["job_id"], route_id=job["route_id"],
                   route_index=job.get("route_index"), scenario_class=job.get("scenario_class"),
                   town=job.get("town"), run_idx=job.get("run_idx"), seed=job.get("seed"),
                   vid=job["vid"], status_version=job.get("status"),
                   pylot_dir=job["pylot_dir"], conf_path=run_conf,
                   outcome=outcome, wall_s=round(time.time() - t0, 1), log=log_path,
                   checkpoint=results_out if os.path.exists(results_out) else None)
        row.update(pr)
        if os.path.exists(results_out):
            try:
                row.update(builtin_parse(results_out))
            except Exception as e:                  # noqa: BLE001
                row["parse_error"] = repr(e)
        with open(results_out + ".row.json", "w") as f:
            json.dump(row, f)
        with open(res_path, "a") as f:
            f.write(json.dumps(row) + "\n")
        print(f"[lb_worker] {job['job_id']}: {outcome} status={row.get('status')} "
              f"RC={row.get('score_route')} trigger={row.get('trigger')} "
              f"blocked={row.get('blocked')} proof_ok={row['proof_ok']} "
              f"difftrace={row['difftrace_lines']} ({row['wall_s']:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
