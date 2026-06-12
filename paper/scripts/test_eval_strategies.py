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
