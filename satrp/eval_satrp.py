#!/usr/bin/env python3
"""
eval_satrp.py — evaluate stochasticity-aware test reduction+prioritization
(SA-TRP) vs STRAP-style deterministic selection, on the injected benchmark,
with a HISTORY axis (cold / base / warm) and budget-fair, held-out ground truth.

Setup (per fault config = a "commit under test")
  * each scenario s has a POOL of recorded run outcomes; a run "triggers" if it
    fails (out_of_lane/collision) — or, if SATRP_TAU>0, also when min_ttc<TAU.
  * a method spends a RUN BUDGET B (counted in executions) by repeatedly choosing
    a scenario and drawing one recorded outcome (CRN: same shuffled pool across
    methods). Detection is method-specific (see below).

Ground truth (held out, no circularity)
  Seeds are split by parity: EVEN seeds define ground truth and the baseline rate
  q_s; methods may only DRAW from ODD seeds. Scenario s is a true regression for
  config c iff  p_s - q_s >= DELTA  on the held-out even seeds (Def. ground-truth).

Methods
  strap   deterministic, one run/scenario, priority = prior trigger rate; flags s
          on its single observed trigger (one-verdict)          [first-trigger]
  random  random not-yet-flagged scenario                       [first-trigger]
  uniform spread runs evenly, flag on first trigger             [first-trigger]
  oracle  knows true p_s,q_s; greedy upper bound                [first-trigger]
  satrp_*  SA-TRP (this paper): Beta-Bernoulli posteriors for p_s AND q_s; flags s
          only when r_s = P[p_s - q_s >= DELTA] >= GAMMA (posterior-confirmed),
          allocates by baseline-aware Thompson gain g = theta * 1[theta-phi>=DELTA],
          abandons s when r_s <= ETA.                            [confirmation]
          HISTORY axis:
            satrp_cold : no history. q_s unknown -> must spend budget calibrating
                         the baseline (M_CAL baseline draws/scenario, CHARGED to B);
                         uninformative prior on p_s.            (charged baseline)
            satrp_base : baseline history known/amortized (q_s from even seeds, free);
                         uninformative prior on p_s.            (amortized baseline)
            satrp_warm : baseline known/amortized + informative "no-regression" prior
                         on p_s centered at q_s (strength KAPPA). (amortized + prior)

Metrics (held-out): recall(B) overall + on flaky subset; budget-to-target (TARGET);
normalized AUC; false-positive rate (flagged non-regressions). Naive methods flag on
first trigger (no baseline model) and therefore pay in FP; SA-TRP confirms and
controls FP — recall and FP must be read together.

Env knobs: INJECT_GLOB, INJECT_OUT, SATRP_TAU(0), SATRP_DELTA(.15), SATRP_GAMMA(.9),
SATRP_ETA(.2), SATRP_KAPPA(6), SATRP_MCAL(2), SATRP_TARGET(.95), SATRP_NBOOT(200),
SATRP_GT(even).
Outputs: satrp_curves.csv, satrp_summary.csv, satrp_curves.png
"""
import os, glob, json, math
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

GLOB   = os.path.expanduser(os.environ.get("INJECT_GLOB", ""))   # runs.jsonl of one instance (data/derived/<instance>/runs.jsonl); required when run as a script
OUT    = os.path.expanduser(os.environ.get("INJECT_OUT", os.path.join(os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "results", "_unnamed")))   # results/<instance>
TAU    = float(os.environ.get("SATRP_TAU", "0.0"))
DELTA  = float(os.environ.get("SATRP_DELTA", "0.15"))
GAMMA  = float(os.environ.get("SATRP_GAMMA", "0.9"))
ETA    = float(os.environ.get("SATRP_ETA", "0.2"))
KAPPA  = float(os.environ.get("SATRP_KAPPA", "6"))      # warm-prior strength
M_CAL  = int(os.environ.get("SATRP_MCAL", "2"))         # cold baseline calib runs/scenario
KP     = float(os.environ.get("SATRP_KP", "2"))         # weak null p-prior strength
N_MIN_ABANDON = int(os.environ.get("SATRP_NMIN", "2"))  # min runs before a scenario may be abandoned
TARGET = float(os.environ.get("SATRP_TARGET", "0.95"))
NBOOT  = int(os.environ.get("SATRP_NBOOT", "200"))
MIN_SEEDS = int(os.environ.get("SATRP_MIN_SEEDS", "0"))  # drop (config,scenario) cells with < this many seeds
GT_MODE = os.environ.get("SATRP_GT_MODE", "split").lower()  # split (parity held-out) | sig (full-pool significance)
GT_CONF = float(os.environ.get("SATRP_GT_CONF", "0.9"))     # full-pool posterior confidence for sig-mode GT
GT_EVEN = os.environ.get("SATRP_GT", "even").lower() != "odd"
FLAKY_LO, FLAKY_HI = 0.2, 0.8
FAIL  = {"out_of_lane", "collision"}
# --- baseline families (see paper Table: Baselines) ---
NAIVE = ["strap", "random", "uniform", "oracle"]   # first-trigger detection / oracle ceiling
RERUN = ["rerun_any", "rerun_maj"]                 # industrial fixed-N rerun protocols (no model)
FREQ  = ["twoprop", "sprt", "apt"]                 # baseline-AWARE frequentist (need q): batch / SPRT / thresholding-bandit
PFS   = ["pfs", "eb_warm"]                          # single-population Beta-Bernoulli (flat / empirical-Bayes warm prior), baseline-UNAWARE
SATRP = ["satrp_cold", "satrp_base", "satrp_warm"] # this paper (history axis)
KNOWN_Q = set(FREQ)                                # methods that consume the known baseline rate q_s
# display / iteration order
SATRP_BF = ["satrp_bf_cold", "satrp_bf_base", "satrp_bf_warm"]  # pre-registered 2026-10-10: Bayes-factor confirmation
METHODS = (["strap", "random", "uniform"] + RERUN + PFS + FREQ + SATRP + ["oracle"])
# config knobs for the new baselines
ALPHA = float(os.environ.get("SATRP_ALPHA", "0.05"))   # test level (twoprop, sprt) — swept for frontier
BETA  = float(os.environ.get("SATRP_BETA",  "0.05"))   # sprt type-II — swept for frontier
APT_C = float(os.environ.get("SATRP_APT_C", "1.0"))    # APT confidence-radius scale — swept for frontier
CAP   = int(os.environ.get("SATRP_CAP", "8"))          # per-scenario truncation cap (sequential methods)
PFS_THRESH = float(os.environ.get("SATRP_PFS_THRESH", "0.5"))  # PFS flags P[p>=thresh]>=gamma
FPR_TARGET = float(os.environ.get("SATRP_FPR", "0.10"))        # for recall-at-fixed-FPR
TOPK_KS = [int(k) for k in os.environ.get("SATRP_TOPK", "1,3,5").split(",")]  # Top-K cutoffs (prioritization)
RNG = np.random.default_rng(0)


