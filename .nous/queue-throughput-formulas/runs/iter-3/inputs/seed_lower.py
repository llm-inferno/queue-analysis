"""seed_lower: predict-and-confirm at the iter-2 bracket LOWER endpoint (M_ITL).

This is the iter-2 per-cell POINT estimate (m_hat) for the itl-or-crossover
cell. It is the ablation of seed_upper: same predict-and-confirm skeleton, but
seed at the LOWER bracket endpoint instead of the upper one.

Per-cell lower endpoint L:
  unbounded         -> M_MAX        (degenerate: bracket is [M_MAX, M_MAX])
  ttft-only         -> M_TPF        (ttft-only bracket point estimate)
  itl-or-crossover  -> M_ITL        (LOWER bound on plateau onset M*)

Hypothesis (iter-3 h-ablation): seeding at L instead of U re-introduces large
gap_throughput_rel on ITL-binding scenarios, because M_ITL is a strict LOWER
bound on the plateau onset (RP-2) -- L lands on the rising part of f(M).
"""

from __future__ import annotations
from typing import Callable

from nous.harness import formulas as F

M_MIN, M_MAX = 1, 256


def _largest_feasible(metric, params: dict, target: float):
    feas = [B for B in range(M_MIN, M_MAX + 1) if metric(B, params) <= target]
    return max(feas) if feas else None


def lower_endpoint(params: dict) -> int:
    itl_binds = F.itl(M_MAX, params) > params["targetITL"]
    ttft_pf_binds = F.ttft_prefill(M_MAX, params) > params["targetTTFT"]
    M_ITL = _largest_feasible(F.itl, params, params["targetITL"]) or M_MIN
    M_TPF = _largest_feasible(F.ttft_prefill, params, params["targetTTFT"]) or M_MIN
    if (not itl_binds) and (not ttft_pf_binds):
        return M_MAX
    if M_TPF < M_ITL:
        return M_TPF
    return M_ITL


def search(target_eval: Callable[[int], dict], params: dict, m_min: int, m_max: int) -> int:
    return max(m_min, min(m_max, lower_endpoint(params)))
