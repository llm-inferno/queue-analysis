"""formula_guided_ablate_infeasible: h-robustness ablation B.

Identical to the benchmark-robust formula_guided (h-main) EXCEPT on an
infeasible m_max seed it returns m_max (not m_min); keeps the high-anchor.

Isolates the infeasibility-detection component: expect worst/mean gap_M
to re-inflate to ~255/56.5 via the 5 fully-infeasible scenarios.
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
        return m_max  # revert: return m_max instead of m_min on infeasible

    threshold = (1.0 - EPS / 2.0) * fstar

    lo = max(m_min, min(M_ITL, M_TPF))
    U = max(M_ITL, M_TPF)
    hi = min(seed, max(3 * U, lo + 1), m_max)
    hi = max(lo, hi)

    iters = 0
    while lo < hi and iters < MAX_ITERS:
        mid = (lo + hi) // 2
        v = target_eval(mid)
        if v["throughput"] >= threshold:
            hi = mid
        else:
            lo = mid + 1
        iters += 1

    return max(m_min, min(m_max, hi))
