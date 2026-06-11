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
    timeout: float = 30.0,
) -> tuple[Callable[[int], dict], OracleStats]:
    """Return (target_eval, stats). target_eval(m) posts to /target using the
    scenario's own alpha/beta/gamma. HTTP 400 -> {"throughput": 0.0}, uncounted.
    """
    stats = OracleStats()
    url = f"{base_url}/target"

    def target_eval(m: int) -> dict:
        problem = scenario_to_problem(scenario, m)
        resp = requests.post(url, json=problem, timeout=timeout)
        if resp.status_code == 400:
            return {"throughput": 0.0}
        resp.raise_for_status()
        stats.calls += 1
        return resp.json()

    return target_eval, stats
