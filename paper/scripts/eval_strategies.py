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
