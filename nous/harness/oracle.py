"""target_eval factory: a counted, scenario-bound oracle for a strategy."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable

import requests

from nous.harness.scenarios import Scenario, scenario_to_problem


@dataclass
class OracleStats:
    calls: int = 0


def make_oracle(
    base_url: str,
    scenario: Scenario,
    *,
    alpha: float = 12.0,
    beta: float = 0.05,
    gamma: float = 0.0005,
    timeout: float = 30.0,
) -> tuple[Callable[[int], dict], OracleStats]:
    """Return (target_eval, stats). The strategy must call target_eval(m).

    target_eval increments stats.calls atomically per call and returns the
    parsed AnalysisData JSON for that maxBatchSize.
    """
    stats = OracleStats()
    url = f"{base_url}/target"

    def target_eval(m: int) -> dict:
        problem = scenario_to_problem(scenario, m, alpha=alpha, beta=beta, gamma=gamma)
        resp = requests.post(url, json=problem, timeout=timeout)
        resp.raise_for_status()
        stats.calls += 1
        return resp.json()

    return target_eval, stats
