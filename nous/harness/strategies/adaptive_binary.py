"""adaptive_binary: binary search with smart first probe and no-crossover exit.

Same structure as adaptive_interpolation but ALWAYS uses midpoint (no
interpolation). Tests whether interpolation is load-bearing for call
reduction.

Expected calls: no-crossover = 2. Crossover = 7-8 strategy calls.
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
    mid_point = (m_min + 1 + m_max) // 2

    r_mid = _ratio(target_eval(mid_point))
    if r_mid >= 1.0:
        lo, hi = m_min + 1, mid_point - 1
        best = mid_point
    else:
        r_top = _ratio(target_eval(m_max))
        if r_top < 1.0:
            return m_max
        lo, hi = mid_point + 1, m_max - 1
        best = m_max

    while lo <= hi:
        mid = (lo + hi) // 2
        r = _ratio(target_eval(mid))
        if r >= 1.0:
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1

    return best
