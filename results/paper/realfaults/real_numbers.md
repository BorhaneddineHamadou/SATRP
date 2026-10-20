# Real-fault validation anchor — numbers (generated 2026-10-20 11:24)

Trigger T1 = straight: trace contact; leaderboard: collision|red_light|outside_route_lanes|route_dev (blocked/timeout separate).
T2 = T1|blocked|timeout (sensitivity). GT = one-sided Fisher p<=0.05 AND gap>=0.15 (same rule as the mutation matrices).

## pylot / lb block — 480 BASE runs, 8 versions, 12 scenarios
BASE trigger rate: mean 0.487; cells with q>=0.85 (saturated, undetectable): 5/12; q==0: 1
BASE outcome mix: collision 0.056, red_light 0.415, ool 0.054, route_dev 0.000, blocked 0.002, timeout 0.004

| version | n | T1 rate | base T1 | pooled gap | pooled Fisher p | GT cells full (T1) | GT cells sep (T1) | GT full (T2) | T2 rate | base T2 | collision | red | ool | blocked | timeout |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v_goal_route0 (likely_inert) | 288 | 0.483 | 0.487 | -0.005 | 0.58 | 0/12 | 0/12 | 0/12 | 0.483 | 0.490 | 0.038/0.056 | 0.417/0.415 | 0.059/0.054 | 0.000/0.002 | 0.014/0.004 |
| v_junction_stop (likely_inert) | 288 | 0.507 | 0.487 | +0.019 | 0.33 | 0/12 | 0/12 | 0/12 | 0.507 | 0.490 | 0.059/0.056 | 0.417/0.415 | 0.087/0.054 | 0.000/0.002 | 0.010/0.004 |
| v_overtake (ready) | 288 | 0.503 | 0.487 | +0.016 | 0.36 | 0/12 | 0/12 | 0/12 | 0.503 | 0.490 | 0.052/0.056 | 0.417/0.415 | 0.066/0.054 | 0.000/0.002 | 0.000/0.004 |
| v_same_lane (ready) | 288 | 0.486 | 0.487 | -0.001 | 0.54 | 0/12 | 0/12 | 0/12 | 0.490 | 0.490 | 0.104/0.056 | 0.413/0.415 | 0.049/0.054 | 0.003/0.002 | 0.062/0.004 |
| v_speed7 (ready) | 288 | 0.479 | 0.487 | -0.008 | 0.62 | 0/12 | 2/12 | 0/12 | 0.479 | 0.490 | 0.073/0.056 | 0.417/0.415 | 0.080/0.054 | 0.000/0.002 | 0.014/0.004 |
| v_tl_perfect (likely_inert) | 288 | 0.503 | 0.487 | +0.016 | 0.36 | 0/12 | 0/12 | 0/12 | 0.503 | 0.490 | 0.056/0.056 | 0.420/0.415 | 0.052/0.054 | 0.000/0.002 | 0.007/0.004 |
| v_wp_index (ready) | 288 | 1.000 | 0.487 | +0.512 | 2.2e-65 | 7/12 | 7/12 | 7/12 | 1.000 | 0.490 | 0.462/0.056 | 0.167/0.415 | 0.670/0.054 | 0.167/0.002 | 0.490/0.004 |
| v_wp_index_pre (likely_inert) | 288 | 0.406 | 0.487 | -0.081 | 0.99 | 0/12 | 0/12 | 7/12 | 1.000 | 0.490 | 0.000/0.056 | 0.406/0.415 | 0.000/0.054 | 0.167/0.002 | 0.833/0.004 |

Null calibration (all versions == BASE), expected GT cells over 8 versions: full 0.9±0.9, sep 0.6±0.8; empirical odd-vs-even BASE pseudo-version: 0 GT cells / 12
OBSERVED GT cells (T1): full 7, sep 9