# ---------- small helpers ----------
def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def beta_mv(a, b):
    s = a + b
    return a / s, (a * b) / (s * s * (s + 1.0))


def r_prob(an, bn, ab, bb, delta):
    """P[p - q >= delta] for p~Beta(an,bn), q~Beta(ab,bb), normal approximation."""
    mp, vp = beta_mv(an, bn)
    mq, vq = beta_mv(ab, bb)
    sd = math.sqrt(vp + vq)
    if sd == 0.0:
        return 1.0 if (mp - mq) >= delta else 0.0
    return _ncdf((mp - mq - delta) / sd)


# ---------- data ----------
def load_pools(pattern=None):
    rows = []
    for f in glob.glob(pattern or GLOB, recursive=True):
        for ln in open(f):
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            if not d.get("engaged"):
                continue
            seed = d.get("seed")
            if seed is None:
                continue
            ttc = d.get("min_ttc")
            trig = (str(d.get("outcome")) in FAIL) or (TAU > 0 and ttc is not None and float(ttc) < TAU)
            rows.append((d.get("commit", "?"), d.get("scenario", "?"), int(seed), int(trig)))
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["config", "scenario", "seed", "trig"])
    pools = {}
    dropped = 0
    for (c, s), g in df.groupby(["config", "scenario"]):
        # depth filter: a (config,scenario) cell must have >= MIN_SEEDS distinct seeds
        if MIN_SEEDS > 0 and g["seed"].nunique() < MIN_SEEDS:
            dropped += 1
            continue
        pools.setdefault(c, {})[s] = list(zip(g["seed"].astype(int), g["trig"].astype(int)))
    if MIN_SEEDS > 0:
        print(f"[min-seeds={MIN_SEEDS}] kept cells with >= {MIN_SEEDS} seeds; dropped {dropped} shallow cells")
    return pools if pools else None


def split_gt_draw(pools):
    gt, draw = {}, {}
    for c, sc in pools.items():
        gt[c], draw[c] = {}, {}
        for s, lst in sc.items():
            gt[c][s]   = [t for (sd, t) in lst if (sd % 2 == 0) == GT_EVEN]
            draw[c][s] = [t for (sd, t) in lst if (sd % 2 == 0) != GT_EVEN]
    return gt, draw


# ---------- naive selectors (first-trigger detection) ----------
def simulate_naive(method, scen, draw_new, base_prior, true_p, budget, gt_set=None):
    # ORACLE = true F1 ceiling: it knows every (p_s,q_s), hence the true regression set.
    # It spends one budget unit per true regression (budget-fair) and flags it on the spot
    # -> precision 1.0, recall ramping with budget. (NOT a first-trigger heuristic.)
    if method == "oracle":
        found = {}
        tf = list(gt_set or [])
        tf.sort(key=lambda s: true_p.get(s, 0.0), reverse=True)   # detect the likeliest first
        t = 0
        for s in tf:
            if t >= budget:
                break
            t += 1; found[s] = t
        return found
    found, exhausted = {}, set()
    n = {s: 0 for s in scen}
    t = 0
    while t < budget:
        cand = [s for s in scen if s not in found and s not in exhausted]
        if method == "strap":
            cand = [s for s in cand if n[s] == 0]
        if not cand:
            break
        if method == "strap":
            s = max(cand, key=lambda s: base_prior.get(s, 0.0))
        elif method == "random":
            s = cand[int(RNG.integers(len(cand)))]
        elif method == "uniform":
            s = min(cand, key=lambda s: n[s])
        else:
            break
        y = draw_new[s]()
        if y is None:
            exhausted.add(s); continue
        n[s] += 1; t += 1
        if y and s not in found:
            found[s] = t            # flag on first observed trigger (one-verdict / naive)
    return found


