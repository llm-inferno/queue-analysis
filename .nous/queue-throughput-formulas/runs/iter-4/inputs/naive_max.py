"""naive_max: return M_MAX unconditionally (no formula, no search).

The plateau-flatness control. Under nc=1 the saturation throughput S(B) is
concave-increasing and f(M) never decreases past its peak, so M_MAX sits on the
f-plateau. Costs exactly 1 oracle call (the harness confirmatory eval).

Hypothesis (iter-3 h-control-negative): on the dev set (nc=1) this matches
seed_upper's gap_throughput_rel to within float noise -- the throughput axis
cannot distinguish a precise formula seed from constant M_MAX, because the
plateau extends all the way to M_MAX.
"""

from __future__ import annotations
from typing import Callable


def search(target_eval: Callable[[int], dict], params: dict, m_min: int, m_max: int) -> int:
    return m_max
