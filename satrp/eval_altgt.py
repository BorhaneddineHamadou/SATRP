#!/usr/bin/env python3
"""
eval_altgt.py  --  ALTERNATIVE-ground-truth evaluation (non-destructive).

Reuses every method simulator and metric helper from eval_satrp.py UNCHANGED.
The ONLY thing this file changes is how ground truth is defined, to break the
circularity in which the sig-GT label and SA-TRP's confirmation share a rule:

  * gt_mode="design"  (for the INJECTION and OPENPILOT instances)
        A cell is a regression iff it is an INJECTED fault on one of its
        INTENDED scenarios -- read from the injection design, NOT from the
        outcomes.  Fully independent of the data the methods draw from
        (no Issue A, no Issue B).
        Variant "design_eff" additionally requires a real full-pool effect
        (p_hat - q_hat >= DELTA), a point-estimate gate (still not SA-TRP's
        Bayesian posterior).

  * gt_mode="fisher"  (for the AUTOWARE instance, which has no design label)
        A cell is a regression iff a one-sided Fisher EXACT test (p > q)
        rejects at level ALPHA on the full pool AND p_hat - q_hat >= DELTA.
        Exact combinatorial test -- different machinery from SA-TRP's
        normal-approx Beta posterior (mitigates Issue B).

Nothing in eval_satrp.py is modified.  We only read its functions/constants.
Run:  python3 eval_altgt.py
"""
import os, sys, math, json, glob
import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_satrp as E

ALPHA = float(os.environ.get("ALTGT_ALPHA", "0.05"))   # Fisher significance level
H = os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------- design labels: which (config, scenario) cells are injected-intended ----------
def load_intended(pattern):
    """Return {config: set(intended scenarios)} from the raw JSONL `intended_scenarios`."""
    intended = {}
    for f in glob.glob(pattern, recursive=True):
        for ln in open(f):
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            c = d.get("commit", "?")
            ins = d.get("intended_scenarios") or []
            if ins:
                intended.setdefault(c, set()).update(ins)
    return intended


def _mean0(lst):
    return float(np.mean(lst)) if lst else 0.0


