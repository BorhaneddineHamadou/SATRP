# Pylot Tier-2 real-fault versions (base = challenge head 8218ca9)

Built 2026-10-13 from a private clone at `~/satrp_real/pylot/versions/_repo` (checked out at 8218ca9, detached). Base tree: `~/satrp_real/pylot/versions/base/` (= `git archive 8218ca9`). Each version `<vid>/` is a full copy of the base tree with `<vid>.patch` applied; `diff -r base <vid>` touches exactly the files listed below. All `<vid>.patch` files pass `git apply --check` on a clean 8218ca9 checkout; all `<vid>.difftrace.patch` files pass `git apply --check` on BOTH `base/` and `<vid>/` and py-compile after application.

Difftrace: one guarded statement (`PYLOT_DIFFTRACE=1`, prefix `[difftrace <vid>]`, written to stderr) inserted at a location whose context is identical in base and version. Deployment proof for a run = md5 of the changed file(s) (table below) + the difftrace lines differing between the base run and the version run on the same scenario. Identical difftrace output on a scenario means the mechanism did not fire there.

## Execution-path facts at 8218ca9 (default challenge.conf)

- `--execution_mode=challenge-map` -> Track.MAP -> OpenDRIVE map is received, so `World._map` and `BehaviorPlanningOperator._map` are set (all `are_on_same_lane` / junction logic is live).
- Perception: faster-rcnn obstacle detection + SORT tracking + LiDAR location finder -> `ObstacleLocationHistoryOperator` -> **linear prediction** (10 past / 30 future steps) -> `PlanningOperator`. Camera TL detector + location finder -> static obstacles. GT conf (`--simulator_obstacle_detection --perfect_obstacle_tracking --perfect_localization`) replaces only the detection/tracking/pose sources; prediction, behaviour planner, `World`, planner and PID are the same code.
- `--planning_type=waypoint`: `PlanningOperator.on_watermark` -> `World.update` -> `World.stop_for_agents` (person / vehicle / traffic-light / uncontrolled-junction speed factors) -> `World.follow_waypoints(speed_factor * target_speed)`. The FOT planner object is constructed anyway (used only by the OVERTAKE branch, which is commented out at base).
- Behaviour planner: FSM FOLLOW_WAYPOINTS <-> OVERTAKE driven by `cost_overtake` (stuck > 50 s at base); prunes one 1 m route point per tick when route[0] < 10 m, goal = route[0] (>= 5 m) -> `HDMap.compute_waypoints` (1 m GlobalRoutePlanner) -> planner waypoint list is ~10 m long.
- Control: `PIDControlOperator` uses `Waypoints.get_angle/get_target_speed` with `min_pid_*_waypoint_distance=5`; `ValueError` from `_get_index` is caught in BOTH the planner (speed 0) and the PID (brake 0.5).
- Flags relevant here (conf / defaults): `stop_for_people/vehicles/traffic_lights=True`, `stop_at_uncontrolled_junctions=True`, `target_speed=6`, `vehicle_max_distance=18`, `vehicle_max_angle=0.4`, `coast_factor=1.75`, `traffic_light_max_distance=20`, `dynamic_obstacle_distance_threshold=30`, `max_road_width_l=5.0`.
- Suite assumptions used below: Town01, lights FROZEN GREEN, 400 m mostly-straight lane, templates LeadDecel / LeadStopped / CutIn / Oncoming / Crossing (ProxCrossingTraffic).

## Summary table

| vid | fix commit | files (+/-) | mechanism (short) | default path | GT path | covering templates | negative controls | predicted metric | status |
|---|---|---|---|---|---|---|---|---|---|
| `v_wp_index` | 4891c00 (2020-11-12) | `pylot/planning/waypoints.py` (+3/-4) | _get_index max-clamp: always LAST waypoint (793b0c2 bug) | yes | yes | LeadDecel, LeadStopped, CutIn, Oncoming, Crossing | - | off-lane / lateral deviation (weak); no collision predicted | **ready** (weak) |
| `v_wp_index_pre` | 4891c00 (2020-11-12) | `pylot/planning/waypoints.py` (+3/-4) | _get_index pre-793b0c2 min-clamp: raises when no wp >= 5 m | yes | yes | - | LeadDecel, LeadStopped, CutIn, Oncoming, Crossing | stuck in last 5 m (route completion), otherwise none | **likely_inert** (none except route end) |
| `v_same_lane` | 760f137 (2020-07-18) | `pylot/planning/world.py` (+2/-2) | are_on_same_lane(pred, ego) arg order in predicted-path fallback | yes | yes | Crossing | LeadDecel, LeadStopped, Oncoming, CutIn | collision with crossing vehicle (approach phase); unnecessary braking inside junction | **ready** (moderate if Crossing is at a junction, else inert) |
| `v_tl_perfect` | 02c8034 (2020-07-30) | `pylot/planning/world.py` (+4/-5) | TL bbox-None hard stop removed (American-style branch) | no | no | - | LeadDecel, LeadStopped, CutIn, Oncoming, Crossing | none in suite (crash/no-control on perfect-TL path with red light elsewhere) | **likely_inert** (none) |
| `v_junction_stop` | afbf196 (2020-07-31) | `pylot/planning/world.py` (+2/-5) | full stop counted after 1 tick instead of >10 ticks | yes | yes | Crossing | LeadDecel, LeadStopped, Oncoming, CutIn | collision with crossing traffic at junction (less stopping); otherwise none | **likely_inert** (small (0.5 s shorter stop) and conditional) |
| `v_overtake` | 7be3b0e (2020-07-30) | `pylot/planning/cost_functions.py`, `pylot/planning/planning_operator.py` (+18/-18) | OVERTAKE branch re-enabled (FOT, no stop_for_agents), 35 s | yes | yes | LeadStopped, LeadDecel | CutIn, Oncoming, Crossing | collision (lead or oncoming) / off-lane; base outcome = stuck | **ready** (strong when it fires; direction is stuck->moving-with-risk, so define the regression metric as collision/off-lane, not stuck) |
| `v_speed7` | 47ff456 (2020-11-15) | `pylot/simulation/challenge/challenge.conf` (+1/-0) | challenge.conf --target_speed 7 (conf variant) | yes | yes | LeadDecel, LeadStopped, CutIn, Oncoming, Crossing | - | collision (rear-end / crossing), min-TTC | **ready** (moderate) |
| `v_goal_route0` | 793b0c2 (2020-11-06) | `pylot/planning/behavior_planning_operator.py` (+1/-6) | behaviour-planner goal = route[1] always (pre-793b0c2) | yes | yes | - | LeadDecel, LeadStopped, CutIn, Oncoming, Crossing | none in suite | **likely_inert** (none) |

## Recommended run order

A-grade first (mechanism on the default path AND exercisable by at least one template), suite-inert last:

1. `v_overtake` - ready: Needs ego stopped (speed<0.7) for >35 s of GAME time: LeadStopped (ego halts behind the lead) and LeadDecel only if the lead ends fully stopped for that long. Scenario must run long enough (>~45 s after the halt). CutIn/Oncoming/Crossing: ego never stuck -> negative controls.
2. `v_speed7` - ready: Template-independent (every tick). Strongest expected in LeadDecel/LeadStopped/CutIn/Crossing; Oncoming weakest (opposite-lane vehicle is ignored by the same-lane filter). Deploy by pointing TEAM_CONFIG at <vid>/pylot/simulation/challenge/challenge.conf (the file in the image is otherwise identical).
3. `v_same_lane` - ready: Fires ONLY if road_id differs AND exactly one of (ego, predicted point) is in a junction: i.e. the Crossing vehicle must cross at a junction. Mid-block crossing (same road_id, or off-road -> no DRIVING waypoint) is symmetric -> inert. LeadDecel/LeadStopped: same lane -> fallback never evaluated. Oncoming: same road, different lane_id -> symmetric. CutIn: adjacent lane, same road -> symmetric.
4. `v_wp_index` - ready: Mechanism is template-independent (fires every control tick); expected effect WEAK on a mostly-straight lane - look for lateral deviation on the curved segment, not collisions. No clean negative control; use the difftrace (idx differs every tick) as deployment proof.
5. `v_junction_stop` - likely_inert: Requires a junction within 13 m on the ego route AND no detected/obeyed TL (all Town01 junctions are signalised; frozen-GREEN lights that the camera TL detector sees count as semaphorized -> rule skipped). Fires only on TL-detection misses near a junction. Likely inert; Crossing is the only template whose geometry could matter.
6. `v_goal_route0` - likely_inert: With a 1 m-spaced route the goal moves by one metre; on a straight lane this is inert. Kept as requested; expect identical outcomes with a trivially different difftrace (goal x,y shifted ~1 m).
7. `v_wp_index_pre` - likely_inert: Needs all remaining waypoints within 5 m: only the last 5 m of the route (if the scenario is not terminated earlier by the leaderboard completion radius). Likely inert in our suite.
8. `v_tl_perfect` - likely_inert: Unreachable in our suite: lights frozen GREEN -> stop_traffic_light returns (True, 1) before this code; the hunk is inside the American-style branch (height_delta>4) which Town01 pole lights do not satisfy; and bbox is None only with --simulator_traffic_light_detection, which neither conf sets.

## Per-version detail

### `v_wp_index`

