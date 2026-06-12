"""formula_guided_ablate_anchor: h-robustness ablation A.

Identical to the benchmark-robust formula_guided (h-main) EXCEPT the f* seed
reverts to the iter-4 cell-aware U-seed (if M_TPF < M_ITL seed=m_max, else
seed=min(max(M_ITL,M_TPF),m_max)); keeps the infeasibility->m_min return.

Isolates the high-anchor's contribution: expect bench-023 gap_f -> 0.22.
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

    # Revert to iter-4 cell-aware seed (not high-anchor)
    ttft_only_cell = M_TPF < M_ITL
    if ttft_only_cell:
        seed = m_max
    else:
        seed = min(max(M_ITL, M_TPF), m_max)  # U = constraint upper endpoint

    result = target_eval(seed)
    fstar = result["throughput"]
    if fstar <= 0.0 and seed < m_max:
        seed = m_max
        result = target_eval(seed)
        fstar = result["throughput"]
    if fstar <= 0.0:
        return m_min  # infeasibility fix retained

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
