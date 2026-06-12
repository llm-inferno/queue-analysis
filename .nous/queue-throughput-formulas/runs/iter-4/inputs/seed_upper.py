"""seed_upper: predict-and-confirm at the iter-2 bracket UPPER endpoint.

Per-cell upper endpoint U (computed live from params via formulas.py):
  unbounded         -> M_MAX                       (no constraint binds)
  ttft-only         -> M_TPF                       (M_TPF < M_ITL)
  itl-or-crossover  -> min(M_TPF, M_MAX)           (M_ITL <= M_TPF)

where M_ITL = largest B with itl(B) <= targetITL, M_TPF = largest B with
ttft_prefill(B) <= targetTTFT. Returns U directly: the harness adds one
confirmatory eval, so this costs exactly 1 oracle call per scenario.

Hypothesis (iter-3 h-main): U sits on the f-plateau (M* >= M_ITL by the RP-2
occupancy gap), so gap_throughput_rel(U) ~ 0 across the dev set.
"""

from __future__ import annotations
from typing import Callable

from nous.harness import formulas as F

M_MIN, M_MAX = 1, 256


def _largest_feasible(metric, params: dict, target: float):
    feas = [B for B in range(M_MIN, M_MAX + 1) if metric(B, params) <= target]
    return max(feas) if feas else None


def upper_endpoint(params: dict) -> int:
    itl_binds = F.itl(M_MAX, params) > params["targetITL"]
    ttft_pf_binds = F.ttft_prefill(M_MAX, params) > params["targetTTFT"]
    M_ITL = _largest_feasible(F.itl, params, params["targetITL"]) or M_MIN
    M_TPF = _largest_feasible(F.ttft_prefill, params, params["targetTTFT"]) or M_MIN
    if (not itl_binds) and (not ttft_pf_binds):
        return M_MAX
    if M_TPF < M_ITL:
        return M_TPF
    return min(M_TPF, M_MAX)


def search(target_eval: Callable[[int], dict], params: dict, m_min: int, m_max: int) -> int:
    return max(m_min, min(m_max, upper_endpoint(params)))