def run_altgt(pattern, gt_mode, gamma, hist_n=None, separate=False):
    """Replicates eval_satrp.run's metric loop but with an ALTERNATIVE truth set.
       Returns a dict {method: {f1_auc, fp_at_2x, recall_at_2x, f1_at_2x}} plus meta."""
    rng = np.random.default_rng(0)
    E.RNG = rng                                            # simulators read E.RNG
    pools = E.load_pools(pattern)
    if pools is None:
        return None
    base_cfg = "BASE" if "BASE" in pools else next((c for c in pools if "none" in str(c).lower()), None)
    if base_cfg is None:
        return None
    scen = sorted({s for c in pools for s in pools[c]})

    # full-pool view (methods draw a budget-limited subsample of this; GT may use all of it)
    full = {c: {s: [t for (_, t) in lst] for s, lst in sc.items()} for c, sc in pools.items()}
    if separate:
        # BUDGET-SEPARATED: GT labels (and amortised baseline history) from the GT seed half
        # (E.GT_EVEN), methods draw ONLY from the other half -- same convention as
        # eval_satrp's split mode, but with the Fisher-exact rule instead of a point gap.
        gt_pools, draw_pools = E.split_gt_draw(pools)
    else:
        gt_pools = draw_pools = full
    base_gt = {s: _mean0(gt_pools[base_cfg].get(s, [])) for s in scen}
    qhist = {}
    for s in scen:
        h = sum(gt_pools[base_cfg].get(s, [])); mm = len(gt_pools[base_cfg].get(s, []))
        qhist[s] = (h, mm)
    base_draw_pool = {s: list(draw_pools[base_cfg].get(s, [])) for s in scen}

    intended = load_intended(pattern) if gt_mode.startswith("design") else {}

    def is_reg(c, s, p_lst):
        eff = _mean0(p_lst) - base_gt.get(s, 0.0)
        if gt_mode == "design":
            return s in intended.get(c, set())
        if gt_mode == "design_eff":
            return (s in intended.get(c, set())) and (eff >= E.DELTA)
        if gt_mode == "fisher":
            if eff < E.DELTA:
                return False
            k_p, n_p = sum(p_lst), len(p_lst)
            k_q, n_q = qhist[s]
            if n_p == 0 or n_q == 0:
                return False
            # one-sided Fisher exact: is the new version's failure rate > baseline's?
            _, pval = fisher_exact([[k_p, n_p - k_p], [k_q, n_q - k_q]], alternative="greater")
            return pval <= ALPHA
        raise ValueError(gt_mode)

    configs = [c for c in pools if c != base_cfg]
    truth, flaky_set = {}, {}
    for c in configs:
        truth[c], flaky_set[c] = {}, set()
        for s in scen:
            if not gt_pools[c].get(s):
                continue
            if is_reg(c, s, gt_pools[c][s]):
                truth[c][s] = _mean0(gt_pools[c][s])
                p_draw = _mean0(draw_pools[c].get(s, []))
                if E.FLAKY_LO <= p_draw <= E.FLAKY_HI:
                    flaky_set[c].add(s)
    n_faults = sum(len(v) for v in truth.values())
    n_flaky = sum(len(v) for v in flaky_set.values())
    if n_faults < 3:
        return {"_meta": {"n_faults": n_faults, "n_flaky": n_flaky, "too_few": True}}

    K = len(scen)
    cap = max((sum(len(draw_pools[c].get(s, [])) for s in scen) for c in configs), default=K)
    maxB = min(5 * K, cap)
    step = max(1, K // 6)
    Bgrid = list(range(K, maxB + 1, step)) or [maxB]

    fp  = {m: {B: [] for B in Bgrid} for m in E.METHODS}
    f1d = {m: {B: [] for B in Bgrid} for m in E.METHODS}
    rec = {m: {B: [] for B in Bgrid} for m in E.METHODS}
    # prioritization accumulators (RQ3): APFDc, Top-K recall, Top-K precision
    apf = {m: [] for m in E.METHODS}
    pk  = {m: {kk: [] for kk in E.TOPK_KS} for m in E.METHODS}
    pkp = {m: {kk: [] for kk in E.TOPK_KS} for m in E.METHODS}

    for _ in range(E.NBOOT):
        for c in configs:
            tf = set(truth[c])
            if not tf:
                continue
            nonreg = [s for s in scen if s not in tf]
            Pn = {s: list(E.RNG.permutation(draw_pools[c].get(s) or [0])) for s in scen}
            Pb = {s: list(E.RNG.permutation(base_draw_pool.get(s) or [0])) for s in scen}
            true_p = {s: _mean0(draw_pools[c].get(s, [])) for s in scen}
            true_q = {s: _mean0(base_draw_pool.get(s, [])) for s in scen}
            # baseline HISTORY available to baseline-aware methods: full pool (default) or a
            # random subsample of hist_n runs/scenario (history-depth sweep; GT stays full-pool)
            if hist_n is None:
                qh = qhist
            else:
                qh = {}
                for s in scen:
                    pool = base_draw_pool.get(s, [])
                    k = min(hist_n, len(pool))
                    sub = E.RNG.choice(pool, size=k, replace=False) if k else []
                    qh[s] = (int(sum(sub)), k)
            q_known = {s: (qh[s][0] / qh[s][1] if qh[s][1] else 0.0) for s in scen}
            qn_known = {s: qh[s][1] for s in scen}
            for mth in E.METHODS:
                ni = {s: 0 for s in scen}; mi = {s: 0 for s in scen}
                def dnew(s, ni=ni):
                    if ni[s] >= len(Pn[s]): return None
                    v = Pn[s][ni[s]]; ni[s] += 1; return int(v)
                def dbase(s, mi=mi):
                    if mi[s] >= len(Pb[s]): return None
                    v = Pb[s][mi[s]]; mi[s] += 1; return int(v)
                draw_new = {s: (lambda s=s: dnew(s)) for s in scen}
                draw_base = {s: (lambda s=s: dbase(s)) for s in scen}
                mB = max(Bgrid)
                if mth in E.NAIVE:
                    found = E.simulate_naive(mth, scen, draw_new, base_gt, true_p, mB, gt_set=tf)
                elif mth == "rerun_any":
                    found = E.simulate_rerun(scen, draw_new, mB, rule="any")
                elif mth == "rerun_maj":
                    found = E.simulate_rerun(scen, draw_new, mB, rule="maj")
                elif mth == "pfs":
                    found = E.simulate_pfs(scen, draw_new, mB, gamma=gamma)
                elif mth == "eb_warm":
                    qbar = {s: (qh[s][0] / qh[s][1] if qh[s][1] else 0.0) for s in scen}
                    eb_prior = {s: (0.5 + E.KP * qbar[s], 0.5 + E.KP * (1 - qbar[s])) for s in scen}
                    found = E.simulate_pfs(scen, draw_new, mB, gamma=gamma, prior=eb_prior)
                elif mth == "sprt":
                    found = E.simulate_sprt(scen, draw_new, q_known, mB)
                elif mth == "apt":
                    found = E.simulate_apt(scen, draw_new, q_known, mB)
                elif mth == "twoprop":
                    found = E.simulate_twoprop(scen, draw_new, q_known, qn_known, Bgrid)
                elif mth in E.SATRP_BF:
                    found = E.simulate_satrp_bf(mth, scen, draw_new, draw_base, qh, true_p, true_q, mB)
                else:
                    found = E.simulate_satrp(mth, scen, draw_new, draw_base, qh, true_p, true_q,
                                             mB, gamma=gamma)
                # prioritization over the induced flag order (RQ3)
                if tf:
                    m_tf = len(tf)
                    # prioritized list = FLAGGED scenarios only (same fix as eval_satrp.py 2026-10-05)
                    ranked = sorted(found, key=lambda s: (found[s], s))
                    for kk in E.TOPK_KS:
                        top = ranked[:kk]
                        hits = len(set(top) & tf)
                        pk[mth][kk].append(hits / m_tf)
                        pkp[mth][kk].append((hits / len(top)) if top else float("nan"))
                    det = [sum(1 for f in tf if found.get(f, math.inf) <= B) / m_tf
                           for B in range(1, mB + 1)]
                    apf[mth].append(sum(det) / len(det))
                for B in Bgrid:
                    flagged = {s for s, ft in found.items() if ft <= B}
                    tp = len(flagged & tf)
                    recall = tp / len(tf)
                    prec = tp / len(flagged) if flagged else 0.0
                    f1 = (2 * prec * recall / (prec + recall)) if (prec + recall) > 0 else 0.0
                    rec[mth][B].append(recall)
                    fp[mth][B].append((len(flagged - tf) / len(nonreg)) if nonreg else 0.0)
                    f1d[mth][B].append(f1)

    rps = [round(B / K, 3) for B in Bgrid]
    i2 = min(range(len(Bgrid)), key=lambda i: abs(Bgrid[i] - 2 * K))
    out = {"_meta": {"n_faults": n_faults, "n_flaky": n_flaky, "scen": K, "configs": len(configs)}}
    for mth in E.METHODS:
        f1curve = [float(np.mean(f1d[mth][B])) for B in Bgrid]
        d = dict(
            f1_auc=E._auc(rps, f1curve),
            f1_at_2x=f1curve[i2],
            fp_at_2x=float(np.mean(fp[mth][Bgrid[i2]])),
            recall_at_2x=float(np.mean(rec[mth][Bgrid[i2]])),
            apfdc=float(np.mean(apf[mth])) if apf[mth] else float("nan"),
        )
        for kk in E.TOPK_KS:
            d[f"topk{kk}_rec"] = float(np.mean(pk[mth][kk])) if pk[mth][kk] else float("nan")
            vals = [v for v in pkp[mth][kk] if v == v]
            d[f"topk{kk}_prec"] = float(np.mean(vals)) if vals else float("nan")
        out[mth] = d
    return out


GRID = [0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]
INSTANCES = [
    ("injection", f"{H}/data/injection/**/*.jsonl",        "design"),
    ("openpilot", f"{H}/data/derived/openpilot/runs.jsonl", "design"),
    ("autoware",  f"{H}/data/derived/autoware/runs.jsonl",  "fisher"),
]


def best_over_gamma(pattern, gt_mode):
    """Sweep gamma, return for each method its full metric dict at its own best-F1 gamma."""
    bymethod = {m: [] for m in E.METHODS}
    meta = None
    for g in GRID:
        r = run_altgt(pattern, gt_mode, g)
        if r is None:
            return None, None
        if r.get("_meta", {}).get("too_few"):
            return None, r["_meta"]
        meta = r["_meta"]
        for m in E.METHODS:
            bymethod[m].append((g, r[m]))
    best = {}
    for m in E.METHODS:
        g, d = max(bymethod[m], key=lambda t: t[1]["f1_auc"])
        best[m] = dict(gamma=g, **d)
    return best, meta


if __name__ == "__main__":
    # ALL instances under the SAME decoupled Fisher-exact GT (uniform, fair).
    FISHER_ALL = [(n, p, "fisher") for n, p, _ in INSTANCES]
    print(f"DECOUPLED-GT validation  (Fisher-exact GT on ALL instances; "
          f"DELTA={E.DELTA}, NBOOT={E.NBOOT}, ALPHA={ALPHA})")
    print("Reports RQ2 (F1/FP), RQ3 (APFDc/Top-K), RQ4 ablation ladder, RQ5 history axis (cold/base/warm).\n")
    SHOW = ["strap", "uniform", "rerun_any", "pfs", "eb_warm", "twoprop", "sprt", "apt",
            "satrp_cold", "satrp_base", "satrp_warm", "oracle"]
    for name, pat, mode in FISHER_ALL:
        best, meta = best_over_gamma(pat, mode)
        if best is None:
            print(f"### {name} [{mode}] ###  skipped ({meta})\n"); continue
        strap = best["strap"]
        print(f"### {name}  [GT={mode}] ###  faults={meta['n_faults']} (flaky={meta['n_flaky']}), "
              f"configs={meta['configs']}, scen={meta['scen']}")
        kk = E.TOPK_KS[-1]
        print(f"  {'method':12s} {'F1auc':>7} {'@g':>4} {'FP':>6} {'APFDc':>6} "
              f"{'top'+str(kk)+'rec':>7} {'top'+str(kk)+'prec':>8}")
        for m in SHOW:
            b = best[m]
            print(f"  {m:12s} {b['f1_auc']:>7.3f} {b['gamma']:>4.2f} {b['fp_at_2x']:>6.3f} "
                  f"{b['apfdc']:>6.3f} {b[f'topk{kk}_rec']:>7.3f} {b[f'topk{kk}_prec']:>8.3f}")
        for m in ["satrp_cold", "satrp_base", "satrp_warm"]:
            dF = best[m]["f1_auc"] - strap["f1_auc"]
            pct = 100 * dF / strap["f1_auc"] if strap["f1_auc"] > 0 else float("nan")
            fpr = (strap["fp_at_2x"] / best[m]["fp_at_2x"]) if best[m]["fp_at_2x"] > 0 else float("inf")
            print(f"   -> {m:11s} vs STRAP: F1 {dF:+.3f} ({pct:+.0f}%);  FP {fpr:.1f}x;  "
                  f"APFDc {best[m]['apfdc']-strap['apfdc']:+.3f};  "
                  f"top{kk}prec {best[m][f'topk{kk}_prec']:.2f} vs {strap[f'topk{kk}_prec']:.2f}")
        print()
