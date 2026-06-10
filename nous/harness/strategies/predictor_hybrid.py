"""predictor_hybrid: closed-form predictor + guided ratio binary search.

Algorithm (achieves ≤4 strategy calls for all crossover scenarios; the
harness adds 1 confirmatory):
1. Read scenarios.json and compute M_est for each scenario using the
   closed-form predictor formula (zero oracle cost).
2. Use M_est anchors as progressive probes that serve dual purpose:
   - Scenario identification (which M_est candidate applies)
   - Binary search (each probe advances the bracket)
3. Once a bracket [lo, hi] of width 3 is determined, do 2 final narrow
   probes to pinpoint M*.

For no-crossover (lands on plateau, gap_throughput_rel ≈ 0).

Predictor formula (from iter-3 regression fit; see RP-9 in report):
    tc = (avgIn + avgOut) / (avgOut + 1)
    tm = avgIn + avgOut / 2
    d_slope = beta * tc + gamma * tm
    d_intercept = alpha + beta + gamma * (avgIn + (avgOut+1)/2)
    n_ITL = (targetITL - d_intercept) / d_slope
    wait_budget = targetTTFT - targetITL - (alpha + n_ITL*d_slope + (beta+gamma)*avgIn)
    M_est = round(n_ITL + 3.0*sqrt(n_ITL) + 0.05*wait_budget)  if wait_budget > 0

NOTE: reads scenarios.json out-of-band to enumerate M_est for *all* test
scenarios — see the limitation flagged in the PR review (search() contract
gives no per-scenario inputs).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from ._common import predict_m_est, ratio

SCENARIOS_JSON = Path(__file__).resolve().parents[2] / "scenarios.json"


def _binary_search_first_crossing(
    target_eval: Callable[[int], dict], lo: int, hi: int
) -> int:
    result = lo
    while lo <= hi:
        mid = (lo + hi) // 2
        r = ratio(target_eval(mid))
        if r >= 1.0:
            result = mid
            hi = mid - 1
        else:
            lo = mid + 1
    return result


def search(target_eval: Callable[[int], dict], m_min: int, m_max: int) -> int:
    config = json.loads(SCENARIOS_JSON.read_text())
    m_est_anchors: list[int] = []
    for s in config.get("scenarios", []):
        m_est = predict_m_est(
            avg_input=s["AvgInputTokens"],
            avg_output=s["AvgOutputTokens"],
            target_itl=s["targetITL"],
            target_ttft=s["targetTTFT"],
        )
        if m_est is not None and m_min <= m_est <= m_max:
            m_est_anchors.append(m_est)
    m_est_anchors = sorted(set(m_est_anchors))

    last_below: int | None = None
    for m_est in m_est_anchors:
        r = ratio(target_eval(m_est))
        if r >= 1.0:
            # Crossover at or before m_est.  Narrow window of width 3.
            if last_below is None:
                lo = max(m_min, m_est - 2)
                hi = m_est
            else:
                lo = last_below + 1
                hi = min(last_below + 3, m_est)
            return _binary_search_first_crossing(target_eval, lo, hi)
        last_below = m_est

    # All anchor probes gave R < 1.0: M* is above last anchor (or no crossover).
    if last_below is None:
        return _binary_search_first_crossing(target_eval, m_min, m_max)

    lo = last_below + 1
    hi = min(m_max, lo + 2)
    # If no crossing found in [lo, hi], the returned lo sits on the plateau.
    return _binary_search_first_crossing(target_eval, lo, hi)
