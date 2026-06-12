"""formula_guided_v3: high-anchor onset search + infeasibility detection.

DESIGN PROBE for iter-5 (not the committed strategy). Extends v2:
  - v2 fix: ALWAYS anchor f* at m_max (robust to U underestimating the peak;
    resolves bench-023 gap_f=0.22 -> 0.004).
  - v3 fix: when the m_max anchor is itself infeasible (throughput<=0, i.e.
    every /target returns 400), the scenario is fully infeasible and the truth
    convention sets M_truth=m_min. Return m_min (gap_M=0) instead of m_max
    (gap_M=255).
"""
from __future__ import annotations
from typing import Callable

from nous.harness import formulas as F

EPS = 0.02
MAX_ITERS = 6


def _largest_feasible(metric, params: dict, target: float) -> int:
    feas = [B for B in range(1, 257) if metric(B, params) <= target]
    return max(feas) if feas else 1


def search(target_eval: Callable[[int], dict], params: dict, m_min: int, m_max: int) -> int:
    M_ITL = _largest_feasible(F.itl, params, params["targetITL"])
    M_TPF = _largest_feasible(F.ttft_prefill, params, params["targetTTFT"])

    seed = m_max
    fstar = target_eval(seed)["throughput"]
    if fstar <= 0.0:
        return m_min  # fully infeasible -> truth convention M_truth = m_min

    threshold = (1.0 - EPS / 2.0) * fstar

    lo = max(m_min, min(M_ITL, M_TPF))
    U = max(M_ITL, M_TPF)
    hi = min(seed, max(3 * U, lo + 1), m_max)
    hi = max(lo, hi)

    iters = 0
    while lo < hi and iters < MAX_ITERS:
        mid = (lo + hi) // 2
        v = target_eval(mid)["throughput"]
        if v >= threshold:
            hi = mid
        else:
            lo = mid + 1
        iters += 1
    return max(m_min, min(m_max, hi))
