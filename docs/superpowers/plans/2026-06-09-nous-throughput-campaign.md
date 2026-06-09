# NOUS Throughput Campaign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the harness, scenarios, NOUS configuration, and pre-flight checks needed to launch a NOUS campaign that discovers structural properties of `f(M) = max-RPS-meeting-targets` for the queue-analysis Go server, then justifies an algorithm that finds `argmax_M f` with few `/target` calls.

**Architecture:** Add a self-contained `nous/` directory to the queue-analysis Go repo. The `harness/` subdirectory is a small Python package that owns the lifecycle of the Go analyzer, exposes a `target_eval` oracle to candidate algorithms (counting `/target` calls), and scores results against a one-time brute-force truth cache. NOUS reads `campaign.yaml` (for orchestration) and `description.txt` (for the planner's full brief, sitting inside the repo so the worktree can `cat` it).

**Tech Stack:** Python 3.11+ (stdlib + `requests` + `pytest`), Go 1.x (the existing analyzer), NOUS (`~/Projects/nous/agentic-strategy-evolution`).

**Spec:** [`docs/superpowers/specs/2026-06-09-nous-throughput-campaign-design.md`](../specs/2026-06-09-nous-throughput-campaign-design.md)

---

## File Structure

Created files (all under `queue-analysis/nous/`):

```
nous/
  campaign.yaml                       # NOUS campaign config (~30 lines)
  description.txt                     # full planner brief
  scenarios.json                      # 4 named scenarios
  requirements.txt                    # requests, pytest
  harness/
    __init__.py
    scenarios.py                      # load + validate scenarios.json
    server.py                         # start/stop the Go analyzer, wait for ready
    oracle.py                         # target_eval factory, call counter
    scoring.py                        # gap_throughput_rel, gap_M
    run.py                            # CLI: orchestrates a strategy across scenarios
    baseline_truth.py                 # CLI: one-time brute-force scan → cache
    strategies/
      __init__.py
      example_linear_scan.py          # smoke-test strategy
    tests/
      __init__.py
      test_scenarios.py
      test_oracle.py
      test_scoring.py
      test_smoke_e2e.py               # spins up server, runs example strategy
```

Modified: `.gitignore` (add `nous/cache/`, `nous/results/`, `nous/.venv/`).

Each Python module is small and single-purpose: `server.py` owns process lifecycle, `oracle.py` owns the call-counting wrapper, `scoring.py` owns gap math, `scenarios.py` owns scenario data shape, `run.py` is the wiring CLI. Strategies are pure Python with one function — no dependencies on the harness internals beyond the `target_eval` callable they receive.

---

## Task 1: Scaffold directory layout and dependencies

**Files:**
- Create: `nous/__init__.py`, `nous/harness/__init__.py`, `nous/harness/strategies/__init__.py`, `nous/harness/tests/__init__.py`
- Create: `nous/requirements.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Create empty package init files**

```bash
mkdir -p nous/harness/strategies nous/harness/tests
touch nous/__init__.py nous/harness/__init__.py
touch nous/harness/strategies/__init__.py nous/harness/tests/__init__.py
```

- [ ] **Step 2: Write `nous/requirements.txt`**

```
requests>=2.31
pytest>=7.4
```

- [ ] **Step 3: Append to `.gitignore`**

```
# nous campaign artifacts
nous/cache/
nous/results/
nous/.venv/
.nous/
```

- [ ] **Step 4: Create venv and install deps**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
python3 -m venv nous/.venv
source nous/.venv/bin/activate
pip install -r nous/requirements.txt
```

Expected: `requests` and `pytest` installed without error.

- [ ] **Step 5: Commit**

```bash
git add nous/__init__.py nous/harness/__init__.py nous/harness/strategies/__init__.py nous/harness/tests/__init__.py nous/requirements.txt .gitignore
git commit -m "scaffold nous campaign directory and python deps"
```

---

## Task 2: Scenarios — data + loader

**Files:**
- Create: `nous/scenarios.json`
- Create: `nous/harness/scenarios.py`
- Test: `nous/harness/tests/test_scenarios.py`

- [ ] **Step 1: Write the failing test `nous/harness/tests/test_scenarios.py`**

```python
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
```

- [ ] **Step 2: Run the test — expect failures (module missing)**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
source nous/.venv/bin/activate
PYTHONPATH=. pytest nous/harness/tests/test_scenarios.py -v
```

Expected: `ModuleNotFoundError: No module named 'nous.harness.scenarios'`.

- [ ] **Step 3: Write `nous/scenarios.json`**

```json
{
  "constants": {
    "alpha": 12.0,
    "beta": 0.05,
    "gamma": 0.0005
  },
  "search_range": {
    "m_min": 1,
    "m_max": 256
  },
  "scenarios": [
    {
      "name": "baseline",
      "AvgInputTokens": 256,
      "AvgOutputTokens": 512,
      "targetITL": 20.0,
      "targetTTFT": 60.0,
      "maxQueueSize": 128
    },
    {
      "name": "short-tight-ttft",
      "AvgInputTokens": 128,
      "AvgOutputTokens": 256,
      "targetITL": 20.0,
      "targetTTFT": 25.0,
      "maxQueueSize": 128
    },
    {
      "name": "long-loose-itl",
      "AvgInputTokens": 256,
      "AvgOutputTokens": 1024,
      "targetITL": 40.0,
      "targetTTFT": 200.0,
      "maxQueueSize": 128
    },
    {
      "name": "small-queue",
      "AvgInputTokens": 256,
      "AvgOutputTokens": 512,
      "targetITL": 20.0,
      "targetTTFT": 60.0,
      "maxQueueSize": 16
    }
  ]
}
```

- [ ] **Step 4: Write `nous/harness/scenarios.py`**

```python
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
    constants = raw["constants"]
    search_range = raw["search_range"]
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
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
PYTHONPATH=. pytest nous/harness/tests/test_scenarios.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add nous/scenarios.json nous/harness/scenarios.py nous/harness/tests/test_scenarios.py
git commit -m "scenarios: 4 named scenarios + loader with validation"
```

---

## Task 3: Server lifecycle (start, wait, stop)

**Files:**
- Create: `nous/harness/server.py`
- Test: `nous/harness/tests/test_server.py`

- [ ] **Step 1: Write the failing test `nous/harness/tests/test_server.py`**

```python
import socket
import threading
import time
import pytest
from nous.harness.server import wait_for_port, AnalyzerServer


def test_wait_for_port_returns_when_socket_accepts():
    """wait_for_port should return promptly once something binds."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    def listen():
        sock.listen(1)
        conn, _ = sock.accept()
        conn.close()

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    try:
        wait_for_port("127.0.0.1", port, timeout=2.0)
    finally:
        sock.close()


def test_wait_for_port_times_out_when_no_listener():
    with pytest.raises(TimeoutError):
        wait_for_port("127.0.0.1", 65530, timeout=0.5)


def test_analyzer_server_context_manager_lifecycle(monkeypatch):
    """AnalyzerServer.__enter__ starts the process; __exit__ kills it.
    We monkeypatch the actual subprocess so this test does not require Go.
    """
    started, killed = [], []

    class FakeProc:
        def __init__(self): self.returncode = None
        def poll(self): return self.returncode
        def kill(self): killed.append(True); self.returncode = -9
        def wait(self, timeout=None): self.returncode = -9; return -9

    def fake_popen(cmd, **kwargs):
        started.append(cmd)
        return FakeProc()

    monkeypatch.setattr("nous.harness.server.subprocess.Popen", fake_popen)
    monkeypatch.setattr("nous.harness.server.wait_for_port", lambda *a, **k: None)

    with AnalyzerServer(repo_dir="/tmp", port=8080) as url:
        assert url == "http://127.0.0.1:8080"
        assert started, "Popen should have been called"
    assert killed, "process should have been killed on exit"
```

- [ ] **Step 2: Run — expect ImportError**

```bash
PYTHONPATH=. pytest nous/harness/tests/test_server.py -v
```

Expected: import error.

- [ ] **Step 3: Write `nous/harness/server.py`**

```python
"""Lifecycle of the Go queue-analysis HTTP server."""

from __future__ import annotations
import socket
import subprocess
import time
from contextlib import AbstractContextManager
from pathlib import Path


def wait_for_port(host: str, port: int, timeout: float = 30.0) -> None:
    """Block until host:port accepts a TCP connection, or raise TimeoutError."""
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError as e:
            last_err = e
            time.sleep(0.1)
    raise TimeoutError(f"port {host}:{port} did not open within {timeout}s; last error: {last_err}")


class AnalyzerServer(AbstractContextManager):
    """Spawn `go run main.go` in repo_dir, wait for :port, kill on exit."""

    def __init__(self, repo_dir: str | Path, port: int = 8080, ready_timeout: float = 60.0):
        self.repo_dir = str(repo_dir)
        self.port = port
        self.ready_timeout = ready_timeout
        self._proc: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> str:
        self._proc = subprocess.Popen(
            ["go", "run", "main.go"],
            cwd=self.repo_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_for_port("127.0.0.1", self.port, timeout=self.ready_timeout)
        except Exception:
            self._kill()
            raise
        return self.url

    def __exit__(self, exc_type, exc, tb) -> None:
        self._kill()

    def _kill(self) -> None:
        if self._proc is None or self._proc.poll() is not None:
            return
        self._proc.kill()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
PYTHONPATH=. pytest nous/harness/tests/test_server.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add nous/harness/server.py nous/harness/tests/test_server.py
git commit -m "harness: server lifecycle (start, wait_for_port, kill)"
```

---

## Task 4: Oracle (target_eval with call counter)

**Files:**
- Create: `nous/harness/oracle.py`
- Test: `nous/harness/tests/test_oracle.py`

- [ ] **Step 1: Write the failing test `nous/harness/tests/test_oracle.py`**

```python
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
```

- [ ] **Step 2: Run — expect ImportError**

```bash
PYTHONPATH=. pytest nous/harness/tests/test_oracle.py -v
```

- [ ] **Step 3: Write `nous/harness/oracle.py`**

```python
"""target_eval factory: a counted, scenario-bound oracle for a strategy."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable

import requests

from nous.harness.scenarios import Scenario, scenario_to_problem


@dataclass
class OracleStats:
    calls: int = 0


def make_oracle(
    base_url: str,
    scenario: Scenario,
    *,
    alpha: float = 12.0,
    beta: float = 0.05,
    gamma: float = 0.0005,
    timeout: float = 30.0,
) -> tuple[Callable[[int], dict], OracleStats]:
    """Return (target_eval, stats). The strategy must call target_eval(m).

    target_eval increments stats.calls atomically per call and returns the
    parsed AnalysisData JSON for that maxBatchSize.
    """
    stats = OracleStats()
    url = f"{base_url}/target"

    def target_eval(m: int) -> dict:
        problem = scenario_to_problem(scenario, m, alpha=alpha, beta=beta, gamma=gamma)
        resp = requests.post(url, json=problem, timeout=timeout)
        resp.raise_for_status()
        stats.calls += 1
        return resp.json()

    return target_eval, stats
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
PYTHONPATH=. pytest nous/harness/tests/test_oracle.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add nous/harness/oracle.py nous/harness/tests/test_oracle.py
git commit -m "harness: target_eval oracle with call counter"
```

---

## Task 5: Scoring (gap formulas)

**Files:**
- Create: `nous/harness/scoring.py`
- Test: `nous/harness/tests/test_scoring.py`

- [ ] **Step 1: Write the failing test `nous/harness/tests/test_scoring.py`**

```python
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
```

- [ ] **Step 2: Run — expect ImportError**

```bash
PYTHONPATH=. pytest nous/harness/tests/test_scoring.py -v
```

- [ ] **Step 3: Write `nous/harness/scoring.py`**

```python
"""Pareto-axis computations: gap_throughput_rel and gap_M."""

from __future__ import annotations
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ScenarioResult:
    scenario: str
    strategy: str
    M_chosen: int
    calls: int
    throughput_chosen: float
    M_truth: int
    throughput_truth: float
    gap_throughput_rel: float
    gap_M: int
    wall_clock_seconds: float
    internal_solve_calls: int

    def to_dict(self) -> dict:
        return asdict(self)


def compute_gap(*, m_chosen: int, throughput_chosen: float,
                m_truth: int, throughput_truth: float) -> dict:
    if throughput_truth <= 0.0:
        rel = 0.0
    else:
        raw = (throughput_truth - throughput_chosen) / throughput_truth
        rel = max(raw, 0.0)
    return {
        "gap_throughput_rel": rel,
        "gap_M": abs(m_chosen - m_truth),
    }
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
PYTHONPATH=. pytest nous/harness/tests/test_scoring.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add nous/harness/scoring.py nous/harness/tests/test_scoring.py
git commit -m "harness: gap_throughput_rel and gap_M scoring"
```

---

## Task 6: Example strategy (smoke-test reference)

**Files:**
- Create: `nous/harness/strategies/example_linear_scan.py`
- Test: `nous/harness/tests/test_strategies.py`

- [ ] **Step 1: Write the failing test `nous/harness/tests/test_strategies.py`**

```python
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
```

- [ ] **Step 2: Run — expect ImportError**

```bash
PYTHONPATH=. pytest nous/harness/tests/test_strategies.py -v
```

- [ ] **Step 3: Write `nous/harness/strategies/example_linear_scan.py`**

```python
"""Reference strategy: brute-force scan. Used only for harness smoke tests.

Real candidate algorithms live alongside this file once the campaign starts
producing them. Every strategy module exposes a single `search` function.
"""

from __future__ import annotations
from typing import Callable


def search(target_eval: Callable[[int], dict], m_min: int, m_max: int) -> int:
    """Return the M in [m_min, m_max] with the highest throughput."""
    best_m = m_min
    best_t = -1.0
    for m in range(m_min, m_max + 1):
        result = target_eval(m)
        t = float(result["throughput"])
        if t > best_t:
            best_t = t
            best_m = m
    return best_m
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
PYTHONPATH=. pytest nous/harness/tests/test_strategies.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add nous/harness/strategies/example_linear_scan.py nous/harness/tests/test_strategies.py
git commit -m "harness: reference linear-scan strategy"
```

---

## Task 7: `run.py` CLI — wires everything together

**Files:**
- Create: `nous/harness/run.py`
- Test: `nous/harness/tests/test_run.py`

- [ ] **Step 1: Write the failing test `nous/harness/tests/test_run.py`**

```python
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
    """
    s = Scenario(name="x", avg_input_tokens=1, avg_output_tokens=1,
                 target_itl=10.0, target_ttft=10.0, max_queue_size=10)

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
    assert result.calls == 9
    assert result.gap_throughput_rel == 0.0
    assert result.gap_M == 0
    assert result.scenario == "x"
    assert result.strategy == "ex"
```

- [ ] **Step 2: Run — expect ImportError**

```bash
PYTHONPATH=. pytest nous/harness/tests/test_run.py -v
```

- [ ] **Step 3: Write `nous/harness/run.py`**

```python
"""Harness CLI: orchestrate one strategy across all scenarios.

    python -m nous.harness.run \
        --scenarios nous/scenarios.json \
        --strategy nous/harness/strategies/<name>.py \
        --m-min 1 --m-max 256 \
        --out nous/results/<arm>.json

For each scenario it spawns the Go analyzer once, runs the strategy,
records (calls, M_chosen, throughput, gap), kills the analyzer, and
writes one JSON file containing a list of records.
"""

from __future__ import annotations
import argparse
import importlib.util
import json
import time
from pathlib import Path
from typing import Callable

from nous.harness.oracle import make_oracle
from nous.harness.scenarios import Scenario, load_campaign
from nous.harness.scoring import ScenarioResult, compute_gap
from nous.harness.server import AnalyzerServer


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_strategy(path: str | Path) -> Callable[[Callable[[int], dict], int, int], int]:
    """Import a Python file by path and return its `search` callable."""
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(f"strategy_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "search"):
        raise AttributeError(f"{path} must define a top-level `search(target_eval, m_min, m_max) -> int`")
    return module.search


def load_truth_for(scenario_name: str, cache_dir: Path) -> dict:
    fp = cache_dir / f"truth-{scenario_name}.json"
    if not fp.exists():
        raise FileNotFoundError(
            f"missing truth cache {fp}; run baseline_truth.py first"
        )
    return json.loads(fp.read_text())


def run_strategy_on_scenario(
    *,
    base_url: str,
    scenario: Scenario,
    search: Callable[[Callable[[int], dict], int, int], int],
    m_min: int,
    m_max: int,
    truth: dict,
    strategy_name: str,
    alpha: float = 12.0,
    beta: float = 0.05,
    gamma: float = 0.0005,
) -> ScenarioResult:
    eval_, stats = make_oracle(base_url, scenario, alpha=alpha, beta=beta, gamma=gamma)
    t0 = time.monotonic()
    m_chosen = int(search(eval_, m_min, m_max))
    elapsed = time.monotonic() - t0
    final = eval_(m_chosen)  # one extra confirmatory call so we record the throughput at chosen M
    throughput_chosen = float(final["throughput"])
    gap = compute_gap(
        m_chosen=m_chosen, throughput_chosen=throughput_chosen,
        m_truth=int(truth["M_truth"]), throughput_truth=float(truth["throughput_truth"]),
    )
    return ScenarioResult(
        scenario=scenario.name,
        strategy=strategy_name,
        M_chosen=m_chosen,
        calls=stats.calls,
        throughput_chosen=throughput_chosen,
        M_truth=int(truth["M_truth"]),
        throughput_truth=float(truth["throughput_truth"]),
        gap_throughput_rel=gap["gap_throughput_rel"],
        gap_M=gap["gap_M"],
        wall_clock_seconds=elapsed,
        internal_solve_calls=0,  # not reported by /target; left at 0 for now
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", required=True, type=Path)
    ap.add_argument("--strategy", required=True, type=Path)
    ap.add_argument("--m-min", type=int, default=None)
    ap.add_argument("--m-max", type=int, default=None)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cache-dir", type=Path, default=REPO_ROOT / "nous" / "cache")
    ap.add_argument("--repo-dir", type=Path, default=REPO_ROOT)
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    config = load_campaign(args.scenarios)
    m_min = args.m_min if args.m_min is not None else config.m_min
    m_max = args.m_max if args.m_max is not None else config.m_max
    search = load_strategy(args.strategy)
    strategy_name = args.strategy.stem

    args.out.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    with AnalyzerServer(repo_dir=args.repo_dir, port=args.port) as base_url:
        for scenario in config.scenarios:
            truth = load_truth_for(scenario.name, args.cache_dir)
            result = run_strategy_on_scenario(
                base_url=base_url, scenario=scenario, search=search,
                m_min=m_min, m_max=m_max, truth=truth,
                strategy_name=strategy_name,
                alpha=config.alpha, beta=config.beta, gamma=config.gamma,
            )
            records.append(result.to_dict())
            print(f"[{scenario.name}] M={result.M_chosen} calls={result.calls} "
                  f"gap_rel={result.gap_throughput_rel:.4f}")
    args.out.write_text(json.dumps(records, indent=2))
    print(f"wrote {len(records)} records to {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
PYTHONPATH=. pytest nous/harness/tests/test_run.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add nous/harness/run.py nous/harness/tests/test_run.py
git commit -m "harness: run.py CLI orchestrating a strategy across scenarios"
```

---

## Task 8: `baseline_truth.py` — populate the truth cache

**Files:**
- Create: `nous/harness/baseline_truth.py`

This is a small CLI that scans `M ∈ [m_min, m_max]` for each scenario and writes one cache file per scenario. It reuses `server.py`, `oracle.py`, `scenarios.py`. No new behaviors; minimal tests (it's tiny enough that the e2e smoke covers it).

- [ ] **Step 1: Write `nous/harness/baseline_truth.py`**

```python
"""One-time brute-force scan to compute M* and f(M*) per scenario.

Writes <cache-dir>/truth-<name>.json:
    {"scenario": "...", "M_truth": ..., "throughput_truth": ...,
     "f_curve": [{"m": 1, "throughput": ...}, ...]}

Re-run only when scenarios.json changes.
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path

from nous.harness.oracle import make_oracle
from nous.harness.scenarios import load_campaign
from nous.harness.server import AnalyzerServer


REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=Path, default=REPO_ROOT / "nous" / "scenarios.json")
    ap.add_argument("--cache-dir", type=Path, default=REPO_ROOT / "nous" / "cache")
    ap.add_argument("--repo-dir", type=Path, default=REPO_ROOT)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--m-min", type=int, default=None)
    ap.add_argument("--m-max", type=int, default=None)
    args = ap.parse_args()

    config = load_campaign(args.scenarios)
    m_min = args.m_min if args.m_min is not None else config.m_min
    m_max = args.m_max if args.m_max is not None else config.m_max
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    with AnalyzerServer(repo_dir=args.repo_dir, port=args.port) as base_url:
        for s in config.scenarios:
            eval_, stats = make_oracle(
                base_url, s, alpha=config.alpha, beta=config.beta, gamma=config.gamma,
            )
            curve = []
            best_m, best_t = m_min, -1.0
            for m in range(m_min, m_max + 1):
                out = eval_(m)
                t = float(out["throughput"])
                curve.append({"m": m, "throughput": t})
                if t > best_t:
                    best_t, best_m = t, m
            payload = {
                "scenario": s.name,
                "M_truth": best_m,
                "throughput_truth": best_t,
                "f_curve": curve,
            }
            (args.cache_dir / f"truth-{s.name}.json").write_text(json.dumps(payload, indent=2))
            print(f"[{s.name}] M*={best_m} f*={best_t:.4f}  (calls={stats.calls})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it (this is the one-time scan; ~1024 /target calls)**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
source nous/.venv/bin/activate
PYTHONPATH=. python -m nous.harness.baseline_truth
```

Expected: prints one line per scenario with M* and f*, and creates four files under `nous/cache/`. May take a few minutes.

- [ ] **Step 3: Sanity-check the cache**

```bash
ls nous/cache/
cat nous/cache/truth-baseline.json | python -m json.tool | head -10
```

Expected: 4 truth-*.json files; baseline shows `M_truth` somewhere in the interior of [1, 256] with a positive `throughput_truth`. If `M_truth == 1` or `M_truth == 256`, flag that as a possible regime issue (the optimum is at the boundary) — see Task 11 pre-flight notes.

- [ ] **Step 4: Commit**

```bash
git add nous/harness/baseline_truth.py
git commit -m "harness: baseline_truth.py one-time brute-force scan"
```

(Cache files stay gitignored — Task 1 added `nous/cache/`.)

---

## Task 9: `description.txt` — the planner's full brief

**Files:**
- Create: `nous/description.txt`

The brief is **load-bearing**: the planner reads it from inside the worktree. It must be self-contained — the planner cannot reference further files except those inside the queue-analysis repo.

- [ ] **Step 1: Write `nous/description.txt`**

```text
Background

queue-analysis is a Go REST server that solves a state-dependent Markovian queueing
model of a vLLM inference server (see pkg/queue/mm1modelstatedependent.go,
pkg/service/analyzer.go). Two HTTP endpoints on :8080:

  POST /solve   — analyze the queue at a given (RPS, MaxBatchSize, ...) and return
                  Throughput, AvgITL, AvgTTFT, AvgRespTime, MaxRPS, etc.
  POST /target  — given (MaxBatchSize, AvgInputTokens, AvgOutputTokens, alpha, beta,
                  gamma, MaxQueueSize, TargetTTFT, TargetITL), return the maximum RPS
                  that satisfies AvgITL <= TargetITL and AvgTTFT <= TargetTTFT. The
                  returned RPS is in the "throughput" field of the response.

Schemas: examples/problem-data.json (input), examples/solution-target.json (output).

Problem definition

For fixed inputs (alpha, beta, gamma, AvgInputTokens, AvgOutputTokens, MaxQueueSize,
TargetITL, TargetTTFT), define

    f(M) = throughput returned by /target when maxBatchSize = M.

Find  M* = argmax_{M in [M_min, M_max]} f(M).

A single /target call evaluates f at one M. The meta-algorithm searches over M.
Fixed for this campaign:  M_min = 1, M_max = 256.  alpha = 12, beta = 0.05,
gamma = 0.0005 (from examples/problem-data.json).

Scenarios

The properties and the algorithm must hold across these 4 named scenarios. Canonical
JSON: nous/scenarios.json.

  baseline          AvgIn=256  AvgOut=512   ITL=20  TTFT=60   QueueSize=128
  short-tight-ttft  AvgIn=128  AvgOut=256   ITL=20  TTFT=35   QueueSize=128
  long-loose-itl    AvgIn=256  AvgOut=1024  ITL=40  TTFT=200  QueueSize=128
  small-queue       AvgIn=256  AvgOut=512   ITL=20  TTFT=60   QueueSize=4

Harness contract

The harness lives at nous/harness/. Strategies (candidate algorithms) are Python
files under nous/harness/strategies/. Every strategy exposes:

    def search(target_eval, m_min: int, m_max: int) -> int

target_eval(m) returns the parsed AnalysisData JSON for that maxBatchSize and
counts the call. The strategy cannot bypass the wrapper.

CLI:
    python -m nous.harness.run \
        --scenarios nous/scenarios.json \
        --strategy nous/harness/strategies/<name>.py \
        --out <results-path>.json

Outputs one record per scenario:
  M_chosen, calls, throughput_chosen, M_truth, throughput_truth,
  gap_throughput_rel, gap_M, wall_clock_seconds, internal_solve_calls.

Pareto axes and scoring

  calls               number of /target calls the strategy made (lower is better)
  gap_throughput_rel  (truth - chosen) / truth  (>= 0; lower is better)
  gap_M               |M_chosen - M_truth|      (reported, not the primary axis;
                                                 plateaus make a large gap_M benign)

Aggregate across scenarios as both worst-case (max) and mean. Worst-case is the
primary comparison. Strategy A Pareto-dominates B iff worst-case A is no worse on
both (calls, gap_throughput_rel) and strictly better on at least one.

Truth cache: nous/cache/truth-<scenario>.json (already populated by
nous/harness/baseline_truth.py — do NOT re-run unless scenarios.json changes).
The truth cache also contains the full f-curve for each scenario, useful for
property discovery in iter 1.

Stage plan

The campaign is staged. Stay within the current iteration's stage; reject design
gates that drift.

  Iter 1: Single-scenario shape characterization (use baseline). Observe-mode
          (no code_changes) — the harness already provides the f-curve in the
          truth cache. Hypotheses about unimodality, monotonicity, peak existence.
  Iter 2: Local shape near the peak. Concavity, plateau width. h-robustness across
          all 4 scenarios. h-ablation across {ITL-target, TTFT-target} drivers.
  Iter 3: Predicting M* from inputs. Closed-form predictor in {AvgOutputTokens,
          TargetITL, TargetTTFT, beta, gamma}. Test predictor accuracy across
          all 4 scenarios.
  Iter 4: First algorithm justified by Stage 1 properties. code_changes adds
          nous/harness/strategies/alg1.py implementing the algorithm. Predict
          worst-case calls and gap_throughput_rel; verify by running run.py.
  Iter 5: Algorithm-2 vs Algorithm-1 (Pareto comparison). code_changes adds
          alg2.py. Compare on (worst-case calls, worst-case gap).

Out of scope

  - Changes to the Go analyzer code (only nous/harness/* and nous/strategies/*).
  - Sweeping alpha/beta/gamma or adding scenarios beyond the 4 named.
  - Online/streaming variants of the algorithm.
```

- [ ] **Step 2: Verify the file is reachable from a fresh worktree**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git worktree add /tmp/qa-preflight HEAD
cat /tmp/qa-preflight/nous/description.txt | head -10
git worktree remove /tmp/qa-preflight
```

Wait — at this point, `description.txt` is uncommitted, so it won't appear in the worktree. Commit it first; the worktree check belongs in Task 11 after all NOUS files are committed.

- [ ] **Step 3: Commit**

```bash
git add nous/description.txt
git commit -m "nous: planner brief (load-bearing — read from worktree)"
```

---

## Task 10: `campaign.yaml`

**Files:**
- Create: `nous/campaign.yaml`

- [ ] **Step 1: Write `nous/campaign.yaml`**

```yaml
research_question: >
  Find structural properties of f(M) = max-RPS-meeting-targets as a function of
  MaxBatchSize M, then design an algorithm that finds argmax_M f with few /target
  calls. Treat /target as the black-box oracle. Score on two axes: (a) number of
  /target calls, (b) gap_throughput_rel = (truth - chosen) / truth. Pareto compare.

  Stage plan: iter 1-3 discover properties (unimodality, local concavity / plateau,
  closed-form predictor for M* from inputs); iter 4-5 propose and compare algorithms
  in nous/harness/strategies/. Use the harness in nous/harness/run.py — strategies
  must implement search(target_eval, m_min, m_max) -> int; the harness counts calls.

  For the full brief — scenarios, harness contract, Pareto axes, scoring rules,
  stage-by-stage iteration plan — read nous/description.txt in this repository.

run_id: queue-throughput

max_iterations: 5

target_system:
  name: "queue-analysis"
  description: >
    Go REST server (main.go) that solves a state-dependent Markovian queueing model
    of a vLLM inference server. Two endpoints on :8080:
      - /solve  : analyze the queue at a given (RPS, MaxBatchSize, ...) and return
                  Throughput, AvgITL, AvgTTFT, etc.
      - /target : find the maximum RPS that satisfies AvgITL <= TargetITL and
                  AvgTTFT <= TargetTTFT for a given MaxBatchSize, returning that
                  RPS as Throughput.
    See examples/problem-data.json (input) and examples/solution-target.json
    (output) for the schemas.
  observable_metrics:
    - throughput
    - avgITL
    - avgTTFT
    - calls_to_target_per_search
    - gap_throughput_rel
  controllable_knobs:
    - MaxBatchSize
    - search_strategy_in_nous_harness_strategies
  repo_path: /Users/tantawi/Projects/llm-inferno/queue-analysis

prompts:
  methodology_layer: "prompts/methodology"
  domain_adapter_layer: null
```

- [ ] **Step 2: Validate against NOUS schema**

```bash
cd ~/Projects/nous/agentic-strategy-evolution
python -c "
import yaml, jsonschema
schema = yaml.safe_load(open('orchestrator/schemas/campaign.schema.yaml'))
data   = yaml.safe_load(open('/Users/tantawi/Projects/llm-inferno/queue-analysis/nous/campaign.yaml'))
jsonschema.validate(data, schema)
print('OK')
"
```

Expected: `OK`. If schema validation fails, fix the campaign.yaml inline.

- [ ] **Step 3: Commit (from queue-analysis dir)**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add nous/campaign.yaml
git commit -m "nous: campaign config (Pareto axes, 5-iter stage plan)"
```

---

## Task 11: Pre-flight checks

**Files:** none created — this task is a sequence of sanity checks. If any fail, the campaign will burn iterations on plumbing instead of science.

- [ ] **Step 1: Build cache check (already populated)**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
ls nous/cache/truth-*.json | wc -l
```

Expected: `4`. If not, re-run Task 8.

- [ ] **Step 2: Run full test suite**

```bash
source nous/.venv/bin/activate
PYTHONPATH=. pytest nous/harness/tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Smoke E2E with the example strategy**

```bash
PYTHONPATH=. python -m nous.harness.run \
  --scenarios nous/scenarios.json \
  --strategy nous/harness/strategies/example_linear_scan.py \
  --m-min 1 --m-max 16 \
  --out /tmp/smoke.json
cat /tmp/smoke.json | python -m json.tool | head -40
```

Expected: 4 records. Each has `calls == 17` (16 search calls + 1 confirmation), `M_chosen` somewhere in [1, 16], and a non-negative `gap_throughput_rel`. Don't worry that the gap is large — search range is artificially small.

- [ ] **Step 4: Verify description.txt and campaign.yaml are committed and worktree-readable**

```bash
git worktree add /tmp/qa-preflight HEAD
cat /tmp/qa-preflight/nous/description.txt | head -10
test -f /tmp/qa-preflight/nous/campaign.yaml && echo "campaign.yaml present"
git worktree remove /tmp/qa-preflight
```

Expected: first ten lines of description.txt print, and `campaign.yaml present`.

- [ ] **Step 5: Verify NOUS CLI is installed and reachable**

```bash
nous --version || echo "NOUS not installed"
nous validate design --help 2>&1 | head -3
```

Expected: a version string; `validate` subcommand help is reachable.

- [ ] **Step 6: Verify `claude` CLI is authenticated (NOUS uses `claude -p`)**

```bash
claude --version
```

Expected: a version string. If not installed/authenticated, NOUS will fail at iter 1 DESIGN.

- [ ] **Step 7: (Optional) Set OpenAI-compatible env vars for gate summaries**

```bash
echo "OPENAI_API_KEY set: ${OPENAI_API_KEY:+yes}"
echo "OPENAI_BASE_URL: ${OPENAI_BASE_URL:-unset}"
```

Note: gate summaries and report generation are skipped if not set; the campaign still runs. This is non-fatal.

- [ ] **Step 8: Boundary check on truth cache**

```bash
for f in nous/cache/truth-*.json; do
  python -c "
import json, sys
d = json.load(open('$f'))
print(f\"{d['scenario']}: M*={d['M_truth']}  f*={d['throughput_truth']:.4f}\")
"
done
```

Expected: each scenario has an interior M* (not 1 and not the M-max boundary). If a scenario has M* == 1 or M* == M_max, the optimum is at the boundary — the iter-1 unimodality hypothesis may need rephrasing. Note this for the design-gate review of iter 1.

---

## Task 12: Launch iteration 1 of the NOUS campaign

This is the operational handoff. From here, NOUS drives the loop.

- [ ] **Step 1: Launch from queue-analysis root**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
nous run nous/campaign.yaml --max-iterations 5 -v
```

Iter 1's DESIGN phase begins. The Planner will explore the repo, read `nous/description.txt`, then write `problem.md`, `bundle.yaml`, `handoff_snapshot.md` to `.nous/queue-throughput/runs/iter-1/`.

- [ ] **Step 2: At the design gate, review `bundle.yaml`**

```bash
cat .nous/queue-throughput/runs/iter-1/bundle.yaml
```

Approve if:
- The bundle is observe-mode (no `code_changes`) — iter 1 is shape characterization.
- H-main is a directional, falsifiable claim about `f(M)`.
- It uses `nous/harness/run.py` or reads the truth cache to obtain the f-curve.

Reject (with reason) if:
- The planner proposes algorithms (that's Stage 2, iter 4+).
- Predictions are non-quantitative.
- It ignores the truth cache and tries to brute-scan independently — wasted compute.

- [ ] **Step 3: Approve, observe execution, then review findings**

```bash
cat .nous/queue-throughput/runs/iter-1/findings.json
cat .nous/queue-throughput/principles.json
```

Approve at the findings gate if the analysis matches the evidence. Then iter 2 begins.

- [ ] **Step 4: Repeat for iters 2–5, steering at each gate per the stage plan in description.txt**

If you need to pause: ctrl-C is safe (NOUS checkpoints to `state.json`). Resume with:

```bash
nous resume nous/campaign.yaml
```

- [ ] **Step 5: When done, generate a report (optional)**

```bash
nous report nous/campaign.yaml > .nous/queue-throughput/report.md
```

---

## Self-Review

**Spec coverage:**
- Spec §3 (4 scenarios) → Task 2.
- Spec §4.1 (file layout) → Task 1 (scaffold) + downstream tasks (each adds files in the layout).
- Spec §4.2 (strategy contract) → Task 6 (example) + documented in description.txt (Task 9).
- Spec §4.3 (harness CLI) → Task 7.
- Spec §4.4 (truth baseline) → Task 8.
- Spec §5 (Pareto axes) → Task 5 (formulas) + description.txt (Task 9).
- Spec §6 (5-iter stage plan) → Task 9 (description.txt) + Task 10 (campaign.yaml `research_question`).
- Spec §7.1 (campaign.yaml content) → Task 10.
- Spec §7.2 (description.txt content) → Task 9.
- Spec §8 (worktree-reachable description) → Task 9 + Task 11 step 4.
- Spec §9 (pre-flight checks) → Task 11.
- Spec §10 (how to launch) → Task 12.

**Placeholder scan:** No "TBD"/"TODO"/"appropriate"/"similar to". Every code step has full code. Every command step has the exact command and expected output.

**Type consistency:** `Scenario` dataclass fields used consistently across `scenarios.py`, `oracle.py`, `run.py`. `OracleStats` defined in `oracle.py`, used in `run.py` test. `ScenarioResult` defined in `scoring.py`, returned from `run.py`. `compute_gap` keyword args (`m_chosen`, `throughput_chosen`, `m_truth`, `throughput_truth`) consistent between `scoring.py` and the call site in `run.py`.

**One known mismatch is intentional:** `internal_solve_calls=0` is a hardcoded zero in `run.py` step 3. /target does not report it, and the spec says it's "logged for audit, not part of the score". A future task can add it if /solve is also called directly; the field exists in the output schema for forward-compat.