GT cells (full, T1): v_wp_index×s1#rt0 p=1.00 q=0.05 (P=1.3e-15, sep); v_wp_index×s1#rt1 p=1.00 q=0.28 (P=1.7e-09, sep); v_wp_index×s3#rt0 p=1.00 q=0.00 (P=4.0e-18, sep); v_wp_index×s3#rt1 p=1.00 q=0.20 (P=4.2e-11, sep); v_wp_index×s4#rt0 p=1.00 q=0.03 (P=1.0e-16, sep); v_wp_index×s4#rt1 p=1.00 q=0.25 (P=5.2e-10, sep); v_wp_index×s8#rt4 p=1.00 q=0.10 (P=8.2e-14, sep)
Additional GT cells under T2 only (blocked/timeout driven): v_wp_index_pre×s1#rt0 p=1.00 q=0.07; v_wp_index_pre×s1#rt1 p=1.00 q=0.28; v_wp_index_pre×s3#rt0 p=1.00 q=0.00; v_wp_index_pre×s3#rt1 p=1.00 q=0.20; v_wp_index_pre×s4#rt0 p=1.00 q=0.03; v_wp_index_pre×s4#rt1 p=1.00 q=0.25; v_wp_index_pre×s8#rt4 p=1.00 q=0.10

## tfpp / lb block — 480 BASE runs, 2 versions, 12 scenarios
BASE trigger rate: mean 0.000; cells with q>=0.85 (saturated, undetectable): 0/12; q==0: 12
BASE outcome mix: collision 0.000, red_light 0.000, ool 0.000, route_dev 0.000, blocked 0.000, timeout 0.027

| version | n | T1 rate | base T1 | pooled gap | pooled Fisher p | GT cells full (T1) | GT cells sep (T1) | GT full (T2) | T2 rate | base T2 | collision | red | ool | blocked | timeout |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v_lidar_stale | 288 | 0.007 | 0.000 | +0.007 | 0.14 | 0/12 | 0/12 | 0/12 | 0.035 | 0.027 | 0.007/0.000 | 0.000/0.000 | 0.003/0.000 | 0.003/0.000 | 0.028/0.027 |
| v_speed_offset | 288 | 0.038 | 0.000 | +0.038 | 1.8e-05 | 1/12 | 1/12 | 1/12 | 0.059 | 0.027 | 0.038/0.000 | 0.000/0.000 | 0.000/0.000 | 0.000/0.000 | 0.021/0.027 |

Null calibration (all versions == BASE), expected GT cells over 2 versions: full 0.0±0.0, sep 0.0±0.0; empirical odd-vs-even BASE pseudo-version: 0 GT cells / 12
OBSERVED GT cells (T1): full 1, sep 1

GT cells (full, T1): v_speed_offset×s7#rt0 p=0.38 q=0.00 (P=4.7e-05, sep)

## tfpp / straight block — 1200 BASE runs, 2 versions, 30 scenarios
BASE trigger rate: mean 0.306; cells with q>=0.85 (saturated, undetectable): 9/30; q==0: 20

| version | n | T1 rate | base T1 | pooled gap | pooled Fisher p | GT cells full (T1) | GT cells sep (T1) | GT full (T2) | T2 rate | base T2 |
|---|---|---|---|---|---|---|---|---|---|---|
| v_lidar_stale | 720 | 0.307 | 0.306 | +0.001 | 0.5 | 0/30 | 0/30 | 0/30 | 0.307 | 0.306 |
| v_speed_offset | 720 | 0.354 | 0.306 | +0.048 | 0.016 | 5/30 | 4/30 | 5/30 | 0.354 | 0.306 |

Null calibration (all versions == BASE), expected GT cells over 2 versions: full 0.1±0.3, sep 0.0±0.2; empirical odd-vs-even BASE pseudo-version: 0 GT cells / 30
OBSERVED GT cells (T1): full 5, sep 4

GT cells (full, T1): v_speed_offset×ProxCrossingTraffic#120 p=1.00 q=0.00 (P=4.0e-18, sep); v_speed_offset×ProxCutIn#63 p=0.92 q=0.28 (P=3.7e-07, sep); v_speed_offset×ProxOncomingDrift#103 p=0.33 q=0.00 (P=1.7e-04, sep); v_speed_offset×ProxOncomingDrift#115 p=1.00 q=0.00 (P=4.0e-18, sep); v_speed_offset×ProxOncomingDrift#119 p=0.29 q=0.00 (P=5.6e-04)

