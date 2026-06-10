"""Mock-based smoke tests for the 7 candidate strategies.

The harness builds a synthetic target_eval that emulates the two-phase f(M)
shape — R(M) = RPSTargetTTFT/RPSTargetITL crosses 1.0 at a known m_star,
and throughput is concave-rising before m_star and flat after — so each
strategy can be checked end-to-end without the Go analyzer.

For predictor_* strategies (which read scenarios.json out-of-band), the
file is monkey-patched to a tmp file with a single synthetic scenario.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from nous.harness.strategies import (
    adaptive_binary,
    adaptive_early_exit,
    adaptive_interpolation,
    ratio_binary_search,
)


def make_eval(m_star: int, *, with_crossover: bool = True):
    """Synthetic target_eval and a shared call counter.

    Returns (target_eval, calls) where `calls` is a list whose length is
    the number of evaluations.

    With crossover: R(m) = 0.5 + 0.5 * m / m_star   (≈1.0 at m_star)
    Without crossover: R(m) = 0.4 (always below 1.0)
    Throughput rises up to m_star then plateaus exactly.
    """
    calls: list[int] = []

    def target_eval(m: int) -> dict:
        calls.append(m)
        if with_crossover:
            r = 0.5 + 0.5 * m / m_star
        else:
            r = 0.4
        # Pin RPSTargetITL=1 so RPSTargetTTFT == r.
        rps_itl = 1.0
        rps_ttft = r * rps_itl
        if m <= m_star:
            throughput = float(m)
        else:
            throughput = float(m_star)  # plateau
        return {
            "throughput": throughput,
            "RPSTargetTTFT": rps_ttft,
            "RPSTargetITL": rps_itl,
        }

    return target_eval, calls


@pytest.mark.parametrize("strategy_module", [
    ratio_binary_search,
    adaptive_binary,
    adaptive_early_exit,
    adaptive_interpolation,
])
def test_ratio_strategies_find_crossover(strategy_module):
    target_eval, calls = make_eval(m_star=40)
    chosen = strategy_module.search(target_eval, m_min=1, m_max=256)
    assert chosen == 40, f"{strategy_module.__name__} returned {chosen}, expected 40"
    assert 1 <= chosen <= 256
    assert len(calls) <= 12, f"{strategy_module.__name__} took {len(calls)} calls"


@pytest.mark.parametrize("strategy_module", [
    adaptive_binary,
    adaptive_early_exit,
    adaptive_interpolation,
])
def test_adaptive_strategies_short_circuit_no_crossover(strategy_module):
    target_eval, calls = make_eval(m_star=999, with_crossover=False)
    chosen = strategy_module.search(target_eval, m_min=1, m_max=256)
    assert chosen == 256, f"{strategy_module.__name__} returned {chosen}, expected 256"
    assert len(calls) <= 2, (
        f"{strategy_module.__name__} took {len(calls)} calls, "
        "expected <= 2 for early-exit on no-crossover"
    )


def test_ratio_binary_search_no_crossover_falls_through_to_m_max():
    target_eval, calls = make_eval(m_star=999, with_crossover=False)
    chosen = ratio_binary_search.search(target_eval, m_min=1, m_max=256)
    assert chosen == 256
    # Full bisection on [2, 256] = 8 probes.
    assert len(calls) == 8


def _write_scenarios_json(path: Path, scenarios: list[dict]) -> None:
    path.write_text(json.dumps({
        "constants": {"alpha": 12.0, "beta": 0.05, "gamma": 0.0005},
        "search_range": {"m_min": 1, "m_max": 256},
        "scenarios": scenarios,
    }))


@pytest.mark.parametrize("strategy_name", [
    "predictor_naive",
    "predictor_direct",
    "predictor_hybrid",
])
def test_predictor_strategies_with_isolated_scenarios(tmp_path, monkeypatch, strategy_name):
    """Predictor strategies reload scenarios.json — patch it to a synthetic file
    with a single scenario whose closed-form M_est lands near m_star=40.

    We don't test exact M_est match (the regression fit can be ±2); we just
    assert the strategy returns within the predicted ±2 window of m_star and
    stays under 6 calls.
    """
    scenarios_json = tmp_path / "scenarios.json"
    _write_scenarios_json(scenarios_json, [{
        "name": "synthetic",
        "AvgInputTokens": 256,
        "AvgOutputTokens": 512,
        "targetITL": 20.0,
        "targetTTFT": 60.0,
        "maxQueueSize": 128,
    }])

    module = importlib.import_module(f"nous.harness.strategies.{strategy_name}")
    monkeypatch.setattr(module, "SCENARIOS_JSON", scenarios_json)

    target_eval, calls = make_eval(m_star=40)
    chosen = module.search(target_eval, m_min=1, m_max=256)

    assert 1 <= chosen <= 256
    assert abs(chosen - 40) <= 2, (
        f"{strategy_name} returned {chosen}, expected within ±2 of 40"
    )
    assert len(calls) <= 6, (
        f"{strategy_name} took {len(calls)} calls, expected <= 6"
    )
