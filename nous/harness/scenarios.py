"""Scenario data and ProblemData construction.

A Scenario is the part of ProblemData that varies across the campaign's test
cases. As of the reformulation campaign, the service constants (alpha, beta,
gamma) are PER-SCENARIO (they are swept), and each scenario carries a `regime`
label used for the iter-5 per-regime breakdown.
"""

from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path


ALLOWED_FIELDS = {
    "name", "AvgInputTokens", "AvgOutputTokens",
    "targetITL", "targetTTFT", "maxQueueSize",
    "alpha", "beta", "gamma", "regime",
}


@dataclass(frozen=True)
class Scenario:
    name: str
    avg_input_tokens: int
    avg_output_tokens: int
    target_itl: float
    target_ttft: float
    max_queue_size: int
    alpha: float
    beta: float
    gamma: float
    regime: str


@dataclass(frozen=True)
class CampaignConfig:
    scenarios: tuple[Scenario, ...]
    m_min: int
    m_max: int


def load_scenarios(path: str | Path) -> list[Scenario]:
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
            alpha=entry["alpha"],
            beta=entry["beta"],
            gamma=entry["gamma"],
            regime=entry["regime"],
        ))
    search_range = raw["search_range"]
    return CampaignConfig(
        scenarios=tuple(scenarios),
        m_min=search_range["m_min"],
        m_max=search_range["m_max"],
    )


def scenario_to_params(s: Scenario) -> dict:
    """The params dict passed to strategies and usable by formulas.py."""
    return {
        "alpha": s.alpha, "beta": s.beta, "gamma": s.gamma,
        "AvgInputTokens": s.avg_input_tokens,
        "AvgOutputTokens": s.avg_output_tokens,
        "targetITL": s.target_itl, "targetTTFT": s.target_ttft,
        "maxQueueSize": s.max_queue_size,
    }


def scenario_to_problem(s: Scenario, max_batch_size: int, *, rps: float = 0.0) -> dict:
    """Build a /target POST body for a (scenario, M) pair.

    /target ignores RPS (it solves for it) but the field must be present per the
    ProblemData schema. alpha/beta/gamma come from the scenario itself.
    """
    return {
        "RPS": rps,
        "maxBatchSize": max_batch_size,
        "AvgInputTokens": s.avg_input_tokens,
        "AvgOutputTokens": s.avg_output_tokens,
        "alpha": s.alpha,
        "beta": s.beta,
        "gamma": s.gamma,
        "maxQueueSize": s.max_queue_size,
        "targetITL": s.target_itl,
        "targetTTFT": s.target_ttft,
    }
