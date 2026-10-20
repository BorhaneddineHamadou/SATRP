"""Leaderboard-evaluator worker for the TF++ junction block.

Runs its slice of a jobs file; each job = ONE route of a routes XML evaluated
once with carla_garage's own vendored leaderboard evaluator
(leaderboard/leaderboard/leaderboard_evaluator_local.py, the one
leaderboard/scripts/local_evaluation.sh uses) against the EXTERNAL CARLA
server of this task, in a fresh subprocess (lb_run_eval.py), with the
evaluator's stdout/stderr captured to <results_out>.log.

Job line: {job_id, route_id, routes_xml, scenarios_json, seed, team_code_dir,
           ckpt_dir, results_out, run_idx, [mutant{mid,site,md5}], [benchmark]}
The evaluator has no route-subset option, so a one-route XML is extracted per
job to <results_out dir>/routes/<job_id>.xml. ROUTES env is set to that file
(the evaluator derives its route_date_string from it). The job seed goes to
--trafficManagerSeed; NOTE the fork seeds CarlaDataProvider._rng with
config.index (= 0 for a one-route XML), so scenario-actor randomness is the
same for every run and only the TrafficManager seed varies with run_idx.

Deployment proof: the worker computes md5(team_code_dir/sensor_agent.py)
and requires the evaluator log's "[team_code] sensor_agent from <f> md5=<m>"
line (printed by lb_run_eval.py from sys.modules) to have f under
team_code_dir and m equal -> proof_ok.

Results: --checkpoint JSON at results_out, parsed with
~/satrp_real/routes/parse_lb_results.py if it exists (parse_checkpoint /
parse_lb_results / parse), else the built-in mapping (trigger = any collision
OR red_light OR outside_route_lanes OR route_dev; blocked / timeout separate;
scores, RC and infraction counts kept). One row per run appended to
<jobs>_task<N>.results.jsonl.

Usage: lb_worker.py JOBS_FILE [TASK NTASK]
Env: CARLA_PORT (default 2000+task*50), LB_TM_PORT (default CARLA_PORT+20),
LB_JOB_TIMEOUT s per attempt (default 2400), LB_EVALUATOR (path),
LB_BENCHMARK (default longest6: 500 background vehicles, deterministic; unset
BENCHMARK in the fork = random.randint(130,260) from an UNSEEDED rng),
LB_CLIENT_TIMEOUT (default 600), CARLA_EXTERNAL=1 (server managed by the
slurm restart loop; recycling = pkill by port).
"""
import hashlib
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
EVALUATOR = os.environ.get(
    "LB_EVALUATOR",
    f"{HOME}/satrp_real/tfpp/carla_garage/leaderboard/leaderboard/"
    "leaderboard_evaluator_local.py")
PARSER_PY = f"{HOME}/satrp_real/routes/parse_lb_results.py"
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


def _kill_external(port):
    subprocess.call(["pkill", "-u", os.environ.get("USER", ""),
                     "-f", f"carla-rpc-port={port}"])


def builtin_parse(checkpoint_json):
    """Built-in version of the parse_lb_results.py mapping."""
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
        route_length=meta.get("route_length"))


def parse_results(checkpoint_json):
    if os.path.exists(PARSER_PY):
        try:
            spec = importlib.util.spec_from_file_location("parse_lb_results", PARSER_PY)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for fn in ("parse_checkpoint", "parse_lb_results", "parse_results", "parse"):
                if hasattr(mod, fn):
                    out = getattr(mod, fn)(checkpoint_json)
                    if isinstance(out, dict):
                        out.setdefault("parser", f"parse_lb_results.{fn}")
                        return out
        except Exception as e:                      # noqa: BLE001
            print(f"[lb_worker] parse_lb_results.py failed ({e!r}); using builtin", flush=True)
    out = builtin_parse(checkpoint_json)
    out["parser"] = "builtin"
    return out


def check_proof(log_path, team_code_dir, expect_md5):
    pat = re.compile(r"\[team_code\] sensor_agent from (\S+) md5=([0-9a-f]{32})")
    found = None
    try:
        for line in open(log_path, errors="replace"):
            m = pat.search(line)
            if m:
                found = m.groups()
    except FileNotFoundError:
        pass
    if found is None:
        return False, None, None
    f, m = found
    ok = os.path.realpath(f).startswith(os.path.realpath(team_code_dir) + os.sep) and m == expect_md5
    return ok, f, m


