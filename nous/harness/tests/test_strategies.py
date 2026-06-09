from nous.harness.strategies.example_linear_scan import search


def test_example_scan_returns_argmax_on_synthetic_curve():
    """f(m) = m * (40 - m) → peak at m=20 on [1, 39]."""
    def fake_eval(m):
        return {"throughput": float(m * (40 - m))}
    chosen = search(fake_eval, m_min=1, m_max=39)
    assert chosen == 20


def test_example_scan_calls_eval_once_per_m():
    seen = []
    def fake_eval(m):
        seen.append(m)
        return {"throughput": float(m)}
    search(fake_eval, m_min=5, m_max=8)
    assert seen == [5, 6, 7, 8]
