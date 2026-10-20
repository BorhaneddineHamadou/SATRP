#!/usr/bin/env python3
"""
extra_analysis.py — produces, per instance:
  (A) gamma-sweep operating points (fp, recall, f1, top5prec) per method  -> figures + point estimates
  (B) config-clustered bootstrap CIs on the SA-TRP vs StRAP F1 gain and FP ratio
  (C) held-out operating-point (gamma) selection: calibrate gamma on a validation split
      to a false-alarm budget, report FP + recall on held-out configurations.
Dumps everything to results/extra_analysis_mut_<instance>.json.  Offline; reuses eval_satrp.
Run:  python3 extra_analysis.py
"""
import os, sys, json, math, glob
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import eval_satrp as E

H = os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INSTANCES = [(n, f"{H}/data/derived/{n}/runs.jsonl") for n in
             (sys.argv[1:] or ["mutation_transfuser"])]
from scipy.stats import fisher_exact
ALTGT_ALPHA = 0.05
GRID = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
NB_SWEEP = int(os.environ.get("NB_SWEEP", "80"))
NB_CFG   = int(os.environ.get("NB_CFG", "30"))
NBOOT_CI = int(os.environ.get("NBOOT_CI", "1000"))
FPR_TARGET = 0.10


def build(pattern):
    E.GT_MODE = "sig"; E.GT_CONF = 0.9
    pools = E.load_pools(pattern)
    base = "BASE" if "BASE" in pools else next((c for c in pools if "none" in str(c).lower()), None)
    scen = sorted({s for c in pools for s in pools[c]})
    full = {c: {s: [t for (_, t) in lst] for s, lst in sc.items()} for c, sc in pools.items()}
    base_gt = {s: (float(np.mean(full[base][s])) if s in full[base] else 0.0) for s in scen}
    qhist = {s: (sum(full[base].get(s, [])), len(full[base].get(s, []))) for s in scen}
    base_draw = {s: list(full[base].get(s, [])) for s in scen}
    def isreg(p, s):
        if not p or (np.mean(p) - base_gt.get(s, 0.0)) < E.DELTA: return False
        kp, npp = sum(p), len(p); kq, nq = qhist[s]
        if npp == 0 or nq == 0: return False
        return fisher_exact([[kp, npp-kp], [kq, nq-kq]], alternative="greater")[1] <= ALTGT_ALPHA
    truth = {}
    for c in pools:
        if c == base: continue
        truth[c] = {s: float(np.mean(full[c][s])) for s in scen if full[c].get(s) and isreg(full[c][s], s)}
    configs = [c for c in pools if c != base]
    K = len(scen)
    return dict(pools=pools, full=full, scen=scen, base=base, base_gt=base_gt, qhist=qhist,
                base_draw=base_draw, truth=truth, configs=configs, K=K, B2=2 * K)


def per_config(ix, method, gamma, nboot, rng):
    scen, truth = ix["scen"], ix["truth"]
    base_gt, qhist, base_draw, B2, full = ix["base_gt"], ix["qhist"], ix["base_draw"], ix["B2"], ix["full"]
    recs = {}
    for c in ix["configs"]:
        tf = set(truth[c]); nonreg = [s for s in scen if s not in tf]; full_c = full[c]
        rec_d = 0.0; tp = 0; fp_num = fp_den = 0.0; f1s = []; nflag = ncell = 0
        for _ in range(nboot):
            Pn = {s: list(rng.permutation(full_c.get(s) or [0])) for s in scen}
            Pb = {s: list(rng.permutation(base_draw.get(s) or [0])) for s in scen}
            ni = {s: 0 for s in scen}; mi = {s: 0 for s in scen}
            def dn(s, ni=ni, Pn=Pn):
                if ni[s] >= len(Pn[s]): return None
                v = Pn[s][ni[s]]; ni[s] += 1; return int(v)
            def db(s, mi=mi, Pb=Pb):
                if mi[s] >= len(Pb[s]): return None
                v = Pb[s][mi[s]]; mi[s] += 1; return int(v)
            draw_new = {s: (lambda s=s: dn(s)) for s in scen}
            draw_base = {s: (lambda s=s: db(s)) for s in scen}
            true_p = {s: float(np.mean(full_c.get(s, []) or [0])) for s in scen}
            true_q = {s: float(np.mean(base_draw.get(s, []) or [0])) for s in scen}
            E.RNG = rng
            if method in ("strap", "uniform"):
                found = E.simulate_naive(method, scen, draw_new, base_gt, true_p, B2, gt_set=tf)
            elif method == "eb_warm":
                qb = {s: (qhist[s][0]/qhist[s][1] if qhist[s][1] else 0.0) for s in scen}
                pr = {s: (0.5+E.KP*qb[s], 0.5+E.KP*(1-qb[s])) for s in scen}
                found = E.simulate_pfs(scen, draw_new, B2, gamma=gamma, prior=pr)
            else:
                found = E.simulate_satrp(method, scen, draw_new, draw_base, qhist, true_p, true_q, B2, gamma=gamma)
            flagged = {s for s, ft in found.items() if ft <= B2}
            ncell += len(scen); nflag += len(flagged)
            if tf:
                tpb = len(flagged & tf); rec_d += tpb/len(tf); tp += tpb
                prec = tpb/len(flagged) if flagged else 0.0; r = tpb/len(tf)
                f1s.append(2*prec*r/(prec+r) if prec+r > 0 else 0.0)
            if nonreg:
                fp_num += len(flagged - tf); fp_den += len(nonreg)
        recs[c] = dict(has_pos=bool(tf), npos=len(tf),
                       recall=(rec_d/nboot if tf else None),
                       fp=(fp_num/fp_den if fp_den else None),
                       f1=(float(np.mean(f1s)) if f1s else None),
                       alarm=nflag, cells=ncell)
    return recs


