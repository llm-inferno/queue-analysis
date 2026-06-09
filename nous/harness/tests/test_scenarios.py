from pathlib import Path
import json
import pytest
from nous.harness.scenarios import Scenario, load_scenarios, scenario_to_problem


REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIOS_PATH = REPO_ROOT / "nous" / "scenarios.json"


def test_loads_four_named_scenarios():
    scenarios = load_scenarios(SCENARIOS_PATH)
    assert [s.name for s in scenarios] == [
        "baseline", "short-tight-ttft", "long-loose-itl", "small-queue",
    ]


def test_baseline_fields():
    scenarios = load_scenarios(SCENARIOS_PATH)
    s = next(s for s in scenarios if s.name == "baseline")
    assert s.avg_input_tokens == 256
    assert s.avg_output_tokens == 512
    assert s.target_itl == 20.0
    assert s.target_ttft == 60.0
    assert s.max_queue_size == 128


def test_scenario_to_problem_data_shape():
    s = Scenario(
        name="x", avg_input_tokens=100, avg_output_tokens=200,
        target_itl=15.0, target_ttft=50.0, max_queue_size=64,
    )
    payload = scenario_to_problem(s, max_batch_size=24)
    assert payload["maxBatchSize"] == 24
    assert payload["AvgInputTokens"] == 100
    assert payload["AvgOutputTokens"] == 200
    assert payload["targetITL"] == 15.0
    assert payload["targetTTFT"] == 50.0
    assert payload["maxQueueSize"] == 64
    assert payload["alpha"] == 12.0
    assert payload["beta"] == 0.05
    assert payload["gamma"] == 0.0005


def test_load_rejects_unknown_scenario_field(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "scenarios": [{"name": "x", "AvgInputTokens": 100, "AvgOutputTokens": 100,
                       "targetITL": 10.0, "targetTTFT": 30.0, "maxQueueSize": 64,
                       "extraneous": True}]
    }))
    with pytest.raises(ValueError):
        load_scenarios(bad)
