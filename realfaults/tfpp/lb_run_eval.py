"""Runs carla_garage's vendored leaderboard evaluator in THIS process and, on
exit, prints the deployment proof the in-process host prints via agent_host:

  [team_code] sensor_agent from <file> md5=<md5>
  [team_code] model from <file> md5=...
  [team_code] config from <file> md5=...

The evaluator itself never prints the agent path (it only prints the .pth
paths), so the proof is taken from sys.modules after the run: the module the
evaluator actually imported (it inserts dirname(--agent) at sys.path[0]).

Usage: lb_run_eval.py <evaluator.py> <evaluator args...>
"""
import hashlib
import runpy
import sys


def _proof(name):
    m = sys.modules.get(name)
    f = getattr(m, "__file__", None) if m is not None else None
    if not f:
        print(f"[team_code] {name} NOT IMPORTED", flush=True)
        return
    md5 = hashlib.md5(open(f, "rb").read()).hexdigest()
    print(f"[team_code] {name} from {f} md5={md5}", flush=True)


def _apply_route_timeout_floor():
    """LB_MIN_ROUTE_TIMEOUT=<seconds>: floor on the leaderboard's per-route
    timeout (default 0.8 s/m + 5 s -> only ~50 s on the 55-61 m s4/s8/s9
    junction routes; TF++ waits at the junction and needs ~65-70 s, so every
    version timed out at 93-95 % route completion in the 2026-10-13 smoke).
    Applied identically to both stacks and all versions; unset = stock."""
    import os
    raw = os.environ.get("LB_MIN_ROUTE_TIMEOUT", "").strip()
    if not raw:
        return
    floor = float(raw)
    import importlib
    applied = []
    # carla_garage's leaderboard_evaluator_local.py imports route_scenario_local;
    # the stock evaluator (Pylot image) imports route_scenario. Patch every one
    # that exists so the floor holds whichever the evaluator uses.
    for modname in ("leaderboard.scenarios.route_scenario",
                    "leaderboard.scenarios.route_scenario_local"):
        try:
            rs = importlib.import_module(modname)
        except Exception:                        # noqa: BLE001 - module absent in this tree
            continue
        orig = rs.RouteScenario._estimate_route_timeout

        def _floored(self, _orig=orig):
            return int(max(_orig(self), floor))

        rs.RouteScenario._estimate_route_timeout = _floored
        applied.append(rs.__file__)
    if applied:
        print(f"[lb_eval] route timeout floor {floor:.0f}s applied ({', '.join(applied)})", flush=True)
    else:
        print("[lb_eval] route timeout floor NOT applied (no route_scenario module importable)", flush=True)


def main():
    evaluator = sys.argv[1]
    sys.argv = [evaluator] + sys.argv[2:]
    rc = 0
    try:
        _apply_route_timeout_floor()
        runpy.run_path(evaluator, run_name="__main__")
    except SystemExit as e:
        rc = int(e.code or 0) if isinstance(e.code, int) or e.code is None else 1
    except BaseException:                      # noqa: BLE001 - report, then re-raise
        import traceback
        traceback.print_exc()
        rc = 1
    finally:
        import os
        names = os.environ.get("PROOF_MODULES", "sensor_agent,model,config").split(",")
        for name in [n.strip() for n in names if n.strip()]:
            _proof(name)
        print(f"[lb_eval] evaluator finished rc={rc}", flush=True)
    sys.exit(rc)


if __name__ == "__main__":
    main()