## Pre-registered mechanism tests — TF++ straight block (versions.json covering vs negative-control classes)
| version | class | role | n | p | q | gap | Fisher p |
|---|---|---|---|---|---|---|---|
| v_lidar_stale | ProxCrossingTraffic | covering | 144 | 0.181 | 0.167 | +0.014 | 0.41 |
| v_lidar_stale | ProxCutIn | covering | 192 | 0.516 | 0.522 | -0.006 | 0.59 |
| v_lidar_stale | ProxLeadDecel | covering | 96 | 0.000 | 0.000 | +0.000 | 1 |
| v_lidar_stale | ProxLeadStopped | NEG-CONTROL | 96 | 0.000 | 0.000 | +0.000 | 1 |
| v_lidar_stale | ProxOncomingDrift | covering | 192 | 0.500 | 0.500 | +0.000 | 0.54 |
| v_lidar_stale | ALL covering | pooled | 624 | 0.354 | 0.353 | +0.001 | 0.5 |
| v_speed_offset | ProxCrossingTraffic | covering | 144 | 0.167 | 0.167 | +0.000 | 0.55 |
| v_speed_offset | ProxCutIn | covering | 192 | 0.490 | 0.522 | -0.032 | 0.79 |
| v_speed_offset | ProxLeadDecel | covering | 96 | 0.010 | 0.000 | +0.010 | 0.38 |
| v_speed_offset | ProxLeadStopped | covering | 96 | 0.010 | 0.000 | +0.010 | 0.38 |
| v_speed_offset | ProxOncomingDrift | covering | 192 | 0.703 | 0.500 | +0.203 | 4.3e-06 |
| v_speed_offset | ALL covering | pooled | 720 | 0.354 | 0.306 | +0.048 | 0.016 |

## Per-class rates — leaderboard block (post-hoc mapping; Pylot pre-registration used the Prox templates which Pylot did not run)
### tfpp: T1 rate per class (version / base), n per class = 48 version / 80 base
| version | s1 | s3 | s4 | s7 | s8 | s9 | any-failure T2 |
|---|---|---|---|---|---|---|---|
| base | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.03 |
| v_lidar_stale | 0.02 | 0.00 | 0.02 | 0.00 | 0.00 | 0.00 | 0.03 |
| v_speed_offset | 0.00 | 0.02 | 0.02 | 0.19** | 0.00 | 0.00 | 0.06 |
(** = one-sided Fisher p<=0.05 vs base at class level)

### pylot: T1 rate per class (version / base), n per class = 48 version / 80 base
| version | s1 | s3 | s4 | s7 | s8 | s9 | any-failure T2 |
|---|---|---|---|---|---|---|---|
| base | 0.16 | 0.10 | 0.14 | 0.97 | 0.55 | 1.00 | 0.49 |
| v_goal_route0 | 0.17 | 0.04 | 0.12 | 1.00 | 0.56 | 1.00 | 0.48 |
| v_junction_stop | 0.19 | 0.21 | 0.15 | 1.00 | 0.50 | 1.00 | 0.51 |
| v_overtake | 0.21 | 0.15 | 0.12 | 1.00 | 0.54 | 1.00 | 0.50 |
| v_same_lane | 0.25 | 0.02 | 0.12 | 0.98 | 0.54 | 1.00 | 0.49 |
| v_speed7 | 0.00 | 0.21 | 0.06 | 1.00 | 0.60 | 1.00 | 0.48 |
| v_tl_perfect | 0.21 | 0.06 | 0.17 | 1.00 | 0.58 | 1.00 | 0.50 |
| v_wp_index | 1.00** | 1.00** | 1.00** | 1.00 | 1.00** | 1.00 | 1.00 |
| v_wp_index_pre | 0.00 | 0.00 | 0.00 | 0.96 | 0.48 | 1.00 | 1.00 |
(** = one-sided Fisher p<=0.05 vs base at class level)
