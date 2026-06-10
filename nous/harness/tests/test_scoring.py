import pytest
from nous.harness.scoring import compute_gap, ScenarioResult


def test_gap_with_optimal_choice_is_zero():
    r = compute_gap(m_chosen=40, throughput_chosen=4.0, m_truth=40, throughput_truth=4.0)
    assert r["gap_throughput_rel"] == pytest.approx(0.0)
    assert r["gap_M"] == 0


def test_gap_relative_throughput_formula():
    r = compute_gap(m_chosen=38, throughput_chosen=3.92, m_truth=40, throughput_truth=4.0)
    assert r["gap_throughput_rel"] == pytest.approx(0.02)
    assert r["gap_M"] == 2


def test_gap_clamps_negative_relative_to_zero():
    """If somehow chosen > truth (numerical noise), gap is reported as 0, not negative."""
    r = compute_gap(m_chosen=40, throughput_chosen=4.01, m_truth=40, throughput_truth=4.0)
    assert r["gap_throughput_rel"] == 0.0


def test_gap_zero_truth_returns_inf_or_nan_safely():
    """Truth throughput == 0 means no feasible solution at any M; gap is undefined."""
    r = compute_gap(m_chosen=10, throughput_chosen=0.0, m_truth=10, throughput_truth=0.0)
    assert r["gap_throughput_rel"] == 0.0  # both zero → no gap


def test_scenario_result_dataclass_round_trip():
    sr = ScenarioResult(
        scenario="baseline", strategy="ex",
        M_chosen=38, calls=7, throughput_chosen=3.92,
        M_truth=40, throughput_truth=4.0,
        gap_throughput_rel=0.02, gap_M=2,
        wall_clock_seconds=1.4, internal_solve_calls=56,
    )
    d = sr.to_dict()
    assert d["scenario"] == "baseline"
    assert d["calls"] == 7
    assert d["gap_throughput_rel"] == pytest.approx(0.02)
