"""formula_guided_v2: high-anchor onset search (benchmark-robust).

iter-4 formula_guided seeds f* at the constraint upper endpoint U=max(M_ITL,
M_TPF) for non-ttft cells. On the benchmark this UNDERESTIMATES the peak
wherever the occupancy gap (RP-2) lets realized throughput climb well past the
per-iteration binding B (e.g. bench-023: U=9, argmax=57) -> threshold too low ->
the descent collapses below the onset -> gap_f violation (0.22 on bench-023).

Fix: ALWAYS anchor f* at m_max (reliable peak proxy under monotone-to-plateau),
regardless of which constraint binds. Keep the closed-form M_ITL/M_TPF only for
the DESCENT BRACKET (lo, hi), not for the f* anchor. Same call budget (1 seed +
<=6 search + 1 harness-confirmatory = 8).
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

    # ALWAYS anchor f* high (m_max) — robust to U underestimating the peak.
    seed = m_max
    fstar = target_eval(seed)["throughput"]
    if fstar <= 0.0:
        return m_max  # fully infeasible

    threshold = (1.0 - EPS / 2.0) * fstar

    lo = max(m_min, min(M_ITL, M_TPF))
    # Upper bracket: occupancy-gap bound 3*max(M_ITL,M_TPF) keeps the bracket
    # above the onset even when one constraint is very tight (bench-023:
    # M_ITL=7 but onset=13, so 3*M_ITL=21 still covers it).
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
