"""adaptive_early_exit: binary search with early no-crossover detection.

Identical to ratio_binary_search except: probes M=m_max first. If R<1.0,
returns m_max immediately (no crossover — on plateau).

For crossover scenarios: 1 (early check) + 8 (binary) = 9 strategy calls.
For no-crossover: 1 strategy call.
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
    r_top = _ratio(target_eval(m_max))
    if r_top < 1.0:
        return m_max

    lo, hi = m_min + 1, m_max
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
