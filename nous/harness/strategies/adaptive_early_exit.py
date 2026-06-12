"""adaptive_early_exit: binary search with early no-crossover detection.

Identical to ratio_binary_search except: probes M=m_max first. If R<1.0,
returns m_max immediately (no crossover — on plateau).

Strategy calls: 1 (no-crossover) or 1 (early check) + 8 (binary) = 9
(crossover); the harness adds 1 confirmatory.
"""

from __future__ import annotations
from typing import Callable

from ._common import ratio


def search(target_eval: Callable[[int], dict], params: dict, m_min: int, m_max: int) -> int:
    r_top = ratio(target_eval(m_max))
    if r_top < 1.0:
        return m_max

    lo, hi = m_min + 1, m_max
    best = m_max

    while lo <= hi:
        mid = (lo + hi) // 2
        r = ratio(target_eval(mid))
        if r >= 1.0:
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1

    return best
