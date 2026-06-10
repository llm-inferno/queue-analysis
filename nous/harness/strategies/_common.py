"""Shared helpers for search strategies.

`ratio(result)` extracts R(M) = RPSTargetTTFT / RPSTargetITL from a /target
response. Six of the seven strategies use this.

`predict_m_est(...)` is the closed-form (regression-fit, see RP-9 in the
report) predictor for the TTFT/ITL crossover M*. Returns None if the
predictor classifies the scenario as no-crossover (n_ITL <= 0 or
wait_budget <= 0).

NOTE: ALPHA/BETA/GAMMA are duplicated here from oracle.py defaults and
scenarios.json["constants"]. See follow-up issue: predictor_* should
receive constants via the search() contract instead of hardcoding.
"""

from __future__ import annotations

import math


ALPHA, BETA, GAMMA = 12.0, 0.05, 0.0005


def ratio(result: dict) -> float:
    """R(M) = RPSTargetTTFT / RPSTargetITL; 0.0 if ITL is unavailable."""
    ttft = float(result.get("RPSTargetTTFT", 0))
    itl = float(result.get("RPSTargetITL", 1))
    if itl <= 0:
        return 0.0
    return ttft / itl


def predict_m_est(avg_input: float, avg_output: float,
                  target_itl: float, target_ttft: float) -> int | None:
    """Predicted M* via the iter-3 regression fit; None for no-crossover."""
    tc = (avg_input + avg_output) / (avg_output + 1)
    tm = avg_input + avg_output / 2
    d_slope = BETA * tc + GAMMA * tm
    d_intercept = ALPHA + BETA + GAMMA * (avg_input + (avg_output + 1) / 2)
    n_itl = (target_itl - d_intercept) / d_slope
    if n_itl <= 0:
        return None
    pt_n = ALPHA + n_itl * d_slope + (BETA + GAMMA) * avg_input
    wait_budget = target_ttft - target_itl - pt_n
    if wait_budget <= 0:
        return None
    return round(n_itl + 3.0 * math.sqrt(n_itl) + 0.05 * wait_budget)