def attempt(job, port, tm_port, timeout, log_path):
    results_out = job["results_out"]
    os.makedirs(os.path.dirname(results_out), exist_ok=True)
    if os.path.exists(results_out):
        os.remove(results_out)
    route_xml = one_route_xml(job["routes_xml"], job["route_id"],
                              os.path.join(os.path.dirname(results_out), "routes",
                                           f"{job['job_id']}.xml"))
    env = dict(os.environ)
    env.pop("SAVE_PATH", None)                       # never log/visualise (needs CarlaDataProvider hero)
    env.update(
        ROUTES=route_xml, SCENARIOS=job["scenarios_json"],
        CHALLENGE_TRACK_CODENAME="SENSORS", REPETITIONS="1", RESUME="0",
        DATAGEN="0", DEBUG_CHALLENGE=env.get("DEBUG_CHALLENGE", "0"),
        BENCHMARK=str(job.get("benchmark") or env.get("LB_BENCHMARK", "longest6")),
        TEAM_AGENT=os.path.join(job["team_code_dir"], "sensor_agent.py"),
        TEAM_CONFIG=job["ckpt_dir"], CHECKPOINT_ENDPOINT=results_out,
        PYTHONUNBUFFERED="1")
    cmd = [sys.executable, os.path.join(HERE, "lb_run_eval.py"), EVALUATOR,
           f"--routes={route_xml}", f"--scenarios={job['scenarios_json']}",
           "--repetitions=1", "--track=SENSORS",
           f"--checkpoint={results_out}",
           f"--agent={env['TEAM_AGENT']}", f"--agent-config={job['ckpt_dir']}",
           "--debug=0", f"--port={port}", f"--trafficManagerPort={tm_port}",
           f"--trafficManagerSeed={int(job['seed'])}",
           f"--timeout={os.environ.get('LB_CLIENT_TIMEOUT', '600')}"]
    # NOTE: --resume is argparse type=bool -> ANY string is True; it is omitted
    # on purpose (default False) and the checkpoint is removed above.
    with open(log_path, "w") as lf:
        lf.write("[lb_worker] cmd: " + " ".join(cmd) + "\n")
        lf.write(f"[lb_worker] expect sensor_agent md5={md5_file(env['TEAM_AGENT'])} "
                 f"team_code_dir={job['team_code_dir']} BENCHMARK={env['BENCHMARK']}\n")
        lf.flush()
        proc = subprocess.Popen(cmd, env=env, stdout=lf, stderr=subprocess.STDOUT,
                                preexec_fn=os.setsid)
        cam = None
        vid_dir = os.environ.get("LB_VIDEO_DIR")
        if vid_dir:                                   # chase-camera sidecar (2nd client)
            cam_out = os.path.join(vid_dir, job["job_id"])
            cam_log = open(cam_out + ".chasecam.log", "w")
            cam = subprocess.Popen(
                [sys.executable, os.path.join(HOME, "satrp_real/tools/chasecam.py"),
                 cam_out, "--port", str(port), "--wait", str(int(timeout))],
                env=env, stdout=cam_log, stderr=subprocess.STDOUT)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            lf.write("[lb_worker] STALL: killed after %.0fs\n" % timeout)
            return None
        finally:
            if cam is not None:
                try:
                    cam.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    cam.terminate()
                    try:
                        cam.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        cam.kill()
    return proc.returncode


def main():
    print("[lb_worker build 2026-10-13 one-route-per-job, fresh evaluator process]", flush=True)
    jobs_file = sys.argv[1]
    task = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    ntask = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    port = int(os.environ.get("CARLA_PORT", 2000 + task * 50))
    tm_port = int(os.environ.get("LB_TM_PORT", port + 20))
    timeout = float(os.environ.get("LB_JOB_TIMEOUT", 2400))
    jobs = [json.loads(l) for l in open(jobs_file) if l.strip()]
    mine = jobs[task::ntask]
    res_path = jobs_file.replace(".jsonl", f"_task{task}.results.jsonl")
    external = bool(os.environ.get("CARLA_EXTERNAL"))
    print(f"[lb_worker] task {task}/{ntask}: {len(mine)} jobs, port {port}, tm {tm_port}, "
          f"evaluator {EVALUATOR}", flush=True)

    def recycle():
        if external:
            _kill_external(port)
            time.sleep(60.0)
        else:
            print("[lb_worker] no external server loop; cannot recycle", flush=True)

    for job in mine:
        results_out = job["results_out"]
        if os.path.exists(results_out) and os.path.exists(results_out + ".row.json"):
            continue
        t0 = time.time()
        log_path = results_out + ".log"
        expect = md5_file(os.path.join(job["team_code_dir"], "sensor_agent.py"))
        rc = attempt(job, port, tm_port, timeout, log_path)
        if rc is None or rc != 0 or not os.path.exists(results_out):
            print(f"[lb_worker] {job['job_id']} "
                  f"{'stalled' if rc is None else f'rc={rc} ckpt_exists={os.path.exists(results_out)}'}"
                  "; recycling server and retrying once", flush=True)
            recycle()
            rc = attempt(job, port, tm_port, timeout, log_path)
            if rc is None:
                recycle()
        outcome = "stall" if rc is None else ("ok" if rc == 0 else f"error:exit{rc}")
        proof_ok, agent_file, agent_md5 = check_proof(log_path, job["team_code_dir"], expect)
        row = dict(job_id=job["job_id"], route_id=job["route_id"],
                   run_idx=job.get("run_idx"), seed=job.get("seed"),
                   vid=(job.get("mutant") or {}).get("mid"),
                   outcome=outcome, proof_ok=bool(proof_ok), agent_file=agent_file,
                   agent_md5=agent_md5, expected_md5=expect,
                   wall_s=round(time.time() - t0, 1), log=log_path,
                   checkpoint=results_out if os.path.exists(results_out) else None)
        if os.path.exists(results_out):
            try:
                row.update(parse_results(results_out))
            except Exception as e:                  # noqa: BLE001
                row["parse_error"] = repr(e)
        with open(results_out + ".row.json", "w") as f:
            json.dump(row, f)
        with open(res_path, "a") as f:
            f.write(json.dumps(row) + "\n")
        print(f"[lb_worker] {job['job_id']}: {outcome} status={row.get('status')} "
              f"RC={row.get('score_route')} trigger={row.get('trigger')} "
              f"blocked={row.get('blocked')} proof_ok={proof_ok} ({row['wall_s']:.0f}s)",
              flush=True)


if __name__ == "__main__":
    main()
