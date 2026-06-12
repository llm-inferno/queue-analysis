"""Reference strategy: brute-force scan. Used only for harness smoke tests.

Real candidate algorithms live alongside this file once the campaign starts
producing them. Every strategy module exposes a single `search` function.
"""

from __future__ import annotations
from typing import Callable


def search(target_eval: Callable[[int], dict], params: dict, m_min: int, m_max: int) -> int:
    """Return the M in [m_min, m_max] with the highest throughput."""
    best_m = m_min
    best_t = -1.0
    for m in range(m_min, m_max + 1):
        result = target_eval(m)
        t = float(result["throughput"])
        if t > best_t:
            best_t = t
            best_m = m
    return best_m