# ---------- SA-TRP (posterior-confirmed detection, history axis) ----------
def simulate_satrp(variant, scen, draw_new, draw_base, qhist, true_p, true_q, budget, gamma=None):
    g_conf = GAMMA if gamma is None else gamma
    cold = (variant == "satrp_cold")
    warm = (variant == "satrp_warm")
    # per-scenario state.  History axis differs ONLY in the baseline posterior q_s:
    #   cold: no history  -> learn q online (charged)         qa=qb=0.5
    #   base: modest history (amortized)                      qa,qb = Jeffreys + counts
    #   warm: rich history (amortized, confident q)           counts scaled by KAPPA
    # The p_s prior is identical for ALL variants: a WEAK NULL prior centered at the
    # baseline rate qbar with strength KP (set below), encoding "a priori the new version
    # behaves like the baseline". It is NOT a directional "which scenarios regress" prior
    # (that would leak from ground truth). The variants differ ONLY in the q_s posterior
    # (strength of baseline history) and whether cold pays budget to learn it.
    a = {}; b = {}; qa = {}; qb = {}; n = {}; m = {}
    for s in scen:
        h, mm = qhist[s]                                     # raw baseline (triggers, runs)
        if cold:
            qa[s], qb[s] = 0.5, 0.5
            qbar = 0.0                                       # no history -> null assumes low rate
        elif warm:
            qa[s], qb[s] = 0.5 + KAPPA * h, 0.5 + KAPPA * (mm - h)
            qbar = h / mm if mm > 0 else 0.0
        else:                                               # base
            qa[s], qb[s] = 0.5 + h, 0.5 + (mm - h)
            qbar = h / mm if mm > 0 else 0.0
        # WEAK NULL prior on p, centered at the baseline rate: a priori the new version
        # behaves like the baseline, so r_s = P[p-q>=delta] starts near 0 and only rises
        # with observed new-version failures (no prior-only confirmations).
        a[s], b[s] = 0.5 + KP * qbar, 0.5 + KP * (1 - qbar)
        n[s] = 0; m[s] = 0
    found, abandoned = {}, set()

    def rval(s):
        return r_prob(a[s], b[s], qa[s], qb[s], DELTA)

    t = 0
    while t < budget:
        cand = []
        for s in scen:
            if s in found or s in abandoned:
                continue
            r = rval(s)
            # Abandon ONLY after the scenario has actually been observed enough times;
            # otherwise an un-tested scenario is abandoned purely from a (possibly
            # uninformative) prior — e.g. the cold-start baseline prior Beta(.5,.5) has
            # mean .5, which makes r_s tiny and would abandon everything before any run.
            if r <= ETA and n[s] >= N_MIN_ABANDON and (not cold or m[s] >= M_CAL):
                abandoned.add(s); continue
            cand.append(s)                                   # undecided -> still needs runs
        if not cand:
            break
        # NOTE: confirmation (r>=GAMMA) happens ONLY after executing a scenario (below),
        # so a regression can never be "confirmed" from the prior without evidence.
        # baseline-aware Thompson gain
        best, best_g, best_theta = None, -1.0, -1.0
        for s in cand:
            theta = RNG.beta(a[s], b[s]); phi = RNG.beta(qa[s], qb[s])
            g = theta if (theta - phi) >= DELTA else 0.0
            if g > best_g or (g == best_g and theta > best_theta):
                best, best_g, best_theta = s, g, theta
        s = best
        # cold: pay to calibrate the baseline first (charged to budget)
        if cold and m[s] < M_CAL and t < budget:
            yb = draw_base[s]()
            if yb is not None:
                qa[s] += yb; qb[s] += (1 - yb); m[s] += 1; t += 1
            if t >= budget:
                break
        y = draw_new[s]()
        if y is None:
            abandoned.add(s); continue
        a[s] += y; b[s] += (1 - y); n[s] += 1; t += 1
        r = rval(s)
        if r >= g_conf and s not in found:
            found[s] = t                                     # posterior-confirmed regression
        elif r <= ETA:
            abandoned.add(s)
    return found


# ---------- SA-TRP-BF: pre-registered refinement (docs/prereg_satrp_bf_2026-10-10.md) ----------
_BF_GRID = (np.arange(1, 400) / 400.0)          # fixed quadrature grid on (0,1) for E_q[.]
from scipy.stats import beta as _beta_dist

def bayes_factor(k, n, qa, qb, delta):
    """BF = E_q[(q+d)^k (1-q-d)^(n-k)] / E_q[q^k (1-q)^(n-k)], q ~ Beta(qa,qb), H1 point alt p=min(q+d,1-1e-3)."""
    w = _beta_dist.pdf(_BF_GRID, qa, qb); w = w / w.sum()
    q = _BF_GRID; p1 = np.minimum(q + delta, 1 - 1e-3)
    l0 = np.sum(w * q ** k * (1 - q) ** (n - k))
    l1 = np.sum(w * p1 ** k * (1 - p1) ** (n - k))
    return l1 / max(l0, 1e-300)


