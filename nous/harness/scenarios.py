"""Scenario data and ProblemData construction.

A Scenario is the part of ProblemData that varies across the campaign's named
test cases. Constants (alpha/beta/gamma) and the M search range live alongside
the scenario list in scenarios.json.
"""

from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ALLOWED_FIELDS = {
    "name", "AvgInputTokens", "AvgOutputTokens",
    "targetITL", "targetTTFT", "maxQueueSize",
}


@dataclass(frozen=True)
class Scenario:
    name: str
    avg_input_tokens: int
    avg_output_tokens: int
    target_itl: float
    target_ttft: float
    max_queue_size: int


@dataclass(frozen=True)
class CampaignConfig:
    scenarios: tuple[Scenario, ...]
    alpha: float
    beta: float
    gamma: float
    m_min: int
    m_max: int


def load_scenarios(path: str | Path) -> list[Scenario]:
    """Load and validate scenarios.json, returning just the Scenario list.

    Use load_campaign() if you also need the constants and M range.
    """
    return list(load_campaign(path).scenarios)


def load_campaign(path: str | Path) -> CampaignConfig:
    raw = json.loads(Path(path).read_text())
    scenarios = []
    for entry in raw["scenarios"]:
        unknown = set(entry) - ALLOWED_FIELDS
        if unknown:
            raise ValueError(f"unknown fields in scenario {entry.get('name')}: {unknown}")
        scenarios.append(Scenario(
            name=entry["name"],
            avg_input_tokens=entry["AvgInputTokens"],
            avg_output_tokens=entry["AvgOutputTokens"],
            target_itl=entry["targetITL"],
            target_ttft=entry["targetTTFT"],
            max_queue_size=entry["maxQueueSize"],
        ))
    constants = raw["constants"]
    search_range = raw["search_range"]
    return CampaignConfig(
        scenarios=tuple(scenarios),
        alpha=constants["alpha"],
        beta=constants["beta"],
        gamma=constants["gamma"],
        m_min=search_range["m_min"],
        m_max=search_range["m_max"],
    )


def scenario_to_problem(
    s: Scenario,
    max_batch_size: int,
    *,
    alpha: float = 12.0,
    beta: float = 0.05,
    gamma: float = 0.0005,
    rps: float = 0.0,
) -> dict:
    """Build a /target POST body for a (scenario, M) pair.

    /target ignores RPS (it solves for it), but the field must be present per
    the ProblemData schema in queue-analysis/README.md.
    """
    return {
        "RPS": rps,
        "maxBatchSize": max_batch_size,
        "AvgInputTokens": s.avg_input_tokens,
        "AvgOutputTokens": s.avg_output_tokens,
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "maxQueueSize": s.max_queue_size,
        "targetITL": s.target_itl,
        "targetTTFT": s.target_ttft,
    }
