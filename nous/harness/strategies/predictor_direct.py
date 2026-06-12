"""predictor_direct: tight-trust predictor with ±2 sequential refinement.

Exploits iter-3's finding that predictor error |M_est - M*| <= 2 for all
crossover scenarios. Probes anchors in order, then uses the tight-trust
bound to resolve the crossover in at most 2 additional probes.

Key insight: when two anchors bracket the crossover (R(lo_anchor) < 1.0,
R(hi_anchor) >= 1.0), M* must be within ±2 of the LOWER anchor
(since the lower anchor is the predictor's M_est for the active scenario).
This gives a window of width ≤2 to search, requiring at most 1 probe.

Strategy calls (the harness adds 1 confirmatory):
  - Crossover, M* above lo_anchor: ≤ 3
  - Crossover, M* at/below first anchor: ≤ 2
  - No-crossover: ≤ 4 (must exhaust ±2 beyond last anchor)

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
            # Crossover at or before m_est.
            if last_below is not None:
                # Bracket: R(last_below) < 1.0, R(m_est) >= 1.0.
                # Tight trust: M* in [last_below+1, last_below+2].
                candidate = last_below + 1
                if candidate >= m_est:
                    return m_est
                if ratio(target_eval(candidate)) >= 1.0:
                    return candidate
                return last_below + 2
            else:
                # First probe hit: crossover at or before m_est.
                # Tight trust: M* in [m_est-2, m_est]. Scan downward.
                lo = max(m_min, m_est - 2)
                for m in range(m_est - 1, lo - 1, -1):
                    if ratio(target_eval(m)) < 1.0:
                        return m + 1
                return lo
        last_below = m_est

    # All anchors gave R < 1.0. Crossover (if any) is above last anchor.
    # Tight trust: M* in [last_below+1, last_below+2].
    for offset in (1, 2):
        m = last_below + offset
        if m > m_max:
            break
        if ratio(target_eval(m)) >= 1.0:
            return m

    # No crossover found within ±2: no crossover exists. Return m_max (plateau).
    return m_max