def simulate_satrp_bf(variant, scen, draw_new, draw_base, qhist, true_p, true_q, budget):
    """SA-TRP with a Bayes-factor (Wald-bound) confirmation test instead of P[p-q>=delta]>=gamma.
       Everything else (priors, history axis, Thompson baseline-aware allocation, cold calibration,
       N_MIN_ABANDON guard, no cap) is identical to simulate_satrp. Knob: ALPHA=BETA (SPRT ladder)."""
    cold = variant.endswith("cold"); warm = variant.endswith("warm")
    A_up = math.log((1 - BETA) / ALPHA); A_lo = math.log(BETA / (1 - ALPHA))
    a = {}; b = {}; qa = {}; qb = {}; n = {}; m = {}; kf = {}
    for s in scen:
        h, mm = qhist[s]
        if cold:
            qa[s], qb[s] = 0.5, 0.5; qbar = 0.0
        elif warm:
            qa[s], qb[s] = 0.5 + KAPPA * h, 0.5 + KAPPA * (mm - h); qbar = h / mm if mm > 0 else 0.0
        else:
            qa[s], qb[s] = 0.5 + h, 0.5 + (mm - h); qbar = h / mm if mm > 0 else 0.0
        a[s], b[s] = 0.5 + KP * qbar, 0.5 + KP * (1 - qbar)
        n[s] = 0; m[s] = 0; kf[s] = 0
    found, abandoned = {}, set()
    t = 0
    while t < budget:
        cand = [s for s in scen if s not in found and s not in abandoned]
        if not cand:
            break
        best, best_g, best_theta = None, -1.0, -1.0
        for s in cand:                                       # allocation UNCHANGED
            theta = RNG.beta(a[s], b[s]); phi = RNG.beta(qa[s], qb[s])
            g = theta if (theta - phi) >= DELTA else 0.0
            if g > best_g or (g == best_g and theta > best_theta):
                best, best_g, best_theta = s, g, theta
        s = best
        if cold and m[s] < M_CAL and t < budget:             # cold calibration UNCHANGED
            yb = draw_base[s]()
            if yb is not None:
                qa[s] += yb; qb[s] += (1 - yb); m[s] += 1; t += 1
            if t >= budget:
                break
        y = draw_new[s]()
        if y is None:
            abandoned.add(s); continue
        a[s] += y; b[s] += (1 - y); n[s] += 1; kf[s] += y; t += 1
        lbf = math.log(max(bayes_factor(kf[s], n[s], qa[s], qb[s], DELTA), 1e-300))
        if lbf >= A_up and s not in found:
            found[s] = t                                     # confirm: BF >= (1-beta)/alpha
        elif lbf <= A_lo and n[s] >= N_MIN_ABANDON and (not cold or m[s] >= M_CAL):
            abandoned.add(s)                                 # abandon: BF <= beta/(1-alpha)
    return found


# ---------- additional baselines (fair-comparison suite) ----------
def _round_robin_next(scen, n, blocked):
    cand = [s for s in scen if s not in blocked]
    return min(cand, key=lambda s: n[s]) if cand else None


def simulate_rerun(scen, draw_new, budget, rule="any"):
    """Industrial fixed-N rerun, allocated round-robin (capped at CAP runs/scenario).
       rule='any' (rerun-until-pass): flag on >=1 trigger.
       rule='maj' (k-rerun-majority): flag when triggers exceed half the runs (n>=2)."""
    n = {s: 0 for s in scen}; tr = {s: 0 for s in scen}; found, blocked = {}, set()
    t = 0
    while t < budget:
        s = _round_robin_next(scen, n, blocked)
        if s is None:
            break
        if n[s] >= CAP:
            blocked.add(s); continue
        y = draw_new[s]()
        if y is None:
            blocked.add(s); continue
        n[s] += 1; tr[s] += y; t += 1
        if s not in found:
            if rule == "any" and y:
                found[s] = t
            elif rule == "maj" and n[s] >= 2 and 2 * tr[s] > n[s]:
                found[s] = t
    return found


def simulate_sprt(scen, draw_new, q_known, budget):
    """Wald SPRT per scenario, H0: p=q vs H1: p=q+DELTA. Round-robin over undecided arms,
       truncation cap CAP; flag (accept H1) when LLR>=log((1-BETA)/ALPHA)."""
    A = math.log((1 - BETA) / ALPHA); Bnd = math.log(BETA / (1 - ALPHA))
    n = {s: 0 for s in scen}; llr = {s: 0.0 for s in scen}; found, decided = {}, set()
    t = 0
    while t < budget:
        s = _round_robin_next(scen, n, decided)
        if s is None:
            break
        if n[s] >= CAP:
            decided.add(s); continue
        q = min(max(q_known.get(s, 0.0), 1e-3), 1 - 1e-3)
        p1 = min(q + DELTA, 1 - 1e-3)
        y = draw_new[s]()
        if y is None:
            decided.add(s); continue
        n[s] += 1; t += 1
        llr[s] += math.log(p1 / q) if y else math.log((1 - p1) / (1 - q))
        if llr[s] >= A and s not in found:
            found[s] = t; decided.add(s)            # accept H1 -> regression
        elif llr[s] <= Bnd:
            decided.add(s)                          # accept H0 -> abandon
    return found


def simulate_apt(scen, draw_new, q_known, budget):
    """Thresholding-bandit (APT-style good-arm id): pull the arm minimizing the gap-to-
       threshold margin sqrt(n)*|p_hat-(q+DELTA)| (unpulled first); flag when the Hoeffding
       lower bound clears q+DELTA, abandon when the upper bound falls below it. Cap CAP."""
    n = {s: 0 for s in scen}; tr = {s: 0 for s in scen}; found, decided = {}, set()
    t = 0
    while t < budget:
        cand = [s for s in scen if s not in decided and n[s] < CAP]
        if not cand:
            break
        def margin(s):
            if n[s] == 0:
                return -1.0                          # explore unpulled arms first
            ph = tr[s] / n[s]
            return math.sqrt(n[s]) * abs(ph - (q_known.get(s, 0.0) + DELTA))
        s = min(cand, key=margin)
        y = draw_new[s]()
        if y is None:
            decided.add(s); continue
        n[s] += 1; tr[s] += y; t += 1
        ph = tr[s] / n[s]
        rad = APT_C * math.sqrt(math.log(max(t, 2.0)) / (2.0 * n[s]))
        thr = q_known.get(s, 0.0) + DELTA
        if ph - rad > thr and s not in found:
            found[s] = t; decided.add(s)
        elif ph + rad < thr:
            decided.add(s)
    return found


