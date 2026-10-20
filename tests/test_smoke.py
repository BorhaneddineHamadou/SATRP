"""Smoke tests (seconds): the shipped instances load, the label rule and the evaluation
harness run end to end on a tiny bootstrap, and the validity filter behaves as documented.
    python3 -m pytest tests -q        (or: python3 tests/test_smoke.py)"""
import os, sys, json, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "satrp"))
os.environ.setdefault("SATRP_ROOT", ROOT)
os.environ.setdefault("INJECT_GLOB", os.path.join(ROOT, "data", "derived", "mutation_transfuser", "runs.jsonl"))
os.environ.setdefault("INJECT_OUT", os.path.join(ROOT, "results", "_smoke"))
os.environ["SATRP_NBOOT"] = "3"


def test_instances_are_balanced():
    for inst, cells, draws, base in (("mutation_openpilot", 840, 24, 40), ("mutation_transfuser", 840, 24, 40)):
        recs = [json.loads(l) for l in open(f"{ROOT}/data/derived/{inst}/runs.jsonl")]
        mut = collections.Counter((r["commit"], r["scenario"]) for r in recs if not r["is_baseline"])
        bas = collections.Counter(r["scenario"] for r in recs if r["is_baseline"])
        assert len(mut) == cells and set(mut.values()) == {draws}, inst
        assert len(bas) == 30 and set(bas.values()) == {base}, inst


def test_validity_filter():
    import adapter as AD
    assert AD._mut_valid_trig("openpilot", {"outcome": "no_engage"}) == (False, 0)
    assert AD._mut_valid_trig("openpilot", {"outcome": "bridge_start_timeout"}) == (False, 0)
    assert AD._mut_valid_trig("openpilot", {"outcome": "out_of_lane", "engaged": True}) == (True, 1)
    assert AD._mut_valid_trig("openpilot", {"outcome": "completed", "engaged": True, "contact": False}) == (True, 0)
    assert AD._mut_valid_trig("transfuser", {"outcome": "completed", "contact": True}) == (True, 1)
    assert AD._mut_valid_trig("transfuser", {"outcome": "completed", "trace_exists": False}) == (False, 0)


def test_fisher_ground_truth_and_harness():
    import eval_altgt as A
    r = A.run_altgt(os.environ["INJECT_GLOB"], "fisher", 0.6, hist_n=None, separate=False)
    m = r["_meta"]
    assert m["n_faults"] == 55 and m["n_flaky"] == 14, m          # Table 1, TransFuser column
    for k in ("strap", "uniform", "sprt", "apt", "satrp_base", "satrp_warm", "oracle"):
        assert k in r and 0.0 <= r[k]["f1_auc"] <= 1.0, k
    assert r["oracle"]["f1_auc"] == 1.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
