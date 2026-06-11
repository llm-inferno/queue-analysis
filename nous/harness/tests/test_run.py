import json
from pathlib import Path
import pytest

from nous.harness import run as run_module
from nous.harness.scenarios import Scenario


def test_load_strategy_module_returns_callable_search(tmp_path):
    strat = tmp_path / "s.py"
    strat.write_text("def search(target_eval, m_min, m_max):\n    return 5\n")
    fn = run_module.load_strategy(strat)
    assert callable(fn)
    assert fn(None, 1, 10) == 5


def test_load_strategy_rejects_module_without_search(tmp_path):
    strat = tmp_path / "bad.py"
    strat.write_text("x = 1\n")
    with pytest.raises(AttributeError):
        run_module.load_strategy(strat)


def test_run_strategy_on_scenario_uses_oracle_and_truth(monkeypatch):
    """Pure-unit slice: no server, no HTTP. Verify wiring.

    We monkeypatch make_oracle to a synthetic curve and supply truth inline.
    The strategy calls eval_ for m=1..9 (9 calls), then run_strategy_on_scenario
    makes one extra confirmatory eval_(m_chosen) call, so total calls == 10.
    """
    s = Scenario(name="x", avg_input_tokens=1, avg_output_tokens=1,
                 target_itl=10.0, target_ttft=10.0, max_queue_size=10,
                 alpha=12.0, beta=0.05, gamma=0.0005, regime="crossover")

    def fake_make_oracle(base_url, scenario, **kw):
        from nous.harness.oracle import OracleStats
        stats = OracleStats()
        def eval_(m):
            stats.calls += 1
            return {"throughput": float(m * (10 - m))}
        return eval_, stats
    monkeypatch.setattr(run_module, "make_oracle", fake_make_oracle)

    truth = {"M_truth": 5, "throughput_truth": 25.0}
    def strategy_search(eval_, m_min, m_max):
        best, bv = m_min, -1
        for m in range(m_min, m_max + 1):
            v = eval_(m)["throughput"]
            if v > bv:
                bv, best = v, m
        return best

    result = run_module.run_strategy_on_scenario(
        base_url="http://x", scenario=s, search=strategy_search,
        m_min=1, m_max=9, truth=truth, strategy_name="ex",
    )
    assert result.M_chosen == 5
    assert result.throughput_chosen == 25.0
    assert result.calls == 10  # 9 strategy calls + 1 harness confirmation call
    assert result.gap_throughput_rel == 0.0
    assert result.gap_M == 0
    assert result.scenario == "x"
    assert result.strategy == "ex"


def test_run_strategy_rejects_out_of_range_M(monkeypatch):
    """The harness must raise if a strategy returns M outside [m_min, m_max]."""
    s = Scenario(name="x", avg_input_tokens=1, avg_output_tokens=1,
                 target_itl=10.0, target_ttft=10.0, max_queue_size=10,
                 alpha=12.0, beta=0.05, gamma=0.0005, regime="crossover")

    def fake_make_oracle(base_url, scenario, **kw):
        from nous.harness.oracle import OracleStats
        stats = OracleStats()
        def eval_(m):
            stats.calls += 1
            return {"throughput": 1.0}
        return eval_, stats
    monkeypatch.setattr(run_module, "make_oracle", fake_make_oracle)

    def bad_strategy(eval_, m_min, m_max):
        return m_max + 1  # off-the-end

    truth = {"M_truth": 5, "throughput_truth": 1.0}
    with pytest.raises(ValueError, match="outside"):
        run_module.run_strategy_on_scenario(
            base_url="http://x", scenario=s, search=bad_strategy,
            m_min=1, m_max=9, truth=truth, strategy_name="bad",
        )