def simulate_pfs(scen, draw_new, budget, gamma, prior=None):
    """Single-population Beta-Bernoulli over p only (PFS-style), baseline-UNAWARE detection:
       allocate by highest posterior variance; flag when P[p>=PFS_THRESH]>=gamma.
       prior=None -> flat Jeffreys Beta(.5,.5) (Meta PFS).
       prior={s:(a0,b0)} -> empirical-Bayes 'warm' prior with pseudo-counts from history
       (ablation: same informative prior as SA-TRP-warm but without the baseline p-q comparison)."""
    if prior is None:
        a = {s: 0.5 for s in scen}; b = {s: 0.5 for s in scen}
    else:
        a = {s: prior[s][0] for s in scen}; b = {s: prior[s][1] for s in scen}
    n = {s: 0 for s in scen}
    found, blocked = {}, set()
    t = 0
    while t < budget:
        cand = [s for s in scen if s not in found and s not in blocked and n[s] < CAP]
        if not cand:
            break
        s = max(cand, key=lambda s: (a[s] * b[s]) / ((a[s] + b[s]) ** 2 * (a[s] + b[s] + 1)))
        y = draw_new[s]()
        if y is None:
            blocked.add(s); continue
        a[s] += y; b[s] += (1 - y); n[s] += 1; t += 1
        m, v = beta_mv(a[s], b[s]); sd = math.sqrt(v)
        pge = 1.0 if sd == 0 else _ncdf((m - PFS_THRESH) / sd)
        if pge >= gamma:
            found[s] = t
    return found


