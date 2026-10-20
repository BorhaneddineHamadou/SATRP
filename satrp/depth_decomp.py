"""Why did every method's F1 drop at depth 24?  Decompose GT-depth vs draw-pool-depth.
run_idx r = (seed - GS) % 1000; even seeds == even r (GS, 1000 even)."""
import os, sys, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import eval_satrp as E, eval_altgt as A
GS = int(os.environ.get("DD_GS", "20260806"))
PAT = os.environ.get("DD_PAT", os.path.join(os.environ.get("SATRP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "derived", "mutation_transfuser", "runs.jsonl"))
E.NBOOT = int(os.environ.get("NB", "100"))
E.METHODS = ["strap", "uniform", "sprt", "apt", "satrp_base", "satrp_warm", "oracle"]
_orig_load = E.load_pools
_orig_split = E.split_gt_draw
FULL = _orig_load(PAT)
def r_of(seed): 
    r = (seed - GS) % 1000; assert 0 <= r < 40, seed; return r
# sanity on run-index recovery
rs = collections.Counter(r_of(sd) for c in FULL for s in FULL[c] for sd, _ in FULL[c][s] if c != "BASE")
print("mutant run_idx histogram:", sorted(rs.items())[:3], "...", sorted(rs.items())[-3:], "n_idx", len(rs), flush=True)

GT_DEPTH = DRAW_DEPTH = 24
def filt(pools, depth, mutants_only=True):
    out = {}
    for c, sc in pools.items():
        out[c] = {}
        for s, lst in sc.items():
            out[c][s] = [(sd, t) for sd, t in lst if (c == "BASE" and mutants_only) or r_of(sd) < depth]
    return out
def my_load(pattern=None):
    # full-pool protocol: the whole pool is both GT and draw source -> depth must be a single number
    return filt(FULL, max(GT_DEPTH, DRAW_DEPTH))
def my_split(pools):
    gt, draw = {}, {}
    for c, sc in pools.items():
        gt[c], draw[c] = {}, {}
        for s, lst in sc.items():
            gt[c][s]   = [t for sd, t in lst if sd % 2 == 0 and (c == "BASE" or r_of(sd) < GT_DEPTH)]
            draw[c][s] = [t for sd, t in lst if sd % 2 == 1 and (c == "BASE" or r_of(sd) < DRAW_DEPTH)]
    return gt, draw
E.load_pools = my_load; E.split_gt_draw = my_split
A.E = E

# exhaustion counters: wrap draw_new so None returns are counted per method
EXH = collections.Counter(); CALLS = collections.Counter()
def wrap_draws(name, dn):
    def mk(s, f):
        def g():
            v = f(); CALLS[name] += 1
            if v is None: EXH[name] += 1
            return v
        return g
    return {s: mk(s, f) for s, f in dn.items()}
for nm in ["simulate_sprt", "simulate_apt"]:
    orig = getattr(E, nm)
    def mkw(orig, nm):
        def w(scen, draw_new, q_known, budget): return orig(scen, wrap_draws(nm, draw_new), q_known, budget)
        return w
    setattr(E, nm, mkw(orig, nm))
_os = E.simulate_satrp
def _ws(variant, scen, draw_new, draw_base, qhist, true_p, true_q, budget, gamma=None):
    return _os(variant, scen, wrap_draws("satrp_" + variant, draw_new), draw_base, qhist, true_p, true_q, budget, gamma=gamma)
E.simulate_satrp = _ws

LEVELS = {1: (0.60, 0.30, 0.50), 5: (0.80, 0.05, 1.30)}
def run(label, sep, gt_d, draw_d, lvl):
    global GT_DEPTH, DRAW_DEPTH
    GT_DEPTH, DRAW_DEPTH = gt_d, draw_d
    g, al, ac = LEVELS[lvl]; E.ALPHA = E.BETA = al; E.APT_C = ac
    EXH.clear(); CALLS.clear()
    r = A.run_altgt(PAT, "fisher", g, hist_n=None, separate=sep)
    m = r["_meta"]
    print(f"\n=== {label} sep={sep} GTdepth={gt_d} DRAWdepth={draw_d} level={lvl} (g={g},a={al},c={ac}) faults={m['n_faults']} flaky={m['n_flaky']}")
    print(f"{'method':12s} {'F1auc':>6} {'F1@2x':>6} {'FP@2x':>6} {'rec@2x':>6} {'exhausted/draw-calls':>22}")
    for k in E.METHODS:
        d = r[k]; ex = f"{EXH.get(k,0)}/{CALLS.get(k,0)}" if k in CALLS else "-"
        print(f"{k:12s} {d['f1_auc']:6.3f} {d['f1_at_2x']:6.3f} {d['fp_at_2x']:6.3f} {d['recall_at_2x']:6.3f} {ex:>22}")
    sys.stdout.flush()

# GT composition under the separated protocol: which cells are faults at depth 12 vs 24?
def gt_cells(depth):
    global GT_DEPTH, DRAW_DEPTH; GT_DEPTH = DRAW_DEPTH = depth
    gt, _ = my_split(my_load())
    from scipy.stats import fisher_exact
    base = {s: gt["BASE"][s] for s in gt["BASE"]}
    cells = {}
    for c in gt:
        if c == "BASE": continue
        for s, lst in gt[c].items():
            if not lst: continue
            p, q = np.mean(lst), np.mean(base[s]); eff = p - q
            if eff < E.DELTA: continue
            _, pv = fisher_exact([[sum(lst), len(lst) - sum(lst)], [sum(base[s]), len(base[s]) - sum(base[s])]], alternative="greater")
            if pv <= A.ALPHA: cells[(c, s)] = eff
    return cells
g12, g24 = gt_cells(12), gt_cells(24)
both = set(g12) & set(g24)
print(f"\nSEP GT cells: depth12={len(g12)} depth24={len(g24)} overlap={len(both)} only12={len(set(g12)-both)} only24={len(set(g24)-both)}")
print(f"  mean effect (p-q, on GT seeds): only-in-12 {np.mean([g12[k] for k in set(g12)-both]) if set(g12)-both else float('nan'):.3f} | both(d12 est) {np.mean([g12[k] for k in both]):.3f} | only-in-24 {np.mean([g24[k] for k in set(g24)-both]) if set(g24)-both else float('nan'):.3f}")
# effect of the only-in-12 cells re-estimated on 24 GT draws
GT_DEPTH = DRAW_DEPTH = 24
gt24, _ = my_split(my_load()); base24 = gt24["BASE"]
re12 = [np.mean(gt24[c][s]) - np.mean(base24[s]) for (c, s) in set(g12) - both]
print(f"  only-in-12 cells re-estimated at depth 24: mean effect {np.mean(re12) if re12 else float('nan'):.3f} (winner's curse if << their depth-12 estimate)")

for lvl in (1, 5):
    run("A reproduce depth12", True, 12, 12, lvl)
    run("B reproduce depth24", True, 24, 24, lvl)
    run("C GT24 / draw12", True, 24, 12, lvl)
    run("D GT12 / draw24", True, 12, 24, lvl)
for lvl in (1, 5):
    run("E full-pool depth12", False, 12, 12, lvl)
    run("F full-pool depth24", False, 24, 24, lvl)
print("\nDONE")
