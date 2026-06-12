"""formula_guided: closed-form guided downward onset search (benchmark-robust v3).

Probes m_max for f*, then binary-searches downward for the smallest M
with f(M) >= (1-EPS/2)*f* — the plateau onset M*.

Algorithm:
1. Compute M_ITL (largest B with itl(B)<=targetITL) and M_TPF (largest B with
   ttft_prefill(B)<=targetTTFT) via the closed-form formulas.
2. Always anchor f* at m_max (robust to U underestimating the peak, RP-2).
3. On fully-infeasible scenarios (m_max returns throughput<=0), return m_min
   to match the truth convention M_truth=m_min.
4. threshold = (1-EPS/2)*f* so the harness confirmatory call stays < EPS=0.02.
5. Lower bracket lo = max(m_min, min(M_ITL, M_TPF)).
6. Upper bracket hi = min(seed, max(3*max(M_ITL,M_TPF), lo+1), m_max).
7. Binary search [lo, hi]; cap at MAX_ITERS=6 so worst-case total calls
   (seed + search + harness-confirmatory) <= 8.
"""

from __future__ import annotations
from typing import Callable

from nous.harness import formulas as F

EPS = 0.02
MAX_ITERS = 6  # seed(1) + MAX_ITERS(6) + harness-confirmatory(1) = 8


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

    # Binary search downward: find smallest M in [lo, hi] with f(M) >= threshold
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