def _bh_reject(pvals, alpha):
    """Benjamini-Hochberg: return the set of indices rejected at FDR=alpha."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items); rej = set(); kmax = 0
    for i, (k, p) in enumerate(items, start=1):
        if p <= alpha * i / m:
            kmax = i
    for i, (k, p) in enumerate(items, start=1):
        if i <= kmax:
            rej.add(k)
    return rej


def simulate_twoprop(scen, draw_new, q_known, qn_known, Bgrid, alpha=None):
    """Fixed-budget BATCH two-proportion test, baseline-aware, with BH-FDR across scenarios.
       Round-robin allocate to max(Bgrid); at each budget B test H0: p<=q+DELTA via a one-sided
       z-test on Agresti-adjusted p_hat, BH-correct, flag significant. Returns first-B found.
       Baseline q is known from a deep pool (qn_known runs), so its variance term uses that n."""
    alpha = ALPHA if alpha is None else alpha
    maxB = max(Bgrid)
    order, blocked = [], set(); n = {s: 0 for s in scen}
    t = 0
    while t < maxB:
        s = _round_robin_next(scen, n, blocked)
        if s is None:
            break
        if n[s] >= CAP:
            blocked.add(s); continue
        y = draw_new[s]()
        if y is None:
            blocked.add(s); continue
        n[s] += 1; t += 1; order.append((s, y))
    found = {}
    for B in sorted(Bgrid):
        cnt = {s: [0, 0] for s in scen}              # [triggers, runs] at budget B
        for s, y in order[:B]:
            cnt[s][0] += y; cnt[s][1] += 1
        pvals = {}
        for s in scen:
            k, nn = cnt[s]
            if nn == 0:
                continue
            ph = (k + 1.0) / (nn + 2.0)              # Agresti-Coull adjust (avoids SE=0)
            q = min(max(q_known.get(s, 0.0), 1e-6), 1 - 1e-6)
            nq = max(qn_known.get(s, 1), 1)          # baseline known with many runs
            se = math.sqrt(ph * (1 - ph) / nn + q * (1 - q) / nq)
            z = (ph - q - DELTA) / se if se > 0 else 0.0
            pvals[s] = 1.0 - _ncdf(z)                # one-sided H1: p>q+DELTA
        for s in _bh_reject(pvals, alpha):
            found.setdefault(s, B)
    return found


def _budget_to_target(rps, found_frac, target):
    x, y = np.asarray(rps, float), np.asarray(found_frac, float)
    for i in range(len(y)):
        if y[i] >= target:
            if i == 0:
                return float(x[0])
            x0, x1, y0, y1 = x[i-1], x[i], y[i-1], y[i]
            return float(x0 + (target - y0) * (x1 - x0) / (y1 - y0)) if y1 > y0 else float(x1)
    return float("inf")


def _auc(rps, found_frac):
    x, y = np.asarray(rps, float), np.asarray(found_frac, float)
    trapz = getattr(np, "trapezoid", np.trapz)
    return float(trapz(y, x) / (x[-1] - x[0])) if x[-1] > x[0] else float("nan")


def run(pattern=None, gamma=None, out=None, quiet=False):
    global RNG
    RNG = np.random.default_rng(0)              # reset for reproducibility across a gamma sweep
    g_conf = GAMMA if gamma is None else gamma
    outdir = OUT if out is None else os.path.expanduser(out); os.makedirs(outdir, exist_ok=True)
    pools = load_pools(pattern)
    if pools is None:
        print("No engaged injection data yet."); return None
    base_cfg = "BASE" if "BASE" in pools else next((c for c in pools if "none" in str(c).lower()), None)
    if base_cfg is None:
        print("No BASE config — cannot define ground-truth regressions."); return None

    scen = sorted({s for c in pools for s in pools[c]})

    def mean0(lst):
        return float(np.mean(lst)) if lst else 0.0

    if GT_MODE == "sig":
        # Significance-aware, FULL-POOL ground truth (no parity split): a cell is a
        # regression iff its full-pool effect size >= DELTA AND the full-pool posterior
        # P[p - q >= DELTA] >= GT_CONF (a two-proportion confidence using ALL seeds).
        # Methods still DRAW from the full pool but only a budget-limited subsample, so
        # the GT (all seeds) is a strictly richer test than anything a method observes
        # -> not circular, and it refuses to label high-variance noise as a regression.
        full = {c: {s: [t for (_, t) in lst] for s, lst in sc.items()} for c, sc in pools.items()}
        gt_pools = draw_pools = full
    else:
        gt_pools, draw_pools = split_gt_draw(pools)

    # baseline: history posterior and (for cold) a draw pool
    base_gt   = {s: mean0(gt_pools[base_cfg].get(s, [])) for s in scen}
    qhist = {}
    for s in scen:
        h = sum(gt_pools[base_cfg].get(s, [])); mm = len(gt_pools[base_cfg].get(s, []))
        qhist[s] = (h, mm)                                  # raw baseline (triggers, runs)
    base_draw_pool = {s: list(draw_pools[base_cfg].get(s, [])) for s in scen}

    def is_regression(p_lst, s):
        """ground-truth test for a cell with outcomes p_lst against baseline scenario s."""
        if not p_lst or (mean0(p_lst) - base_gt.get(s, 0.0)) < DELTA:
            return False
        if GT_MODE != "sig":
            return True                                     # parity-split: point-estimate gap >= DELTA
        k_p, n_p = sum(p_lst), len(p_lst)                   # full-pool counts for the test version
        k_q, n_q = qhist[s]                                 # full-pool counts for the baseline
        r = r_prob(0.5 + k_p, 0.5 + (n_p - k_p), 0.5 + k_q, 0.5 + (n_q - k_q), DELTA)
        return r >= GT_CONF                                 # full-pool two-proportion confidence

    configs = [c for c in pools if c != base_cfg]
    truth, flaky_set, flak = {}, {}, []
    for c in configs:
        truth[c], flaky_set[c] = {}, set()
        for s in scen:
            if not gt_pools[c].get(s):
                continue
            if is_regression(gt_pools[c][s], s):
                truth[c][s] = mean0(gt_pools[c][s])
                p_draw = mean0(draw_pools[c].get(s, [])); flak.append(p_draw)
                if FLAKY_LO <= p_draw <= FLAKY_HI:
                    flaky_set[c].add(s)
    n_faults = sum(len(v) for v in truth.values())
    n_flaky  = sum(len(v) for v in flaky_set.values())
    if not quiet:
        gtdesc = f"sig(full-pool, conf={GT_CONF})" if GT_MODE == "sig" else f"split({'even' if GT_EVEN else 'odd'} seeds)"
        print(f"trigger={'fail-only' if TAU==0 else f'fail|ttc<{TAU}'}  GT={gtdesc}  "
              f"DELTA={DELTA} GAMMA={g_conf} ETA={ETA} KAPPA={KAPPA} M_CAL={M_CAL} KP={KP}")
        print(f"configs={len(configs)} scenarios={len(scen)} ground-truth faults={n_faults} "
              f"(flaky={n_flaky}; median draw-prob={np.median(flak):.2f})" if flak else "no faults yet")
    if n_faults < 3:
        print("Too few held-out faults so far — re-run when more campaign data lands."); return None

    K = len(scen)
    cap = max((sum(len(draw_pools[c].get(s, [])) for s in scen) for c in configs), default=K)
    maxB = min(5 * K, cap)
    step = max(1, K // 6)
    Bgrid = list(range(K, maxB + 1, step)) or [maxB]

    subsets = ["all", "flaky"] if n_flaky >= 3 else ["all"]
    rec = {sub: {m: {B: [] for B in Bgrid} for m in METHODS} for sub in subsets}
    fp  = {m: {B: [] for B in Bgrid} for m in METHODS}
    f1d = {m: {B: [] for B in Bgrid} for m in METHODS}
    # --- prioritization accumulators (cost = total runs; found[s] is the run position of the flag) ---
    apf = {m: [] for m in METHODS}                              # APFDc (cost-cognizant, uniform run cost)
    pk  = {m: {kk: [] for kk in TOPK_KS} for m in METHODS}      # Top-K recall
    pkp = {m: {kk: [] for kk in TOPK_KS} for m in METHODS}      # Top-K precision (of the K earliest flags)

    for _ in range(NBOOT):
        for c in configs:
            tf = set(truth[c])
            if not tf:
                continue
            ff = flaky_set[c]
            nonreg = [s for s in scen if s not in tf]
            Pn = {s: list(RNG.permutation(draw_pools[c].get(s) or [0])) for s in scen}
            Pb = {s: list(RNG.permutation(base_draw_pool.get(s) or [0])) for s in scen}
            true_p = {s: mean0(draw_pools[c].get(s, [])) for s in scen}
            true_q = {s: mean0(base_draw_pool.get(s, [])) for s in scen}
            q_known = {s: (qhist[s][0] / qhist[s][1] if qhist[s][1] else 0.0) for s in scen}  # amortized baseline
            qn_known = {s: qhist[s][1] for s in scen}                                          # baseline sample size
            for mth in METHODS:
                ni = {s: 0 for s in scen}; mi = {s: 0 for s in scen}
                def dnew(s, ni=ni):
                    if ni[s] >= len(Pn[s]): return None
                    v = Pn[s][ni[s]]; ni[s] += 1; return int(v)
                def dbase(s, mi=mi):
                    if mi[s] >= len(Pb[s]): return None
                    v = Pb[s][mi[s]]; mi[s] += 1; return int(v)
                draw_new = {s: (lambda s=s: dnew(s)) for s in scen}
                draw_base = {s: (lambda s=s: dbase(s)) for s in scen}
                maxB = max(Bgrid)
                if mth in NAIVE:
                    found = simulate_naive(mth, scen, draw_new, base_gt, true_p, maxB, gt_set=tf)
                elif mth == "rerun_any":
                    found = simulate_rerun(scen, draw_new, maxB, rule="any")
                elif mth == "rerun_maj":
                    found = simulate_rerun(scen, draw_new, maxB, rule="maj")
                elif mth == "pfs":
                    found = simulate_pfs(scen, draw_new, maxB, gamma=g_conf)
                elif mth == "eb_warm":
                    # empirical-Bayes prior on p centered at the historical rate q_bar, SAME
                    # weak-null strength KP as SA-TRP's p-prior -> isolates baseline-aware detection.
                    qbar = {s: (qhist[s][0] / qhist[s][1] if qhist[s][1] else 0.0) for s in scen}
                    eb_prior = {s: (0.5 + KP * qbar[s], 0.5 + KP * (1 - qbar[s])) for s in scen}
                    found = simulate_pfs(scen, draw_new, maxB, gamma=g_conf, prior=eb_prior)
                elif mth == "sprt":
                    found = simulate_sprt(scen, draw_new, q_known, maxB)
                elif mth == "apt":
                    found = simulate_apt(scen, draw_new, q_known, maxB)
                elif mth == "twoprop":
                    found = simulate_twoprop(scen, draw_new, q_known, qn_known, Bgrid)
                elif mth in SATRP_BF:
                    found = simulate_satrp_bf(mth, scen, draw_new, draw_base, qhist, true_p, true_q, maxB)
                else:
                    found = simulate_satrp(mth, scen, draw_new, draw_base, qhist, true_p, true_q,
                                           maxB, gamma=g_conf)
                # --- prioritization: APFDc + Top-K over the induced flag order ---
                # found[s] = run position at which s was flagged; rank scenarios by it
                # (unflagged -> inf). APFDc = mean %faults-detected over run cost 1..maxB.
                if tf:
                    m_tf = len(tf)
                    # Only FLAGGED scenarios form the prioritized list; unflagged ones are
                    # never surfaced to the engineer, so they count neither as hits nor as
                    # list slots (the old version ranked all scenarios with unflagged -> inf
                    # and alphabetical fill, which let unflagged true faults inflate the
                    # numerator above the flagged-only denominator -> precision > 1).
                    ranked = sorted(found, key=lambda s: (found[s], s))
                    for kk in TOPK_KS:
                        top = ranked[:kk]
                        hits = len(set(top) & tf)
                        pk[mth][kk].append(hits / m_tf)                                      # Top-K recall
                        pkp[mth][kk].append((hits / len(top)) if top else float("nan"))      # Top-K precision
                    det = [sum(1 for f in tf if found.get(f, math.inf) <= B) / m_tf
                           for B in range(1, maxB + 1)]
                    apf[mth].append(sum(det) / len(det))
                for B in Bgrid:
                    flagged = {s for s, ft in found.items() if ft <= B}
                    tp = len(flagged & tf)
                    recall = tp / len(tf)
                    prec = tp / len(flagged) if flagged else 0.0
                    f1 = (2 * prec * recall / (prec + recall)) if (prec + recall) > 0 else 0.0
                    rec["all"][mth][B].append(recall)
                    if "flaky" in subsets and ff:
                        rec["flaky"][mth][B].append(len(flagged & ff) / len(ff))
                    fp[mth][B].append((len(flagged - tf) / len(nonreg)) if nonreg else 0.0)
                    f1d[mth][B].append(f1)

    # assemble
    rows, summ_rows = [], []
    for sub in subsets:
        for mth in METHODS:
            curve = [float(np.mean(rec[sub][mth][B])) for B in Bgrid]
            rps = [round(B / K, 3) for B in Bgrid]
            for B, mc in zip(Bgrid, curve):
                v = rec[sub][mth][B]
                rows.append(dict(subset=sub, method=mth, budget=B, runs_per_scenario=round(B / K, 3),
                                 recall=float(np.mean(v)), ci=float(1.96 * np.std(v) / np.sqrt(len(v)))))
            i2 = min(range(len(Bgrid)), key=lambda i: abs(Bgrid[i] - 2 * K))
            fp2 = float(np.mean(fp[mth][Bgrid[i2]])) if sub == "all" else float("nan")
            f1curve = [float(np.mean(f1d[mth][B])) for B in Bgrid]
            f12 = f1curve[i2] if sub == "all" else float("nan")
            f1auc = _auc(rps, f1curve) if sub == "all" else float("nan")
            # recall at fixed FPR: best recall over the budget sweep with overall FP <= FPR_TARGET
            if sub == "all":
                fpcurve = [float(np.mean(fp[mth][B])) for B in Bgrid]
                ok = [curve[i] for i in range(len(Bgrid)) if fpcurve[i] <= FPR_TARGET]
                rec_at_fpr = float(max(ok)) if ok else 0.0
            else:
                rec_at_fpr = float("nan")
            row = dict(subset=sub, method=mth, recall_at_2x=curve[i2],
                       budget_to_target_rps=_budget_to_target(rps, curve, TARGET),
                       auc=_auc(rps, curve), fp_at_2x=fp2,
                       f1_at_2x=f12, f1_auc=f1auc, recall_at_fpr=rec_at_fpr)
            if sub == "all":
                row["apfdc"] = float(np.mean(apf[mth])) if apf[mth] else float("nan")
                for kk in TOPK_KS:
                    row[f"topk{kk}_rec"]  = float(np.mean(pk[mth][kk]))  if pk[mth][kk]  else float("nan")
                    vals = [v for v in pkp[mth][kk] if v == v]   # drop NaN (no flags in top-K)
                    row[f"topk{kk}_prec"] = float(np.mean(vals)) if vals else float("nan")
            summ_rows.append(row)
    cur = pd.DataFrame(rows); summ = pd.DataFrame(summ_rows)
    if not quiet:
        cur.to_csv(f"{outdir}/satrp_curves.csv", index=False)
        summ.to_csv(f"{outdir}/satrp_summary.csv", index=False)
        for sub in subsets:
            s = summ[summ.subset == sub].set_index("method")
            print(f"\n=== subset: {sub} (GAMMA={g_conf}) ===")
            hdr = f"{'method':11s} {'recall@2x':>10} {'AUC':>7}"
            hdr += f" {'FP@2x':>7} {'F1@2x':>7} {'F1auc':>7}" if sub == "all" else ""
            print(hdr)
            for mth in METHODS:
                line = f"{mth:11s} {s.loc[mth,'recall_at_2x']:>10.3f} {s.loc[mth,'auc']:>7.3f}"
                if sub == "all":
                    line += f" {s.loc[mth,'fp_at_2x']:>7.3f} {s.loc[mth,'f1_at_2x']:>7.3f} {s.loc[mth,'f1_auc']:>7.3f}"
                print(line)
            key = "f1_auc" if sub == "all" else "auc"
            print(f"  {key}: satrp_base vs STRAP {s.loc['satrp_base',key]-s.loc['strap',key]:+.3f} | "
                  f"vs Uniform {s.loc['satrp_base',key]-s.loc['uniform',key]:+.3f}")
            print(f"  history axis ({key}): cold {s.loc['satrp_cold',key]:.3f} -> "
                  f"base {s.loc['satrp_base',key]:.3f} -> warm {s.loc['satrp_warm',key]:.3f}")

    # figure
    if quiet:
        return summ
    try:
        sty = {"strap": ("#d62728", "STRAP (1 run/scen)"), "random": ("#bbbbbb", "Random"),
               "uniform": ("#9467bd", "Uniform-repeat"),
               "rerun_any": ("#e377c2", "Rerun-until-pass"), "rerun_maj": ("#c49c94", "k-rerun-majority"),
               "pfs": ("#ff7f0e", "PFS Beta (no baseline)"),
               "eb_warm": ("#ffbb78", "EB-PFS (warm prior, no baseline)"),
               "twoprop": ("#7f7f7f", "Two-prop test+BH"), "sprt": ("#bcbd22", "SPRT (Wald)"),
               "apt": ("#aec7e8", "Thresholding bandit (APT)"),
               "satrp_cold": ("#8c564b", "SA-TRP (no history)"),
               "satrp_base": ("#2ca02c", "SA-TRP (baseline known)"),
               "satrp_warm": ("#17becf", "SA-TRP (full history)"),
               "oracle": ("#1f77b4", "Oracle")}
        fig, axes = plt.subplots(1, len(subsets), figsize=(6.8 * len(subsets), 4.3), squeeze=False)
        for ax, sub in zip(axes[0], subsets):
            d0 = cur[cur.subset == sub]
            for mth in METHODS:
                d = d0[d0.method == mth]; col, lab = sty.get(mth, ("#333333", mth))
                fmt = "o--" if mth == "random" else "o-"
                ax.plot(d.runs_per_scenario, d.recall, fmt, color=col, label=lab,
                        lw=2.4 if mth.startswith("satrp") else 1.3)
                ax.fill_between(d.runs_per_scenario, d.recall - d.ci, d.recall + d.ci, color=col, alpha=.10)
            ax.axhline(TARGET, ls=":", c="gray", lw=1)
            ax.set_xlabel("run budget (runs per scenario)")
            ax.set_ylabel("fraction of true regressions detected")
            ax.set_title(f"{'All' if sub=='all' else 'Flaky'} faults (held-out ground truth)")
            ax.set_ylim(0, 1.02); ax.grid(alpha=.3); ax.legend(fontsize=7.5)
        fig.tight_layout(); fig.savefig(f"{outdir}/satrp_curves.png", dpi=140)
        print(f"\nwrote {outdir}/satrp_curves.png")
    except Exception as e:
        print("figure skipped:", e)
    return summ


if __name__ == "__main__":
    run()
