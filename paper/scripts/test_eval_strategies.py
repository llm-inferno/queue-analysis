# paper/scripts/test_eval_strategies.py
import eval_strategies as E


def test_cache_oracle_counts_only_feasible():
    f_curve = [{"m": 1, "throughput": 0.0}, {"m": 2, "throughput": 5.0},
               {"m": 3, "throughput": 7.0}]
    ev, stats = E.cache_oracle(f_curve)
    assert ev(1) == {"throughput": 0.0}      # infeasible
    assert ev(2) == {"throughput": 5.0}      # feasible
    assert ev(99) == {"throughput": 0.0}     # out of range -> infeasible
    assert stats["calls"] == 1               # only m=2 counted
    assert stats["probes"] == [1, 2, 99]     # every probe recorded


def test_epsilon_onset_smallest_within_two_percent():
    # rises 0,1,2,...,10 then flat 10 -> peak 10, 0.98*10=9.8 first met at m=10
    f_curve = [{"m": m, "throughput": float(min(m, 10))} for m in range(1, 21)]
    assert E.epsilon_onset(f_curve, eps=0.02) == 10


def test_epsilon_onset_infeasible_returns_none():
    f_curve = [{"m": m, "throughput": 0.0} for m in range(1, 6)]
    assert E.epsilon_onset(f_curve, eps=0.02) is None


import json
from pathlib import Path
from nous.harness.strategies import formula_guided, naive_max

REPO = Path(__file__).resolve().parents[2]


def _baseline_cache():
    return json.loads((REPO / "nous" / "cache" / "truth-baseline.json").read_text())


def _baseline_params():
    scns = json.loads((REPO / "nous" / "scenarios.json").read_text())["scenarios"]
    s = next(x for x in scns if x["name"] == "baseline")
    return {k: s[k] for k in E.PARAM_KEYS}


def test_replay_naive_max_one_call():
    rec = E.replay(naive_max.search, _baseline_params(), _baseline_cache())
    assert rec["M_chosen"] == E.M_MAX
    assert rec["calls"] == 1                       # confirmatory only
    assert rec["gap_argmax"] == E.M_MAX - rec["M_truth"]


def test_replay_formula_guided_baseline_trace():
    rec = E.replay(formula_guided.search, _baseline_params(), _baseline_cache())
    assert rec["probes"][0] == E.M_MAX             # high anchor
    assert rec["calls"] <= 8
    assert rec["M_chosen"] == 67
    assert rec["M_onset"] == 66
    assert rec["gap_f"] <= 0.02


def test_evaluate_all_reproduces_headline():
    results = E.evaluate_all()
    bench_fg = results["aggregates"]["benchmark"]["formula_guided"]
    assert bench_fg["calls_worst"] <= 8
    assert bench_fg["gap_f_worst"] <= 0.02
    assert bench_fg["gap_argmax_worst"] == 72
    assert bench_fg["gap_onset_worst"] == 38
    # baselines violate epsilon on the benchmark
    assert results["aggregates"]["benchmark"]["naive_max"]["gap_f_worst"] > 0.02
    assert results["aggregates"]["benchmark"]["naive_ternary"]["gap_f_worst"] > 0.02
    # feasible-count invariant
    assert results["aggregates"]["benchmark"]["n_scenarios"] == 25
