"""ratio_binary_search: full-range binary search on R(M) = RPSTargetTTFT / RPSTargetITL.

Finds the smallest M where R(M) >= 1.0 (the TTFT-ITL crossover).
Uses no predictor — searches the entire [m_min, m_max] range.
Expected: 8 binary steps + 1 confirmatory = 9 total calls for crossover scenarios.
For no-crossover (R never reaches 1.0): returns m_max (on plateau, gap≈0).
"""

from __future__ import annotations
from typing import Callable


def _ratio(result: dict) -> float:
    ttft = float(result.get("RPSTargetTTFT", 0))
    itl = float(result.get("RPSTargetITL", 1))
    if itl <= 0:
        return 0.0
    return ttft / itl


def search(target_eval: Callable[[int], dict], m_min: int, m_max: int) -> int:
    lo, hi = m_min + 1, m_max  # skip M=1 (always infeasible)
    best = m_max  # default: if no crossing found, land on plateau

    while lo <= hi:
        mid = (lo + hi) // 2
        r = _ratio(target_eval(mid))
        if r >= 1.0:
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1

    return best
