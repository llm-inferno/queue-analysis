import pytest
from nous.harness.scenarios import Scenario
from nous.harness.oracle import make_oracle, OracleStats


SCENARIO = Scenario(
    name="t", avg_input_tokens=100, avg_output_tokens=200,
    target_itl=15.0, target_ttft=50.0, max_queue_size=64,
)


def fake_post(url, json, **kw):
    class R:
        status_code = 200
        def json(self_):
            return {
                "throughput": 0.1 * json["maxBatchSize"],
                "avgITL": 1.0,
                "avgTTFT": 1.0,
                "maxRPS": 1.0,
            }
        def raise_for_status(self_): return None
    return R()


def test_target_eval_hits_target_endpoint(monkeypatch):
    seen_urls = []
    def capture(url, json, **kw):
        seen_urls.append(url)
        return fake_post(url, json, **kw)
    monkeypatch.setattr("nous.harness.oracle.requests.post", capture)
    eval_, stats = make_oracle("http://x", SCENARIO)
    eval_(10)
    assert seen_urls == ["http://x/target"]


def test_oracle_counts_calls(monkeypatch):
    monkeypatch.setattr("nous.harness.oracle.requests.post", fake_post)
    eval_, stats = make_oracle("http://x", SCENARIO)
    for m in (5, 10, 20):
        eval_(m)
    assert stats.calls == 3


def test_oracle_returns_throughput_for_M(monkeypatch):
    monkeypatch.setattr("nous.harness.oracle.requests.post", fake_post)
    eval_, stats = make_oracle("http://x", SCENARIO)
    out = eval_(7)
    assert out["throughput"] == pytest.approx(0.7)


def test_oracle_payload_uses_scenario_fields(monkeypatch):
    captured = {}
    def cap(url, json, **kw):
        captured.update(json)
        return fake_post(url, json, **kw)
    monkeypatch.setattr("nous.harness.oracle.requests.post", cap)
    eval_, _ = make_oracle("http://x", SCENARIO)
    eval_(33)
    assert captured["maxBatchSize"] == 33
    assert captured["AvgInputTokens"] == 100
    assert captured["targetITL"] == 15.0


def test_stats_dataclass_initial_state():
    assert OracleStats().calls == 0