- **Fix commit:** 4891c00 (2020-11-12); introduced by 793b0c2
- **Direction:** revert fix (re-introduce 793b0c2 max-clamp bug)
- **Mechanism:** Waypoints._get_index clamps with max(len-1, min_index) -> ALWAYS returns the LAST waypoint of the list instead of the first waypoint >= min_distance (5 m). Used by PID steering (get_angle), PID target speed (get_target_speed) and World.stop_for_agents (get_vector/get_angle -> obstacle angle frame).
- **Expected pre-fix behaviour:** Steering look-ahead = last planner waypoint (~10 m ahead at steady state, because the behaviour planner's goal sits ~10 m ahead with the dense 1 m route) instead of ~5 m; obstacle-angle reference vector points to the same far waypoint. On a straight lane: slower lateral convergence; on curves: corner cutting. Target speed unaffected (uniform per message).
- **On default conf path:** True; **on GT-perception conf path:** True
- **Templates:** covering = LeadDecel, LeadStopped, CutIn, Oncoming, Crossing; negative controls = none. Mechanism is template-independent (fires every control tick); expected effect WEAK on a mostly-straight lane - look for lateral deviation on the curved segment, not collisions. No clean negative control; use the difftrace (idx differs every tick) as deployment proof.
- **Predicted failure metric:** off-lane / lateral deviation (weak); no collision predicted
- **Status:** ready (expected effect: weak)
- **Difftrace variable:** index returned by Waypoints._get_index inside get_vector (fix: first idx with dist>=5 m; version: len-1) - patch `v_wp_index.difftrace.patch` (git context -U3) in `pylot/planning/waypoints.py`
- **md5 of changed files:**
  - `pylot/planning/waypoints.py`: base `037a3f66b7054dcf7abd5452b56d507c` -> version `d15050bd0b3bb90cd7d93fd73e8262c9`
- **`diff -r base v_wp_index`:**
```diff
diff -r /home/users/bhamadou/satrp_real/pylot/versions/base/pylot/planning/waypoints.py /home/users/bhamadou/satrp_real/pylot/versions/v_wp_index/pylot/planning/waypoints.py
119,121c119,120
<         if min_index == -1:
<             min_index = len(self.waypoints) - 1
<         if min_index < 0:
---
>         wp_index = max(len(self.waypoints) - 1, min_index)
>         if wp_index < 0:
123c122
<         return min_index
---
>         return wp_index
```
- **`v_wp_index.patch` (base -> version):**
```diff
diff --git a/pylot/planning/waypoints.py b/pylot/planning/waypoints.py
index 726a950..64623b7 100644
--- a/pylot/planning/waypoints.py
+++ b/pylot/planning/waypoints.py
@@ -116,11 +116,10 @@ class Waypoints(object):
             if distance >= min_distance:
                 min_index = index
                 break
-        if min_index == -1:
-            min_index = len(self.waypoints) - 1
-        if min_index < 0:
+        wp_index = max(len(self.waypoints) - 1, min_index)
+        if wp_index < 0:
             raise ValueError('No more waypoints')
-        return min_index
+        return wp_index
 
     def get_angle(self, transform, min_distance):
         """Returns the angle between the transform and the first waypoint that
```
- **`v_wp_index.difftrace.patch`:**
```diff
diff --git a/pylot/planning/waypoints.py b/pylot/planning/waypoints.py
index 726a950..028ace8 100644
--- a/pylot/planning/waypoints.py
+++ b/pylot/planning/waypoints.py
@@ -133,6 +133,12 @@ class Waypoints(object):
     def get_vector(self, transform, min_distance):
         """Returns the vector between the transform and the first waypoint that
         is at least min_distance away."""
+        if __import__('os').environ.get('PYLOT_DIFFTRACE') == '1':
+            try:
+                _dt_idx = self._get_index(transform, min_distance)
+            except ValueError:
+                _dt_idx = 'ValueError'
+            __import__('sys').stderr.write('[difftrace v_wp_index] get_vector n=%d idx=%s\n' % (len(self.waypoints), _dt_idx))
         wp_index = self._get_index(transform, min_distance)
         return self.waypoints[wp_index].location.as_vector_2D() - \
             transform.location.as_vector_2D()
```

### `v_wp_index_pre`

- **Fix commit:** 4891c00 (2020-11-12)
- **Direction:** forward chronology: _get_index as it was BEFORE 793b0c2 (min-clamp; raises ValueError when no waypoint is >= min_distance)
- **Mechanism:** Pre-793b0c2 code: wp_index = min(len-1, min_index); when no waypoint is >= 5 m away min_index=-1 -> ValueError('No more waypoints'). 4891c00's fix instead returns the last waypoint. (793b0c2 bug state is v_wp_index; the pre-state DIFFERS from the fix, so this is a distinct version.)
- **Expected pre-fix behaviour:** Identical to base except when ALL waypoints in the planner list are < 5 m from the ego: then World.stop_for_agents returns speed 0 and the PID brakes (both catch ValueError). Happens for ~4 ticks at route start (ego is stationary anyway) and in the final ~5 m before the route goal.
- **On default conf path:** True; **on GT-perception conf path:** True
- **Templates:** covering = none; negative controls = LeadDecel, LeadStopped, CutIn, Oncoming, Crossing. Needs all remaining waypoints within 5 m: only the last 5 m of the route (if the scenario is not terminated earlier by the leaderboard completion radius). Likely inert in our suite.
- **Predicted failure metric:** stuck in last 5 m (route completion), otherwise none
- **Status:** likely_inert (expected effect: none except route end)
- **Difftrace variable:** index returned by _get_index inside get_vector ('ValueError' string in version when it raises) - patch `v_wp_index_pre.difftrace.patch` (git context -U3) in `pylot/planning/waypoints.py`
- **md5 of changed files:**
  - `pylot/planning/waypoints.py`: base `037a3f66b7054dcf7abd5452b56d507c` -> version `3f6505cac3e2dead6f3359f40972bad7`
- **`diff -r base v_wp_index_pre`:**
```diff
diff -r /home/users/bhamadou/satrp_real/pylot/versions/base/pylot/planning/waypoints.py /home/users/bhamadou/satrp_real/pylot/versions/v_wp_index_pre/pylot/planning/waypoints.py
119,121c119,120
<         if min_index == -1:
<             min_index = len(self.waypoints) - 1
<         if min_index < 0:
---
>         wp_index = min(len(self.waypoints) - 1, min_index)
>         if wp_index < 0:
123c122
<         return min_index
---
>         return wp_index
```
- **`v_wp_index_pre.patch` (base -> version):**
```diff
diff --git a/pylot/planning/waypoints.py b/pylot/planning/waypoints.py
index 726a950..fed2ba3 100644
--- a/pylot/planning/waypoints.py
+++ b/pylot/planning/waypoints.py
@@ -116,11 +116,10 @@ class Waypoints(object):
             if distance >= min_distance:
                 min_index = index
                 break
-        if min_index == -1:
-            min_index = len(self.waypoints) - 1
-        if min_index < 0:
+        wp_index = min(len(self.waypoints) - 1, min_index)
+        if wp_index < 0:
             raise ValueError('No more waypoints')
-        return min_index
+        return wp_index
 
     def get_angle(self, transform, min_distance):
         """Returns the angle between the transform and the first waypoint that
```
- **`v_wp_index_pre.difftrace.patch`:**
```diff
diff --git a/pylot/planning/waypoints.py b/pylot/planning/waypoints.py
index 726a950..03498d0 100644
--- a/pylot/planning/waypoints.py
+++ b/pylot/planning/waypoints.py
@@ -133,6 +133,12 @@ class Waypoints(object):
     def get_vector(self, transform, min_distance):
         """Returns the vector between the transform and the first waypoint that
         is at least min_distance away."""
+        if __import__('os').environ.get('PYLOT_DIFFTRACE') == '1':
+            try:
+                _dt_idx = self._get_index(transform, min_distance)
+            except ValueError:
+                _dt_idx = 'ValueError'
+            __import__('sys').stderr.write('[difftrace v_wp_index_pre] get_vector n=%d idx=%s\n' % (len(self.waypoints), _dt_idx))
         wp_index = self._get_index(transform, min_distance)
         return self.waypoints[wp_index].location.as_vector_2D() - \
             transform.location.as_vector_2D()
```

### `v_same_lane`

- **Fix commit:** 760f137 (2020-07-18)
- **Direction:** revert fix (swap are_on_same_lane argument order in the predicted-trajectory check, stop_person + stop_vehicle)
- **Mechanism:** World.stop_person/stop_vehicle: when the obstacle's CURRENT location is not on the ego lane, the fallback checks whether ANY predicted location is on the ego lane via HDMap.are_on_same_lane(a, b). The function is asymmetric only in the junction rule: 'if waypoint_a.is_junction and not waypoint_b.is_junction: return False' (different road_id case). Fixed order (ego, pred): ignore obstacle when EGO is in the junction and the predicted point is outside. Bug order (pred, ego): ignore obstacle when the PREDICTED point is in the junction and the ego is outside -> an approaching ego ignores traffic crossing inside the junction.
- **Expected pre-fix behaviour:** Ego approaching a junction ignores a vehicle/person whose predicted path lies inside the junction (no braking) -> collision risk; conversely, while inside a junction it brakes for off-junction obstacles on other roads it should ignore.
- **On default conf path:** True; **on GT-perception conf path:** True
- **Templates:** covering = Crossing; negative controls = LeadDecel, LeadStopped, Oncoming, CutIn. Fires ONLY if road_id differs AND exactly one of (ego, predicted point) is in a junction: i.e. the Crossing vehicle must cross at a junction. Mid-block crossing (same road_id, or off-road -> no DRIVING waypoint) is symmetric -> inert. LeadDecel/LeadStopped: same lane -> fallback never evaluated. Oncoming: same road, different lane_id -> symmetric. CutIn: adjacent lane, same road -> symmetric.
- **Predicted failure metric:** collision with crossing vehicle (approach phase); unnecessary braking inside junction
- **Status:** ready (expected effect: moderate if Crossing is at a junction, else inert)
- **Difftrace variable:** 'ignore <label> <id>' event emitted when the fallback decides to ignore an obstacle (same statement at both call sites) - patch `v_same_lane.difftrace.patch` (git context -U1) in `pylot/planning/world.py`
- **md5 of changed files:**
  - `pylot/planning/world.py`: base `2bfab7f963a1fb9523029116f8e8163d` -> version `973f066dbcee82d231adfbd4898569e7`
- **`diff -r base v_same_lane`:**
```diff
diff -r /home/users/bhamadou/satrp_real/pylot/versions/base/pylot/planning/world.py /home/users/bhamadou/satrp_real/pylot/versions/v_same_lane/pylot/planning/world.py
170c170
<                                 self.ego_transform.location, transform.location
---
>                                 transform.location, self.ego_transform.location
219c219
<                                 self.ego_transform.location, transform.location
---
>                                 transform.location, self.ego_transform.location
```
- **`v_same_lane.patch` (base -> version):**
```diff
diff --git a/pylot/planning/world.py b/pylot/planning/world.py
index 7b1859e..d70b983 100644
--- a/pylot/planning/world.py
+++ b/pylot/planning/world.py
@@ -167,7 +167,7 @@ class World(object):
                 if not any(
                         map(
                             lambda transform: self._map.are_on_same_lane(
-                                self.ego_transform.location, transform.location
+                                transform.location, self.ego_transform.location
                             ), obstacle.predicted_trajectory)):
                     # The person is not going to be on the same lane.
                     self._logger.debug(
@@ -216,7 +216,7 @@ class World(object):
                 if not any(
                         map(
                             lambda transform: self._map.are_on_same_lane(
-                                self.ego_transform.location, transform.location
+                                transform.location, self.ego_transform.location
                             ), obstacle.predicted_trajectory)):
                     # The vehicle is not going to be on the same lane as ego.
                     self._logger.debug(
```
- **`v_same_lane.difftrace.patch`:**
```diff
diff --git a/pylot/planning/world.py b/pylot/planning/world.py
index 7b1859e..ef0990c 100644
--- a/pylot/planning/world.py
+++ b/pylot/planning/world.py
@@ -171,2 +171,3 @@ class World(object):
                             ), obstacle.predicted_trajectory)):
+                    if __import__('os').environ.get('PYLOT_DIFFTRACE') == '1': __import__('sys').stderr.write('[difftrace v_same_lane] ignore %s %d ego=(%.1f,%.1f) obs=(%.1f,%.1f)\n' % (obstacle.label, obstacle.id, self.ego_transform.location.x, self.ego_transform.location.y, obstacle.transform.location.x, obstacle.transform.location.y))
                     # The person is not going to be on the same lane.
@@ -220,2 +221,3 @@ class World(object):
                             ), obstacle.predicted_trajectory)):
+                    if __import__('os').environ.get('PYLOT_DIFFTRACE') == '1': __import__('sys').stderr.write('[difftrace v_same_lane] ignore %s %d ego=(%.1f,%.1f) obs=(%.1f,%.1f)\n' % (obstacle.label, obstacle.id, self.ego_transform.location.x, self.ego_transform.location.y, obstacle.transform.location.x, obstacle.transform.location.y))
                     # The vehicle is not going to be on the same lane as ego.
```

### `v_tl_perfect`

- **Fix commit:** 02c8034 (2020-07-30)
- **Direction:** revert behavioural hunk (drop the bounding_box-is-None hard stop); 09901a8 crash-fix hunk KEPT
- **Mechanism:** World.stop_traffic_light, American-style branch (height_delta > 4): fixed code forces speed_factor_tl=0 when dist_to_intersection<12 and (bbox is None OR bbox area>400). Version: requires bbox area > 400 (would raise AttributeError when bbox is None, i.e. on the --simulator_traffic_light_detection path). Only the world.py hunk is re-expressed; 02c8034's ERDOSAgent visible-TL filter now lives in ERDOSBaseAgent.send_perfect_detections (moved by 52b8570) and its max_angle /4->/3 tweak is not re-expressed.
- **Expected pre-fix behaviour:** On the perfect-TL path with a RED/YELLOW American-style light within 12 m of the junction: AttributeError in the planner (crash / no control) instead of a hard stop. On the camera path (default conf) bbox is never None -> no behavioural difference at all.
- **On default conf path:** False; **on GT-perception conf path:** False
- **Templates:** covering = none; negative controls = LeadDecel, LeadStopped, CutIn, Oncoming, Crossing. Unreachable in our suite: lights frozen GREEN -> stop_traffic_light returns (True, 1) before this code; the hunk is inside the American-style branch (height_delta>4) which Town01 pole lights do not satisfy; and bbox is None only with --simulator_traffic_light_detection, which neither conf sets.
- **Predicted failure metric:** none in suite (crash/no-control on perfect-TL path with red light elsewhere)
- **Status:** likely_inert (expected effect: none)
- **Difftrace variable:** speed_factor_tl per traffic light after the style-specific logic (tl id, state, bbox_none, american, dist) - patch `v_tl_perfect.difftrace.patch` (git context -U3) in `pylot/planning/world.py`
- **md5 of changed files:**
  - `pylot/planning/world.py`: base `2bfab7f963a1fb9523029116f8e8163d` -> version `18fd68c87cf3e0c12c893f9760b62fb6`
- **`diff -r base v_tl_perfect`:**
```diff
diff -r /home/users/bhamadou/satrp_real/pylot/versions/base/pylot/planning/world.py /home/users/bhamadou/satrp_real/pylot/versions/v_tl_perfect/pylot/planning/world.py
406,410c406,409
<                             and dist_to_intersection < 12):
<                         if (tl.bounding_box is None
<                                 or tl.bounding_box.get_width() *
<                                 tl.bounding_box.get_height() > 400):
<                             speed_factor_tl = 0
---
>                             and dist_to_intersection < 12
>                             and tl.bounding_box.get_width() *
>                             tl.bounding_box.get_height() > 400):
>                         speed_factor_tl = 0
```
- **`v_tl_perfect.patch` (base -> version):**
```diff
diff --git a/pylot/planning/world.py b/pylot/planning/world.py
index 7b1859e..3db4d03 100644
--- a/pylot/planning/world.py
+++ b/pylot/planning/world.py
@@ -403,11 +403,10 @@ class World(object):
                     dist_to_intersection = self._map.distance_to_intersection(
                         self.ego_transform.location, max_distance_to_check=20)
                     if (dist_to_intersection is not None
-                            and dist_to_intersection < 12):
-                        if (tl.bounding_box is None
-                                or tl.bounding_box.get_width() *
-                                tl.bounding_box.get_height() > 400):
-                            speed_factor_tl = 0
+                            and dist_to_intersection < 12
+                            and tl.bounding_box.get_width() *
+                            tl.bounding_box.get_height() > 400):
+                        speed_factor_tl = 0
                     if (dist_to_intersection is not None and tl_dist < 27
                             and 12 <= dist_to_intersection <= 20):
                         speed_factor_tl = 0
```
- **`v_tl_perfect.difftrace.patch`:**
```diff
diff --git a/pylot/planning/world.py b/pylot/planning/world.py
index 7b1859e..c7e1d0d 100644
--- a/pylot/planning/world.py
+++ b/pylot/planning/world.py
@@ -417,6 +417,7 @@ class World(object):
                     # The traffic light is nearby and the vehicle is driving
                     # straight; the angle to the traffic light can be higher.
                     speed_factor_tl = 0
+        if __import__('os').environ.get('PYLOT_DIFFTRACE') == '1': __import__('sys').stderr.write('[difftrace v_tl_perfect] tl=%s state=%s bbox_none=%s american=%s dist=%.1f sf_tl=%.3f\n' % (tl.id, tl.state, tl.bounding_box is None, american_tl, tl_dist, speed_factor_tl))
         if speed_factor_tl < 1:
             dist_to_intersection = self._map.distance_to_intersection(
                 self.ego_transform.location, max_distance_to_check=20)
```

### `v_junction_stop`

- **Fix commit:** afbf196 (2020-07-31)
- **Direction:** revert the _num_ticks_stopped (>10 ticks) hunk in World.update; ERDOSAgent TL delta_y hunk untouched (now in ERDOSBaseAgent)
- **Mechanism:** World.update: fixed code resets _distance_since_last_full_stop / _last_stop_ego_location only after >10 consecutive ticks with forward_speed<0.7 (a genuine full stop). Version resets on the FIRST slow tick. Consumer: stop_for_agents uncontrolled-junction rule (--stop_at_uncontrolled_junctions=True in challenge.conf): speed_factor_stop=0 when a junction is <=13 m ahead, no semaphorized (detected+obeyed) TL, and >13 m driven since last full stop. The unused __init__ line 'self._num_ticks_stopped = 0' is kept so the difftrace is valid in both trees.
- **Expected pre-fix behaviour:** At a junction that the planner treats as uncontrolled (no TL detected within range), the version 'stops' for a single tick and rolls through; base holds a >10-tick (~0.5 s game time) full stop.
- **On default conf path:** True; **on GT-perception conf path:** True
- **Templates:** covering = Crossing; negative controls = LeadDecel, LeadStopped, Oncoming, CutIn. Requires a junction within 13 m on the ego route AND no detected/obeyed TL (all Town01 junctions are signalised; frozen-GREEN lights that the camera TL detector sees count as semaphorized -> rule skipped). Fires only on TL-detection misses near a junction. Likely inert; Crossing is the only template whose geometry could matter.
- **Predicted failure metric:** collision with crossing traffic at junction (less stopping); otherwise none
- **Status:** likely_inert (expected effect: small (0.5 s shorter stop) and conditional)
- **Difftrace variable:** World._num_ticks_stopped and _distance_since_last_full_stop at the end of World.update (version: ticks stays 0; dist resets one tick earlier) - patch `v_junction_stop.difftrace.patch` (git context -U3) in `pylot/planning/world.py`
- **md5 of changed files:**
  - `pylot/planning/world.py`: base `2bfab7f963a1fb9523029116f8e8163d` -> version `789f9a6fa1bb90c629402926520ed2db`
- **`diff -r base v_junction_stop`:**
```diff
diff -r /home/users/bhamadou/satrp_real/pylot/versions/base/pylot/planning/world.py /home/users/bhamadou/satrp_real/pylot/versions/v_junction_stop/pylot/planning/world.py
78,81c78,79
<             self._num_ticks_stopped += 1
<             if self._num_ticks_stopped > 10:
<                 self._distance_since_last_full_stop = 0
<                 self._last_stop_ego_location = self.ego_transform.location
---
>             self._distance_since_last_full_stop = 0
>             self._last_stop_ego_location = self.ego_transform.location
83d80
<             self._num_ticks_stopped = 0
```
- **`v_junction_stop.patch` (base -> version):**
```diff
diff --git a/pylot/planning/world.py b/pylot/planning/world.py
index 7b1859e..a009daf 100644
--- a/pylot/planning/world.py
+++ b/pylot/planning/world.py
@@ -75,12 +75,9 @@ class World(object):
             # We can't just check if forward_speed is zero because localization
             # noise can cause the forward_speed to be non zero even when the
             # ego is stopped.
-            self._num_ticks_stopped += 1
-            if self._num_ticks_stopped > 10:
-                self._distance_since_last_full_stop = 0
-                self._last_stop_ego_location = self.ego_transform.location
+            self._distance_since_last_full_stop = 0
+            self._last_stop_ego_location = self.ego_transform.location
         else:
-            self._num_ticks_stopped = 0
             if self._last_stop_ego_location is not None:
                 self._distance_since_last_full_stop = \
                     self.ego_transform.location.distance(
```
- **`v_junction_stop.difftrace.patch`:**
```diff
diff --git a/pylot/planning/world.py b/pylot/planning/world.py
index 7b1859e..39de2c7 100644
--- a/pylot/planning/world.py
+++ b/pylot/planning/world.py
@@ -87,6 +87,7 @@ class World(object):
                         self._last_stop_ego_location)
             else:
                 self._distance_since_last_full_stop = 0
+        if __import__('os').environ.get('PYLOT_DIFFTRACE') == '1': __import__('sys').stderr.write('[difftrace v_junction_stop] ts=%d speed=%.2f ticks_stopped=%d dist_since_stop=%.2f\n' % (timestamp.coordinates[0], pose.forward_speed, self._num_ticks_stopped, self._distance_since_last_full_stop))
 
     def update_waypoints(self, goal_location, waypoints):
         self._goal_location = goal_location
```

### `v_overtake`

- **Fix commit:** 7be3b0e (2020-07-30)
- **Direction:** re-enable OVERTAKE special case in PlanningOperator with pre-commit threshold 35 s (cost_functions 50000->35000 ms)
- **Mechanism:** Behaviour planner FSM (live at base) switches FOLLOW_WAYPOINTS->OVERTAKE after the ego has not moved (speed<0.7) for >threshold ms game time, and back after 3 s of motion. Base: PlanningOperator ignores the state (branch commented out) -> stop_for_agents always applied, ego stays stopped. Version: in OVERTAKE the planner runs FOTPlanner.run (Frenet planner over world.waypoints with predicted obstacle corners, max_road_width_l=5 m) and SKIPS stop_for_agents (ignores obstacles/TL speed factors); threshold 35 s instead of 50 s. Two hunks, one mechanism (branch + its threshold). 7be3b0e's behaviour-planner prune hunk is NOT revertable (lines rewritten by ab5384a/793b0c2/47ff456) and is a no-op at base (10 m in both branches).
- **Expected pre-fix behaviour:** After ~35 s stuck behind a stopped lead, the ego pulls out around it on an FOT path (up to 5 m left = fully into the oncoming lane in Town01), ignoring stop logic for ~3 s of motion, then snaps back to lane following with stop_for_agents -> side-swipe / collision with lead or oncoming, or off-lane excursion; if FOT fails it sends an emergency stop (same as base). Base: stuck behind the lead until timeout.
- **On default conf path:** True; **on GT-perception conf path:** True
- **Templates:** covering = LeadStopped, LeadDecel; negative controls = CutIn, Oncoming, Crossing. Needs ego stopped (speed<0.7) for >35 s of GAME time: LeadStopped (ego halts behind the lead) and LeadDecel only if the lead ends fully stopped for that long. Scenario must run long enough (>~45 s after the halt). CutIn/Oncoming/Crossing: ego never stuck -> negative controls.
- **Predicted failure metric:** collision (lead or oncoming) / off-lane; base outcome = stuck
- **Status:** ready (expected effect: strong when it fires; direction is stuck->moving-with-risk, so define the regression metric as collision/off-lane, not stuck)
- **Difftrace variable:** PlanningOperator state + output waypoint count + first target speed per tick (state OVERTAKE appears 15 s earlier; FOT output replaces follow_waypoints output) - patch `v_overtake.difftrace.patch` (git context -U1) in `pylot/planning/planning_operator.py`
- **md5 of changed files:**
  - `pylot/planning/cost_functions.py`: base `a7c305d14b4613bf231658598e216211` -> version `f8e2395a8247b4b3fd9c62659b5e495a`
  - `pylot/planning/planning_operator.py`: base `953fac453446258e752a5589a1ed359b` -> version `6eadf02c485d700b282ff497fd06b421`
- **`diff -r base v_overtake`:**
```diff
diff -r /home/users/bhamadou/satrp_real/pylot/versions/base/pylot/planning/cost_functions.py /home/users/bhamadou/satrp_real/pylot/versions/v_overtake/pylot/planning/cost_functions.py
111c111
<     if ego_info.current_time - ego_info.last_time_moving > 50000:
---
>     if ego_info.current_time - ego_info.last_time_moving > 35000:
diff -r /home/users/bhamadou/satrp_real/pylot/versions/base/pylot/planning/planning_operator.py /home/users/bhamadou/satrp_real/pylot/versions/v_overtake/pylot/planning/planning_operator.py
181,193c181,182
<         # if self._state == BehaviorPlannerState.OVERTAKE:
<         #     # Ignore traffic lights and obstacle.
<         #     output_wps = self._planner.run(timestamp, ttd)
<         # else:
<         (speed_factor, _, _, speed_factor_tl,
<          speed_factor_stop) = self._world.stop_for_agents(timestamp)
<         if self._flags.planning_type == 'waypoint':
<             target_speed = speed_factor * self._flags.target_speed
<             self._logger.debug(
<                 '@{}: speed factor: {}, target speed: {}'.format(
<                     timestamp, speed_factor, target_speed))
<             output_wps = self._world.follow_waypoints(target_speed)
<         else:
---
>         if self._state == BehaviorPlannerState.OVERTAKE:
>             # Ignore traffic lights and obstacle.
195,198c184,198
<             speed_factor = min(speed_factor_stop, speed_factor_tl)
<             self._logger.debug('@{}: speed factor: {}'.format(
<                 timestamp, speed_factor))
<             output_wps.apply_speed_factor(speed_factor)
---
>         else:
>             (speed_factor, _, _, speed_factor_tl,
>              speed_factor_stop) = self._world.stop_for_agents(timestamp)
>             if self._flags.planning_type == 'waypoint':
>                 target_speed = speed_factor * self._flags.target_speed
>                 self._logger.debug(
>                     '@{}: speed factor: {}, target speed: {}'.format(
>                         timestamp, speed_factor, target_speed))
>                 output_wps = self._world.follow_waypoints(target_speed)
>             else:
>                 output_wps = self._planner.run(timestamp, ttd)
>                 speed_factor = min(speed_factor_stop, speed_factor_tl)
>                 self._logger.debug('@{}: speed factor: {}'.format(
>                     timestamp, speed_factor))
>                 output_wps.apply_speed_factor(speed_factor)
```
- **`v_overtake.patch` (base -> version):**
```diff
diff --git a/pylot/planning/cost_functions.py b/pylot/planning/cost_functions.py
index aad8abd..b6129b7 100644
--- a/pylot/planning/cost_functions.py
+++ b/pylot/planning/cost_functions.py
@@ -108,7 +108,7 @@ def cost_inefficiency(vehicle_info, predictions, trajectory):
 
 
 def cost_overtake(current_state, future_state, ego_info):
-    if ego_info.current_time - ego_info.last_time_moving > 50000:
+    if ego_info.current_time - ego_info.last_time_moving > 35000:
         # Switch to OVERTAKE if ego hasn't moved for a while.
         if future_state == BehaviorPlannerState.OVERTAKE:
             return 0
diff --git a/pylot/planning/planning_operator.py b/pylot/planning/planning_operator.py
index 8593335..5992dcc 100644
--- a/pylot/planning/planning_operator.py
+++ b/pylot/planning/planning_operator.py
@@ -178,24 +178,24 @@ class PlanningOperator(erdos.Operator):
         ttd = ttd_msg.data - (time.time() - self._world.pose.localization_time)
         self._logger.debug('@{}: adjusting ttd from {} to {}'.format(
             timestamp, ttd_msg.data, ttd))
-        # if self._state == BehaviorPlannerState.OVERTAKE:
-        #     # Ignore traffic lights and obstacle.
-        #     output_wps = self._planner.run(timestamp, ttd)
-        # else:
-        (speed_factor, _, _, speed_factor_tl,
-         speed_factor_stop) = self._world.stop_for_agents(timestamp)
-        if self._flags.planning_type == 'waypoint':
-            target_speed = speed_factor * self._flags.target_speed
-            self._logger.debug(
-                '@{}: speed factor: {}, target speed: {}'.format(
-                    timestamp, speed_factor, target_speed))
-            output_wps = self._world.follow_waypoints(target_speed)
-        else:
+        if self._state == BehaviorPlannerState.OVERTAKE:
+            # Ignore traffic lights and obstacle.
             output_wps = self._planner.run(timestamp, ttd)
-            speed_factor = min(speed_factor_stop, speed_factor_tl)
-            self._logger.debug('@{}: speed factor: {}'.format(
-                timestamp, speed_factor))
-            output_wps.apply_speed_factor(speed_factor)
+        else:
+            (speed_factor, _, _, speed_factor_tl,
+             speed_factor_stop) = self._world.stop_for_agents(timestamp)
+            if self._flags.planning_type == 'waypoint':
+                target_speed = speed_factor * self._flags.target_speed
+                self._logger.debug(
+                    '@{}: speed factor: {}, target speed: {}'.format(
+                        timestamp, speed_factor, target_speed))
+                output_wps = self._world.follow_waypoints(target_speed)
+            else:
+                output_wps = self._planner.run(timestamp, ttd)
+                speed_factor = min(speed_factor_stop, speed_factor_tl)
+                self._logger.debug('@{}: speed factor: {}'.format(
+                    timestamp, speed_factor))
+                output_wps.apply_speed_factor(speed_factor)
         waypoints_stream.send(WaypointsMessage(timestamp, output_wps))
         waypoints_stream.send(erdos.WatermarkMessage(timestamp))
```
- **`v_overtake.difftrace.patch`:**
```diff
diff --git a/pylot/planning/planning_operator.py b/pylot/planning/planning_operator.py
index 8593335..e9ebbf5 100644
--- a/pylot/planning/planning_operator.py
+++ b/pylot/planning/planning_operator.py
@@ -199,2 +199,3 @@ class PlanningOperator(erdos.Operator):
         waypoints_stream.send(WaypointsMessage(timestamp, output_wps))
+        if __import__('os').environ.get('PYLOT_DIFFTRACE') == '1': __import__('sys').stderr.write('[difftrace v_overtake] ts=%d state=%s n_wps=%d ts0=%s\n' % (timestamp.coordinates[0], self._state, len(output_wps.waypoints), (list(output_wps.target_speeds)[:1] or [None])[0]))
         waypoints_stream.send(erdos.WatermarkMessage(timestamp))
```

### `v_speed7`

- **Fix commit:** 47ff456 (2020-11-15)
- **Direction:** revert ONLY --target_speed 6->7 in challenge.conf (conf-file variant, not source); behaviour-planner prune 2->3 and Dockerfile hunks dropped
- **Mechanism:** PlanningOperator (waypoint mode): target_speed = speed_factor * FLAGS.target_speed every tick; PID tracks it. Higher cruise speed with unchanged distance-based stop thresholds (vehicle_max_distance 18 m, coast_factor 1.75, person zones).
- **Expected pre-fix behaviour:** Cruise at 7 m/s instead of 6: longer stopping distance, later effective braking relative to the fixed distance thresholds -> more/closer rear-end and crossing conflicts.
- **On default conf path:** True; **on GT-perception conf path:** True
- **Templates:** covering = LeadDecel, LeadStopped, CutIn, Oncoming, Crossing; negative controls = none. Template-independent (every tick). Strongest expected in LeadDecel/LeadStopped/CutIn/Crossing; Oncoming weakest (opposite-lane vehicle is ignored by the same-lane filter). Deploy by pointing TEAM_CONFIG at <vid>/pylot/simulation/challenge/challenge.conf (the file in the image is otherwise identical).
- **Predicted failure metric:** collision (rear-end / crossing), min-TTC
- **Status:** ready (expected effect: moderate)
- **Difftrace variable:** FLAGS.target_speed, speed_factor and target_speed per planner tick - patch `v_speed7.difftrace.patch` (git context -U3) in `pylot/planning/planning_operator.py`
- **md5 of changed files:**
  - `pylot/simulation/challenge/challenge.conf`: base `665b35611c98ffd64bf25246eab6e6e2` -> version `67f95a3243ac49663900cd3be5338734`
- **`diff -r base v_speed7`:**
```diff
diff -r /home/users/bhamadou/satrp_real/pylot/versions/base/pylot/simulation/challenge/challenge.conf /home/users/bhamadou/satrp_real/pylot/versions/v_speed7/pylot/simulation/challenge/challenge.conf
39c39
< --target_speed=6
---
> --target_speed=7
```
- **`v_speed7.patch` (base -> version):**
```diff
diff --git a/pylot/simulation/challenge/challenge.conf b/pylot/simulation/challenge/challenge.conf
index 3f9c497..fe54293 100644
--- a/pylot/simulation/challenge/challenge.conf
+++ b/pylot/simulation/challenge/challenge.conf
@@ -36,7 +36,7 @@
 ########## Planning flags ##########
 --planning_type=waypoint
 #--planning_type=frenet_optimal_trajectory
---target_speed=6
+--target_speed=7
 --max_speed=16
 --d_road_w=0.2
 --d_t_s=0.25
```
- **`v_speed7.difftrace.patch`:**
```diff
diff --git a/pylot/planning/planning_operator.py b/pylot/planning/planning_operator.py
index 8593335..34b59de 100644
--- a/pylot/planning/planning_operator.py
+++ b/pylot/planning/planning_operator.py
@@ -189,6 +189,7 @@ class PlanningOperator(erdos.Operator):
             self._logger.debug(
                 '@{}: speed factor: {}, target speed: {}'.format(
                     timestamp, speed_factor, target_speed))
+            if __import__('os').environ.get('PYLOT_DIFFTRACE') == '1': __import__('sys').stderr.write('[difftrace v_speed7] ts=%d flag_target_speed=%s speed_factor=%.3f target_speed=%.3f\n' % (timestamp.coordinates[0], self._flags.target_speed, speed_factor, target_speed))
             output_wps = self._world.follow_waypoints(target_speed)
         else:
             output_wps = self._planner.run(timestamp, ttd)
```

### `v_goal_route0`

- **Fix commit:** 793b0c2 (2020-11-06)
- **Direction:** revert the __get_goal_location hunk (goal = route[1] always, instead of route[0] when ego is >=5 m from route[0]). NOTE: this hunk is in 793b0c2, NOT in ab5384a as listed in the brief (ab5384a only refactored the goal code into __get_goal_location without changing route[1])
- **Mechanism:** BehaviourPlanningOperator.__get_goal_location: the goal (end of the map-computed waypoint list handed to the planner) is route[0] when the ego is >=5 m from it, else route[1]. Route = dense 1 m leaderboard world-coord plan (used since 2019); remove_waypoint_if_close(10) pops one route point per tick, so route[0] settles ~10 m ahead and the goal is ~10 m ahead (base) vs ~11 m ahead (version).
- **Expected pre-fix behaviour:** Planner waypoint list extends 1 m further; identical lane geometry on a straight road. Differences only where route[0] and route[1] lie on different roads/lanes (junction turns) or at the route end.
- **On default conf path:** True; **on GT-perception conf path:** True
- **Templates:** covering = none; negative controls = LeadDecel, LeadStopped, CutIn, Oncoming, Crossing. With a 1 m-spaced route the goal moves by one metre; on a straight lane this is inert. Kept as requested; expect identical outcomes with a trivially different difftrace (goal x,y shifted ~1 m).
- **Predicted failure metric:** none in suite
- **Status:** likely_inert (expected effect: none)
- **Difftrace variable:** route length, distance to route[0] and the selected goal location per behaviour-planner tick - patch `v_goal_route0.difftrace.patch` (git context -U3) in `pylot/planning/behavior_planning_operator.py`
- **md5 of changed files:**
  - `pylot/planning/behavior_planning_operator.py`: base `9cc1b381b9c9406921af573f3c95559e` -> version `837fc9d8c02674d854de43d3299b5a00`
- **`diff -r base v_goal_route0`:**
```diff
diff -r /home/users/bhamadou/satrp_real/pylot/versions/base/pylot/planning/behavior_planning_operator.py /home/users/bhamadou/satrp_real/pylot/versions/v_goal_route0/pylot/planning/behavior_planning_operator.py
235,240c235
<             dist = ego_transform.location.distance(
<                 self._route.waypoints[0].location)
<             if dist < 5:
<                 new_goal_location = self._route.waypoints[1].location
<             else:
<                 new_goal_location = self._route.waypoints[0].location
---
>             new_goal_location = self._route.waypoints[1].location
```
- **`v_goal_route0.patch` (base -> version):**
```diff
diff --git a/pylot/planning/behavior_planning_operator.py b/pylot/planning/behavior_planning_operator.py
index 4a364e2..928cbb5 100644
--- a/pylot/planning/behavior_planning_operator.py
+++ b/pylot/planning/behavior_planning_operator.py
@@ -232,12 +232,7 @@ class BehaviorPlanningOperator(erdos.Operator):
 
     def __get_goal_location(self, ego_transform):
         if len(self._route.waypoints) > 1:
-            dist = ego_transform.location.distance(
-                self._route.waypoints[0].location)
-            if dist < 5:
-                new_goal_location = self._route.waypoints[1].location
-            else:
-                new_goal_location = self._route.waypoints[0].location
+            new_goal_location = self._route.waypoints[1].location
         elif len(self._route.waypoints) == 1:
             new_goal_location = self._route.waypoints[0].location
         else:
```
- **`v_goal_route0.difftrace.patch`:**
```diff
diff --git a/pylot/planning/behavior_planning_operator.py b/pylot/planning/behavior_planning_operator.py
index 4a364e2..29f0540 100644
--- a/pylot/planning/behavior_planning_operator.py
+++ b/pylot/planning/behavior_planning_operator.py
@@ -120,6 +120,7 @@ class BehaviorPlanningOperator(erdos.Operator):
             else:
                 self._route.remove_waypoint_if_close(ego_transform.location, 3)
         new_goal_location = self.__get_goal_location(ego_transform)
+        if __import__('os').environ.get('PYLOT_DIFFTRACE') == '1': __import__('sys').stderr.write('[difftrace v_goal_route0] ts=%d route_n=%d d0=%.2f goal=(%.2f,%.2f)\n' % (timestamp.coordinates[0], len(self._route.waypoints), (ego_transform.location.distance(self._route.waypoints[0].location) if len(self._route.waypoints) > 0 else -1.0), new_goal_location.x, new_goal_location.y))
         if new_goal_location != self._goal_location:
             self._goal_location = new_goal_location
             if self._map:
```

## Dropped / not re-expressed

| candidate | fix commit | reason |
|---|---|---|
| v_remove_completed (73e7e0f) | 73e7e0f (2020-05-30) | planning/utils.py no longer contains remove_completed_waypoints at 8218ca9 (removed by dc4cc8d 'Refactored methods that compute angles and distances between vectors', 2020-06-08; logic now lives in Waypoints.remove_completed/closest_waypoint). git apply -R fails. Not re-expressed. |
| v_location_history (3a763f7) | 3a763f7 (2020-04-26) | obstacle_location_history_operator.py was restructured after the fix (ObstacleTrajectory(obstacle, trajectory) signature, loop body rewritten). git apply -R fails at hunk @61. Not re-expressed. |
| v_lidar_depth (20e1151) | 20e1151 (2020-06-04) | point_cloud.py was rewritten (type hints, renamed locals) after the fix; the normalized-depth logic is still present but the exact lines are gone. git apply -R fails at hunk @101. Not re-expressed. |
| v_prune_in_junction (760f137 behaviour-planner hunk) | 760f137 (2020-07-18) | 'if not is_intersection: remove_waypoint_if_close(5)' was superseded by 7be3b0e (OVERTAKE branch + 3.5 m in junction), ab5384a (10 m / 3 m), 793b0c2 (3->2) and 47ff456 (2->3). Lines absent at base; separate mechanism but not cleanly revertable. Not re-expressed. |
| 02c8034 ERDOSAgent visible-TL filter + max_angle /4->/3 | 02c8034 (2020-07-30) | Filter moved into ERDOSBaseAgent.send_perfect_detections (52b8570 refactor) and only runs with --simulator_traffic_light_detection (not in either conf); the angle tweak is American-style-only. Not re-expressed; v_tl_perfect carries only the world.py bbox hunk. |
| ab5384a other hunks | ab5384a (2020-08-10) | Localization Kalman noise vars (x10), hd_map __is_intersection shim (gone at base: Waypoint wrapper exposes is_junction), prune 5->10 / 3.5->3 (later changed again), TL lookahead 15->20. Bundled, partly superseded; not requested. |

## Surprises from reading the code

1. The `goal = route[1] -> route[0]` hunk is in **793b0c2 (2020-11-06)**, not in ab5384a (2020-08-10); ab5384a only moved the unchanged `route[1]` logic into `__get_goal_location`. `v_goal_route0` therefore reverts 793b0c2's goal hunk (fix_commit=793b0c2). With the dense 1 m leaderboard route (used by the challenge agent since 2019) the goal moves by one metre: inert on a straight lane.
2. 793b0c2 and 4891c00 are a bug/fix pair whose pre-state differs from the fix: pre-793b0c2 `_get_index` raised `ValueError` when no waypoint was >= 5 m away, 4891c00 returns the last waypoint instead. Hence two distinct versions `v_wp_index` (793b0c2 max-clamp bug: always the LAST waypoint) and `v_wp_index_pre` (raises). The planner waypoint list is only ~10 m long at base (goal ~10 m ahead), so the max-clamp bug moves the steering look-ahead from ~5 m to ~10 m: a weak effect on a mostly-straight lane.
3. `HDMap.are_on_same_lane` is asymmetric only through the junction rule (`waypoint1.is_junction and not waypoint2.is_junction -> False`, different-road case). `v_same_lane` can therefore only fire when the crossing vehicle's predicted path is INSIDE a junction while the ego is outside (or vice versa). A mid-block crossing is symmetric -> inert.
4. The 02c8034 bbox-None hunk sits inside the American-style branch (`height_delta > 4`) and only matters when `tl.bounding_box is None`, i.e. on the `--simulator_traffic_light_detection` path with a non-green light. On the camera path the version and base compute the same thing even for red lights. With frozen-green lights it is unreachable. Its ERDOSAgent companion hunk now lives in `ERDOSBaseAgent.send_perfect_detections` (52b8570 refactor).
5. The OVERTAKE FSM is alive at base (behaviour planner transitions after 50 s stuck and sends the state), but `PlanningOperator` ignores it (branch commented out by 7be3b0e). `v_overtake` re-enables the branch (FOT planner, no stop_for_agents) with the 35 s threshold. This is the one version whose "fix" makes the car stay stuck and whose "bug" makes it move: define the regression metric as collision/off-lane, not stuck. It needs the ego halted for > 35 s of game time, so LeadStopped must run long enough.
6. `stop_at_uncontrolled_junctions=True` in challenge.conf: the junction-stop rule is live but is skipped whenever a detected TL is "obeyed" (green counts). In Town01 all junctions are signalised, so `v_junction_stop` only fires on TL-detection misses within 13 m of a junction, and the difference is a 1-tick vs >10-tick stop.
7. 760f137's "no pruning inside intersections" behaviour-planner hunk, 7be3b0e's behaviour-planner hunk, and the three older fixes (73e7e0f, 3a763f7, 20e1151) are not cleanly revertable at 8218ca9 (lines rewritten); they are listed as dropped and not re-expressed.
8. `remove_waypoint_if_close` pops ONE route point per tick regardless of ego motion, and `__get_goal_location` changes the goal every tick, so `HDMap.compute_waypoints` (GlobalRoutePlanner A*) runs every behaviour-planner tick at base. Not a version, but relevant to runtime.

## Deployment notes

- Source versions: mount/copy `<vid>/pylot` over the image's `pylot` package (or `rsync` the whole tree) - the md5 table above is the deployment check.
- `v_speed7` is a conf-only variant: point `TEAM_CONFIG` at `<vid>/pylot/simulation/challenge/challenge.conf` (the base conf is `base/pylot/simulation/challenge/challenge.conf`).
- Difftrace: apply `<vid>.difftrace.patch` with `git apply` (or `patch -p1`) inside BOTH the base tree and the version tree used for the pair, run with `PYLOT_DIFFTRACE=1`, and capture stderr of the leaderboard process (the ERDOS operators run in-process, so stderr is the leaderboard's stderr).
- The materialised trees under `versions/` do NOT have the difftrace applied; apply it into a copy when needed.
- `_repo` is a plain clone (not shared with `~/satrp_real/pylot/pylot_repo`).