def agg(recs):
    rc = [r for r in recs.values() if r["has_pos"]]
    recall = float(np.mean([r["recall"] for r in rc])) if rc else 0.0
    fpv = [r["fp"] for r in rc if r["fp"] is not None]
    fp = float(np.mean(fpv)) if fpv else 0.0
    f1v = [r["f1"] for r in rc if r["f1"] is not None]
    f1 = float(np.mean(f1v)) if f1v else 0.0
    alarm = sum(r["alarm"] for r in recs.values())/max(1, sum(r["cells"] for r in recs.values()))
    return dict(recall=recall, fp=fp, f1=f1, alarm=alarm)


def main():
    out = {"_meta": dict(NB_SWEEP=NB_SWEEP, NB_CFG=NB_CFG, NBOOT_CI=NBOOT_CI, grid=GRID)}
    for name, pat in INSTANCES:
        print(f"\n===== {name} =====", flush=True)
        ix = build(pat)
        print(f"configs={len(ix['configs'])} positives={sum(len(v) for v in ix['truth'].values())}", flush=True)

        import pandas as pd
        bf = pd.read_csv(f"{H}/results/{name}/frontier_all_fisher_best.csv").set_index("method")
        best = {m: float(bf.loc[m, "at_gamma"]) for m in bf.index}
        best["sprt"] = best["apt"] = 0.55   # level-0 knob for the frequentist tests (their best on TF)
        # (B) config-clustered bootstrap CIs (warm vs strap)
        rng = np.random.default_rng(0)
        rw = per_config(ix, "satrp_warm", best["satrp_warm"], NB_CFG, rng)
        rs = per_config(ix, "strap", best["strap"], NB_CFG, rng)
        E.ALPHA = E.BETA = 0.40; E.APT_C = 0.30   # level-0 knobs (best F1 for sprt/apt on TF depth-24)
        rsprt = per_config(ix, "sprt", best["sprt"], NB_CFG, rng)
        rapt = per_config(ix, "apt", best["apt"], NB_CFG, rng)
        rbase = per_config(ix, "satrp_base", best["satrp_base"], NB_CFG, rng)
        cfgs = [c for c in ix["configs"] if rw[c]["has_pos"]]
        def stat(sample):
            aw = agg({c: rw[c] for c in sample}); a2 = agg({c: rs[c] for c in sample})
            fpr = (a2["fp"]/aw["fp"]) if aw["fp"] > 0 else float("inf")
            return aw["f1"] - a2["f1"], fpr, aw["f1"], a2["f1"], aw["fp"], a2["fp"]
        p = stat(cfgs)
        bs = [stat(list(rng.choice(cfgs, size=len(cfgs), replace=True))) for _ in range(NBOOT_CI)]
        dF1 = sorted(b[0] for b in bs); fx = sorted(b[1] for b in bs if math.isfinite(b[1]))
        lo, hi = lambda a: a[int(.025*len(a))], lambda a: a[int(.975*len(a))]
        ci = dict(n_configs=len(cfgs), f1_warm=p[2], f1_strap=p[3], fp_warm=p[4], fp_strap=p[5],
                  dF1=p[0], dF1_lo=lo(dF1), dF1_hi=hi(dF1),
                  dF1_pct=(100*p[0]/p[3] if p[3] > 0 else None),
                  dF1_pct_lo=(100*lo(dF1)/p[3] if p[3] > 0 else None),
                  dF1_pct_hi=(100*hi(dF1)/p[3] if p[3] > 0 else None),
                  FPx=p[1], FPx_lo=(lo(fx) if fx else None), FPx_hi=(hi(fx) if fx else None))
        for lab, rr in (("vs_sprt", rsprt), ("vs_apt", rapt)):
            def stat2(sample, rr=rr):
                aw = agg({c: rbase[c] for c in sample}); a2 = agg({c: rr[c] for c in sample})
                return aw["f1"] - a2["f1"], (a2["fp"]/aw["fp"]) if aw["fp"] > 0 else float("inf"), aw["f1"], a2["f1"], aw["fp"], a2["fp"]
            p2 = stat2(cfgs); bs2 = [stat2(list(rng.choice(cfgs, size=len(cfgs), replace=True))) for _ in range(NBOOT_CI)]
            d2 = sorted(b[0] for b in bs2)
            ci[lab] = dict(dF1=p2[0], dF1_lo=lo(d2), dF1_hi=hi(d2), f1_base=p2[2], f1_other=p2[3], fp_base=p2[4], fp_other=p2[5])
            print(f"  CI base {lab}: dF1={p2[0]:+.3f}[{lo(d2):+.3f},{hi(d2):+.3f}] f1 {p2[2]:.3f} vs {p2[3]:.3f} fp {p2[4]:.3f} vs {p2[5]:.3f}", flush=True)
        out.setdefault("ci", {})[name] = ci
        print(f"  CI dF1={ci['dF1']:+.3f}[{ci['dF1_lo']:+.3f},{ci['dF1_hi']:+.3f}] "
              f"({ci['dF1_pct']:+.0f}%) FP {ci['FPx']:.1f}x[{ci['FPx_lo']:.1f},{ci['FPx_hi']:.1f}] "
              f"n={ci['n_configs']}", flush=True)

        # (C) held-out operating-point selection
        pc = {g: per_config(ix, "satrp_warm", g, NB_CFG, np.random.default_rng(7)) for g in GRID}
        rng2 = np.random.default_rng(11); R = 30
        tfp, trec, tg, gap = [], [], [], []
        for _ in range(R):
            perm = list(rng2.permutation(cfgs)); h = max(1, len(perm)//2)
            val, tst = set(perm[:h]), set(perm[h:]) or set(perm[:h])
            chosen = next((g for g in GRID if agg({c: pc[g][c] for c in val})["fp"] <= FPR_TARGET), GRID[-1])
            a = agg({c: pc[chosen][c] for c in tst})
            orec = max([agg({c: pc[g][c] for c in tst})["recall"]
                        for g in GRID if agg({c: pc[g][c] for c in tst})["fp"] <= FPR_TARGET] or [0.0])
            tfp.append(a["fp"]); trec.append(a["recall"]); tg.append(chosen); gap.append(orec - a["recall"])
        sel = dict(target=FPR_TARGET, R=R, test_fp=float(np.mean(tfp)), test_fp_sd=float(np.std(tfp)),
                   test_recall=float(np.mean(trec)), test_recall_sd=float(np.std(trec)),
                   gamma_mode=float(np.median(tg)), recall_gap=float(np.mean(gap)))
        out.setdefault("opselect", {})[name] = sel
        print(f"  OPSELECT gamma~{sel['gamma_mode']:.2f} testFP={sel['test_fp']:.3f}(target {FPR_TARGET}) "
              f"testRecall={sel['test_recall']:.3f} gap={sel['recall_gap']:.3f}", flush=True)

    os.makedirs(f"{H}/results", exist_ok=True)
    json.dump(out, open(f"{H}/results/extra_analysis_mut_{'_'.join(n for n,_ in INSTANCES)}.json", "w"), indent=1)
    print("\nWROTE results/extra_analysis_mut_*.json")


if __name__ == "__main__":
    main()
