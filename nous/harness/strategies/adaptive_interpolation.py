"""adaptive_interpolation: interpolation search with smart no-crossover exit.

Key idea: probe at m_max/2 first (not m_max). If R>=1.0, crossover is in
the lower half and we saved the m_max probe. If R<1.0, probe m_max next:
if R<1.0 there too, no crossover (2 calls). If R>=1.0, bracket is
[m_max/2, m_max] and we continue with interpolation.

Once a bracket [lo, hi] with measured R(lo)<1.0 and R(hi)>=1.0 is
established, switches from binary to interpolation for faster convergence.

Strategy calls: 2 (no-crossover) or 5-6 (crossover); the harness adds 1
confirmatory.
"""

from __future__ import annotations
from typing import Callable

from ._common import ratio

# Minimum |r_hi - r_lo| spread for interpolation to be numerically stable;
# below this we fall back to bisection to avoid amplifying float noise.
MIN_RATIO_SPREAD = 0.001


def search(target_eval: Callable[[int], dict], m_min: int, m_max: int) -> int:
    mid_point = (m_min + 1 + m_max) // 2

    r_mid = ratio(target_eval(mid_point))
    if r_mid >= 1.0:
        lo, hi = m_min + 1, mid_point - 1
        r_lo = None
        r_hi = r_mid
        best = mid_point
    else:
        r_top = ratio(target_eval(m_max))
        if r_top < 1.0:
            return m_max
        lo, hi = mid_point + 1, m_max - 1
        r_lo = r_mid
        r_hi = r_top
        best = m_max

    while lo <= hi:
        width = hi - lo

        if r_lo is not None and width >= 1:
            denom = r_hi - r_lo
            if denom > MIN_RATIO_SPREAD:
                frac = (1.0 - r_lo) / denom
                frac = max(0.0, min(1.0, frac))
                mid = lo + int(round(width * frac))
                mid = max(lo, min(hi, mid))
            else:
                mid = (lo + hi) // 2
        else:
            mid = (lo + hi) // 2

        r = ratio(target_eval(mid))
        if r >= 1.0:
            best = mid
            hi = mid - 1
            r_hi = r
        else:
            lo = mid + 1
            r_lo = r

    return best
