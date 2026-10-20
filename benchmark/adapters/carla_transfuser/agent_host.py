"""Minimal in-process host for the TransFuser leaderboard agent.

Replaces the leaderboard evaluator: builds the sensor rig from
agent.sensors(), collects sync-mode sensor packets into the
input_data dict format the AutonomousAgent API expects, feeds the
global plan, and returns one carla.VehicleControl per world tick.

Requires (worker PYTHONPATH): CARLA egg (py3.7),
~/transfuser_repo/leaderboard, ~/transfuser_repo/scenario_runner,
~/transfuser_repo/team_code_transfuser.
"""
import os
import sys
import importlib
import queue

import numpy as np

import carla
from leaderboard.utils.route_manipulation import interpolate_trajectory


class SensorRig:
    """Spawns the agent's declared sensors on the ego; sync collection."""

    GPS_TICK = ("sensor.other.gnss",)

    def __init__(self, world, ego, sensor_specs):
        self.world = world
        self.actors = []
        self.queues = {}
        self.last = {}      # last sample per sensor (scalar-sensor fallback)
        bp_lib = world.get_blueprint_library()
        for spec in sensor_specs:
            sid, stype = spec["id"], spec["type"]
            if stype == "sensor.speedometer":     # virtual, computed in tick
                self.queues[sid] = None
                continue
            bp = bp_lib.find(stype)
            for attr in ("width", "height", "fov"):
                if attr in spec:
                    bp.set_attribute("image_size_x" if attr == "width"
                                     else "image_size_y" if attr == "height"
                                     else "fov", str(spec[attr]))
            if stype == "sensor.lidar.ray_cast":
                # NOTE: these are NOT leaderboard 1.0's defaults, despite
                # the original comment. agent_wrapper.py sets
                # rotation_frequency=10 and four dropoff/attenuation
                # attributes we omit. At 20 FPS, freq 10 delivers a HALF
                # sweep per tick -- which is what TransFuser's training
                # data contains -- while freq 20 delivers a full 360 one,
                # and no dropoff makes the cloud far denser than training.
                # TF_LIDAR_LEADERBOARD=1 switches to the exact leaderboard
                # spec. Default is left unchanged so the existing campaign
                # stays reproducible.
                if os.environ.get("TF_LIDAR_LEADERBOARD") == "1":
                    lidar_attrs = (
                        ("rotation_frequency", "10"),
                        ("points_per_second", "600000"),
                        ("channels", "64"), ("range", "85"),
                        ("upper_fov", "10"), ("lower_fov", "-30"),
                        ("atmosphere_attenuation_rate", "0.004"),
                        ("dropoff_general_rate", "0.45"),
                        ("dropoff_intensity_limit", "0.8"),
                        ("dropoff_zero_intensity", "0.4"))
                else:
                    lidar_attrs = (("rotation_frequency", "20"),
                                   ("points_per_second", "600000"),
                                   ("channels", "64"), ("range", "85"),
                                   ("upper_fov", "10"), ("lower_fov", "-30"))
                for k, v in lidar_attrs:
                    if bp.has_attribute(k):
                        bp.set_attribute(k, v)
            if stype == "sensor.other.imu" and bp.has_attribute(
                    "sensor_tick"):
                # 0.0 = produce every world tick; sensor_tick == world delta
                # makes the IMU skip frames on float rounding (empty queue)
                bp.set_attribute("sensor_tick", "0.0")
            tf = carla.Transform(
                carla.Location(x=spec.get("x", 0.0), y=spec.get("y", 0.0),
                               z=spec.get("z", 0.0)),
                carla.Rotation(roll=spec.get("roll", 0.0),
                               pitch=spec.get("pitch", 0.0),
                               yaw=spec.get("yaw", 0.0)))
            actor = world.spawn_actor(bp, tf, attach_to=ego)
            q = queue.Queue()
            actor.listen(q.put)
            self.actors.append(actor)
            self.queues[sid] = (q, stype)

    def tick(self, ego, frame, timeout=2.0):
        """Returns input_data: {id: (frame, data)} in agent format."""
        out = {}
        for sid, entry in self.queues.items():
            if entry is None:                     # speedometer
                v = ego.get_velocity()
                out[sid] = (frame, {"speed": float(np.hypot(v.x, v.y))})
                continue
            q, stype = entry
            data = None
            while True:                            # drain to current frame
                try:
                    d = q.get(timeout=timeout)
                except queue.Empty:
                    break
                if d.frame >= frame:
                    data = d
                    break
                data = d
            if data is None:
                # scalar sensors may legitimately skip a frame; reuse last
                if stype in ("sensor.other.imu", "sensor.other.gnss") \
                        and sid in self.last:
                    out[sid] = (frame, self.last[sid])
                    continue
                raise RuntimeError(f"sensor {sid} produced no data")
            conv = self._convert(data, stype)
            self.last[sid] = conv
            out[sid] = (data.frame, conv)
        return out

    @staticmethod
    def _convert(d, stype):
        if stype == "sensor.camera.rgb":
            a = np.frombuffer(d.raw_data, dtype=np.uint8)
            return a.reshape((d.height, d.width, 4)).copy()
        if stype == "sensor.lidar.ray_cast":
            a = np.frombuffer(d.raw_data, dtype=np.float32)
            return a.reshape((-1, 4)).copy()
        if stype == "sensor.other.imu":
            return np.array(
                [d.accelerometer.x, d.accelerometer.y, d.accelerometer.z,
                 d.gyroscope.x, d.gyroscope.y, d.gyroscope.z, d.compass],
                dtype=np.float64)
        if stype == "sensor.other.gnss":
            return np.array([d.latitude, d.longitude, d.altitude],
                            dtype=np.float64)
        return d

    def destroy(self):
        for a in self.actors:
            try:
                a.stop()
                a.destroy()
            except RuntimeError:
                pass


