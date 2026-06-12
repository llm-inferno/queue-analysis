# nous/harness/tests/test_formula_guided.py
"""Regression tests pinning the high-anchor (v3) onset search.

The stale iter-4 strategy seeded f* at the constraint endpoint U for the
itl-or-crossover cell and failed bench-023 (U=9 << peak@57), and returned
m_max on fully-infeasible scenarios. These tests fail on that version and
pass on v3 (universal m_max anchor; infeasible -> m_min).
"""
import json
from pathlib import Path

from nous.harness.strategies.formula_guided import search

REPO = Path(__file__).resolve().parents[3]


def _cache_eval(name: str):
    sub = "bench/" if name.startswith("bench-") else ""
    prefix = "" if name.startswith("bench-") else "truth-"
    cache = json.loads((REPO / "nous" / "cache" / f"{sub}{prefix}{name}.json").read_text())
    f = {pt["m"]: pt["throughput"] for pt in cache["f_curve"]}
    return (lambda m: {"throughput": f.get(m, 0.0)}), f


def _params(name: str) -> dict:
    fname = "scenarios_benchmark.json" if name.startswith("bench-") else "scenarios.json"
    scns = json.loads((REPO / "nous" / fname).read_text())["scenarios"]
    s = next(x for x in scns if x["name"] == name)
    keys = ("alpha", "beta", "gamma", "AvgInputTokens", "AvgOutputTokens",
            "targetITL", "targetTTFT", "maxQueueSize")
    return {k: s[k] for k in keys}


def test_bench023_high_anchor_within_epsilon():
    """bench-023 (itl-or-crossover, U=9 undershoots peak@57): the m_max anchor
    must land within EPS=0.02 of the peak. The stale U-seed gives gap_f=0.22."""
    ev, f = _cache_eval("bench-023")
    peak = max(f.values())
    m = search(ev, _params("bench-023"), 1, 256)
    gap_f = (peak - f[m]) / peak
    assert gap_f <= 0.02, f"bench-023 gap_f={gap_f:.4f} exceeds EPS (chose M={m})"


def test_fully_infeasible_returns_m_min():
    """bench-005 is infeasible everywhere (all-zero f); must return m_min=1."""
    ev, _ = _cache_eval("bench-005")
    m = search(ev, _params("bench-005"), 1, 256)
    assert m == 1
