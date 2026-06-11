"""predictor_naive: predictor with scenario identification but NO ratio refinement.

Ablation of predictor_direct: uses the same anchor-probing to identify which
M_est is active, then returns M_est directly without the ±2 ratio-based
refinement. This isolates the value of the refinement step.

When predictor error > 0, gap > 0 (demonstrates refinement necessity).

Strategy calls: 2-3 (the harness adds 1 confirmatory call to result.calls).
Gap: up to 2.47% for baseline (M_est=38 vs M*=40).

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


def search(target_eval: Callable[[int], dict], params: dict, m_min: int, m_max: int) -> int:
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

    if not m_est_anchors:
        return m_max

    last_below: int | None = None

    for m_est in m_est_anchors:
        r = ratio(target_eval(m_est))
        if r >= 1.0:
            # Crossover at or before m_est. This anchor is at/above M*.
            # Return the lower anchor (which is the active M_est) if available.
            if last_below is not None:
                return last_below
            # First probe crossed: return m_est itself.
            return m_est
        last_below = m_est

    # All anchors below crossover. Return the last (highest) anchor.
    return last_below