def load_agent(ckpt_dir, world, route_locations):
    """Instantiate HybridAgent with checkpoint dir + dense global plan.

    route_locations: list of carla.Location along the ego lane
    (LanePath.pose points work). Returns (agent, sensor_specs).
    """
    # SA-TRP mutation campaign: a mutant copy of team_code_transfuser can be
    # selected per job via TF_TEAM_CODE_DIR (absent = stock repo, unchanged).
    _tc = os.environ.get("TF_TEAM_CODE_DIR")
    if _tc:
        sys.path.insert(0, _tc)
    # Tier-1 real-fault study (2026-10-13): TF_AGENT_MODULE selects the
    # agent module inside TF_TEAM_CODE_DIR (e.g. "sensor_agent" for the
    # carla_garage TransFuser++). Absent = "submission_agent", unchanged.
    _agent_mod = os.environ.get("TF_AGENT_MODULE", "submission_agent")
    mod = importlib.import_module(_agent_mod)
    import hashlib as _hl
    _md5 = _hl.md5(open(mod.__file__, "rb").read()).hexdigest()
    print(f"[team_code] {_agent_mod} from {mod.__file__} md5={_md5}", flush=True)
    for _m in ("model", "config"):
        _mm = sys.modules.get(_m)
        if _mm is not None and getattr(_mm, "__file__", None):
            print(f"[team_code] {_m} from {_mm.__file__} md5="
                  f"{_hl.md5(open(_mm.__file__, 'rb').read()).hexdigest()}", flush=True)
    cls = getattr(mod, mod.get_entry_point())
    agent = cls(ckpt_dir)                          # calls setup()
    gps_route, route = interpolate_trajectory(world, route_locations)
    # SMOKE: 2022 fork signature — set_global_plan(global_plan_gps,
    # global_plan_world_coord); verify downsampling inside the agent.
    agent.set_global_plan(gps_route, route)
    return agent, agent.sensors()
