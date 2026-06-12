"""ratio_binary_search: full-range binary search on R(M) = RPSTargetTTFT / RPSTargetITL.

Finds the smallest M where R(M) >= 1.0 (the TTFT-ITL crossover).
Uses no predictor — searches the entire [m_min, m_max] range.
Strategy calls: 8 binary steps (the harness adds 1 confirmatory).
For no-crossover (R never reaches 1.0): returns m_max (on plateau, gap≈0).
"""

from __future__ import annotations
from typing import Callable

from ._common import ratio


def search(target_eval: Callable[[int], dict], params: dict, m_min: int, m_max: int) -> int:
    lo, hi = m_min + 1, m_max  # skip M=1 (always infeasible)
    best = m_max  # default: if no crossing found, land on plateau

    while lo <= hi:
        mid = (lo + hi) // 2
        r = ratio(target_eval(mid))
        if r >= 1.0:
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1

    return best
