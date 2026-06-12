"""Offline replay of the committed onset-search strategies against the truth
caches, for the paper's Experiments section. No Go server: the truth cache is
the analytic oracle tabulated at every M in [1, 256], so a cache lookup IS the
oracle value. Deterministic strategies => exact reproduction of M_chosen/calls.

Outputs paper/data/eval_results.json (per-scenario records + aggregates).
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))  # so `nous` (pure-stdlib formulas/strategies) imports

DATA_DIR = REPO / "paper" / "data"
EPS = 0.02
M_MIN, M_MAX = 1, 256
PARAM_KEYS = ("alpha", "beta", "gamma", "AvgInputTokens", "AvgOutputTokens",
              "targetITL", "targetTTFT", "maxQueueSize")


def cache_oracle(f_curve: list[dict]):
    """Return (target_eval, stats). Mirrors nous/harness/oracle.py: an
    infeasible reading (throughput <= 0) is uncounted; every probe is recorded."""
    f = {pt["m"]: pt["throughput"] for pt in f_curve}
    stats = {"calls": 0, "probes": []}

    def target_eval(m: int) -> dict:
        stats["probes"].append(m)
        thr = f.get(m, 0.0)
        if thr > 0.0:
            stats["calls"] += 1
        return {"throughput": thr}

    return target_eval, stats


def epsilon_onset(f_curve: list[dict], eps: float = EPS):
    """Smallest m with f(m) >= (1-eps)*peak; None if the scenario is infeasible."""
    f = {pt["m"]: pt["throughput"] for pt in f_curve}
    peak = max(f.values())
    if peak <= 0.0:
        return None
    thresh = (1.0 - eps) * peak
    for m in sorted(f):
        if f[m] >= thresh:
            return m
    return max(f)


def replay(search, params: dict, cache: dict, m_min: int = M_MIN, m_max: int = M_MAX) -> dict:
    """Run one strategy against one cached scenario; return a scored record.

    Adds one confirmatory oracle(M_chosen) call after the strategy returns,
    matching nous/harness/run.py (so `calls` includes that +1)."""
    f_curve = cache["f_curve"]
    f = {pt["m"]: pt["throughput"] for pt in f_curve}
    M_truth = int(cache["M_truth"])
    f_truth = float(cache["throughput_truth"])
    onset = epsilon_onset(f_curve)
    onset_eff = onset if onset is not None else M_truth

    ev, stats = cache_oracle(f_curve)
    m_chosen = int(search(ev, params, m_min, m_max))
    if not (m_min <= m_chosen <= m_max):
        raise ValueError(f"strategy returned M={m_chosen} outside [{m_min}, {m_max}]")
    thr_chosen = ev(m_chosen)["throughput"]  # confirmatory (counted if feasible)

    gap_f = max((f_truth - thr_chosen) / f_truth, 0.0) if f_truth > 0 else 0.0
    return {
        "M_chosen": m_chosen,
        "calls": stats["calls"],
        "probes": list(stats["probes"]),
        "throughput_chosen": thr_chosen,
        "M_onset": onset_eff,
        "M_truth": M_truth,
        "throughput_truth": f_truth,
        "feasible": f_truth > 0,
        "gap_onset": abs(m_chosen - onset_eff),
        "gap_argmax": abs(m_chosen - M_truth),
        "gap_f": gap_f,
    }
