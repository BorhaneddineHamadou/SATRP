"""Pylot (ERDOSAgent) host plug-in for the carla_transfuser in-process harness.

Selected by env CH_AGENT_HOST=pylot_host (run_one.py hook). Provides the
same two names run_one.py takes from agent_host:

  SensorRig  -- agent_host.SensorRig + the leaderboard pseudo-sensor
                'sensor.opendrive_map' (input key -> (frame, {'opendrive': xodr}))
  load_agent(conf_path, world, route_locations) -> (agent, sensor_specs)

Env:
  TF_CKPT / PYLOT_CONF  base absl flagfile (challenge.conf style)
  TF_TEAM_CODE_DIR      per-job pylot SOURCE dir (run_one sets it from the
                        job field team_code_dir); inserted at sys.path[0]
                        before `import pylot` so the version is selected by
                        source dir inside one process (fresh process per job).
  CARLA_PORT            injected into the per-run conf as --simulator_port
                        (ERDOSBaseAgent opens its own client for the
                        perfect/simulator components).
  CH_OUTCOME_OUT        (set by worker.py) -> per-run log dir/prefix.
"""
import hashlib
import importlib
import os
import subprocess
import sys

import agent_host as _ah

HERE = os.path.dirname(os.path.abspath(__file__))
OPENDRIVE_TYPE = "sensor.opendrive_map"


class SensorRig(_ah.SensorRig):
    """agent_host.SensorRig + pseudo-sensors Pylot declares.

    The leaderboard's OpenDriveMapReader delivers {'opendrive': str} on
    every tick at reading_frequency; ERDOSAgent forwards it once and then
    closes its stream, so re-delivery is harmless and matches upstream.
    """

    def __init__(self, world, ego, sensor_specs):
        self._virtual = {}
        real = []
        for spec in sensor_specs:
            if spec["type"] == OPENDRIVE_TYPE:
                self._virtual[spec["id"]] = {
                    "opendrive": world.get_map().to_opendrive()}
            else:
                real.append(spec)
        super().__init__(world, ego, real)

    def tick(self, ego, frame, timeout=2.0):
        out = super().tick(ego, frame, timeout)
        for sid, payload in self._virtual.items():
            out[sid] = (frame, payload)
        return out


def _git_sha(d):
    try:
        return subprocess.check_output(
            ["git", "-C", d, "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "n/a"


def _per_run_conf(base_conf, port):
    """Copy the flagfile and append run-specific flags (port, log paths)."""
    ofile = os.environ.get("CH_OUTCOME_OUT")
    if ofile:
        prefix = ofile.replace(".npz.outcome.json", "").replace(
            ".outcome.json", "")
    else:
        prefix = os.path.join(os.getcwd(), "pylot_run")
    os.makedirs(os.path.dirname(prefix) or ".", exist_ok=True)
    out = prefix + ".pylot.conf"
    with open(base_conf) as f:
        lines = [l for l in f.read().splitlines()
                 if not l.startswith(("--simulator_port", "--simulator_host",
                                      "--log_file_name",
                                      "--csv_log_file_name",
                                      "--profile_file_name"))]
    lines += ["--simulator_host=localhost",
              "--simulator_port=%d" % port,
              "--log_file_name=%s.pylot.log" % prefix,
              "--csv_log_file_name=%s.pylot.csv" % prefix,
              "--profile_file_name=%s.pylot.profile.json" % prefix]
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    return out


def load_agent(conf_path, world, route_locations):
    """Instantiate Pylot's ERDOSAgent on `conf_path` with a dense global plan.

    Mirrors agent_host.load_agent: `agent = cls(conf)` (-> setup(), which
    parses the flagfile, builds the ERDOS dataflow and starts it with
    erdos.run_async()), then set_global_plan(gps_route, route).
    """
    # never let the TransFuser fork's leaderboard shadow the image's
    sys.path[:] = [p for p in sys.path if "transfuser_repo" not in p]
    src = os.environ.get("TF_TEAM_CODE_DIR") or os.environ.get("PYLOT_SRC")
    if src:
        src = os.path.expanduser(src)
        if src in sys.path:
            sys.path.remove(src)
        sys.path.insert(0, src)
    conf_path = os.path.expanduser(
        conf_path or os.environ.get("PYLOT_CONF", ""))
    if not os.path.isfile(conf_path):
        raise FileNotFoundError("pylot conf not found: %r" % conf_path)
    port = int(os.environ.get("CARLA_PORT", "2000"))
    run_conf = _per_run_conf(conf_path, port)

    import carla
    import erdos
    import pylot
    mod = importlib.import_module("pylot.simulation.challenge.ERDOSAgent")
    md5 = hashlib.md5(open(mod.__file__, "rb").read()).hexdigest()
    root = os.path.dirname(os.path.dirname(pylot.__file__))
    print("[pylot_host] pylot from %s (git %s) erdos %s ERDOSAgent md5=%s "
          "conf=%s" % (pylot.__file__, _git_sha(root),
                       getattr(erdos, "__version__", "?"), md5, run_conf),
          flush=True)
    cl = carla.Client("localhost", port)
    print("[pylot_host] carla client %s server %s" % (
        cl.get_client_version(), cl.get_server_version()), flush=True)
    del cl

    cls = getattr(mod, mod.get_entry_point())
    agent = cls(run_conf)                      # setup(): flags + dataflow
    from leaderboard.utils.route_manipulation import interpolate_trajectory
    gps_route, route = interpolate_trajectory(world, route_locations)
    agent.set_global_plan(gps_route, route)
    specs = agent.sensors()
    print("[pylot_host] track=%s sensors=%s" % (
        agent.track, [(s["type"], s["id"]) for s in specs]), flush=True)
    return agent, specs
