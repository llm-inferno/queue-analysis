# NOUS Reformulation — Formula-Guided Search Campaign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the NOUS queue-throughput campaign on the corrected analyzer (`99024df`): hand NOUS the analytic ITL/TTFT/τ primitives as an importable module, sweep (α, β, γ) per scenario, and run a 5-iteration campaign that derives a parameter-generic predictor M̂(params) and a formula-guided search that Pareto-dominates a parameter-blind baseline.

**Architecture:** Two halves. **(A) Harness preparation** — deterministic, code-bearing, TDD: a new `formulas.py` (Python port of the analyzer's service-time primitives, parity-checked against the Go source), a per-scenario (α,β,γ,regime) scenario schema, a widened `search(target_eval, params, m_min, m_max)` strategy contract, an LHS benchmark generator, staged truth-cache regeneration, and a rewritten NOUS brief. **(B) Campaign execution** — five NOUS iterations (3 observe, 2 code_changes), each with an explicit gate from spec §8.1, reviewed with the user before proceeding.

**Tech Stack:** Python 3.12 (`numpy`, `scipy` for LHS, `requests`), the existing Go `queue-analysis` REST server (`/target`), `pytest` for harness tests, NOUS (`agentic-strategy-evolution`) for the campaign loop.

**Source documents:**
- Spec: `docs/superpowers/specs/2026-06-11-nous-reformulation-design.md`
- Analyzer primitives: `pkg/analyzer/queueanalyzer.go:275-394`, `pkg/analyzer/utils.go:8-47`
- Harness contract: `nous/harness/{scenarios,oracle,run,scoring,baseline_truth}.py`, `nous/harness/strategies/`
- Superseded campaign: `docs/superpowers/specs/2026-06-09-nous-throughput-campaign-design.md`
- NOUS install/run: follow the `reference_nous_install` memory (editable in `nous/.venv`; source before `nous run`)

**Resolved design decisions (spec §11):**
1. **Branch:** new `nous-formula-campaign` off `main`.
2. **`formulas.py` visibility:** importable module (NOUS imports it; still shows its derivation in iter 1).
3. **Truth caches:** staged — dev (6) first, validate, then benchmark (~30).
4. **Baseline cohort:** keep all prior strategies (retrofit all 8 to accept-and-ignore `params`).

---

## Canonical contracts (read before any task)

These types/signatures are referenced across tasks. Keep them identical everywhere.

**`Scenario` dataclass fields** (`nous/harness/scenarios.py`):
`name, avg_input_tokens, avg_output_tokens, target_itl, target_ttft, max_queue_size, alpha, beta, gamma, regime`

**`ALLOWED_FIELDS`** (scenario JSON keys):
`{"name", "AvgInputTokens", "AvgOutputTokens", "targetITL", "targetTTFT", "maxQueueSize", "alpha", "beta", "gamma", "regime"}`

**`params` dict** (built by the harness, passed to every strategy and usable by `formulas.py`):
```python
{"alpha", "beta", "gamma", "AvgInputTokens", "AvgOutputTokens",
 "targetITL", "targetTTFT", "maxQueueSize"}
```
(No `regime` — regime is metadata, not a strategy input. No `maxNumTokens` — `formulas.py` uses the constant `MAX_NUM_TOKENS = 8192`, matching the analyzer's `DefaultMaxNumTokens`.)

**Strategy signature** (widened):
```python
def search(target_eval: Callable[[int], dict], params: dict, m_min: int, m_max: int) -> int
```

**`formulas.py` public functions** (each takes `(B: int, params: dict)`):
`num_iterations_per_prefill(B, params) -> int`, `delta(B, params) -> float`, `itl(B, params) -> float`, `ttft_prefill(B, params) -> float`, `tau(B, params) -> float`

**Cache layout:** dev → `nous/cache/truth-<name>.json`; benchmark → `nous/cache/bench/<idx>.json`.

**Analyzer primitives being ported** (from `queueanalyzer.go`, all at a given batch size `B` with chunk count `nc`):
```
wPrefill = (β + γ·(nc+1)/2)·n                       # n = AvgInputTokens
wDecode  = β·m + γ·m·(n + (m+1)/2)                   # m = AvgOutputTokens
wTotal   = wPrefill + wDecode
delta    = wTotal / (nc + m)
tIter(B) = α + B·delta
tau(B)   = (nc + m)·tIter(B)
bg(B)    = max(0, α + (B-1)·delta)
prefill(B) = nc·bg(B) + wPrefill
itl(B)   = bg(B) + β + γ·(n + (m+1)/2)
```
`nc` comes from `NumIterationsPerPrefill` (`utils.go:40`), which depends on `MaxNumTokens=8192`.

---

## Phase 0 — Branch

### Task 0: Create the campaign branch

**Files:** none (git only)

- [ ] **Step 1: Confirm clean tree and branch off main**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git status --short        # only docs/references/ untracked expected
git fetch origin
git checkout -b nous-formula-campaign origin/main
```
Expected: new branch `nous-formula-campaign` tracking `origin/main`.

If `origin/main` is unavailable, branch off local `main`: `git checkout -b nous-formula-campaign main`.

- [ ] **Step 2: Copy the spec + this plan onto the branch** (they live on `paper-analysis-section`)

```bash
git checkout paper-analysis-section -- docs/superpowers/specs/2026-06-11-nous-reformulation-design.md docs/superpowers/plans/2026-06-11-nous-reformulation-campaign.md
git add docs/superpowers/
git commit -m "docs: carry NOUS reformulation spec + plan onto campaign branch"
```
Expected: spec and plan present on the new branch.

---

## Phase 1 — `formulas.py` + Go parity fixture

### Task 1: Generate a Go parity golden fixture

**Files:**
- Create: `nous/harness/parity/dump_primitives.go`
- Create (output): `nous/harness/tests/golden_primitives.json`

**Why:** `formulas.py` is a hand port of unexported Go functions. We can't call the unexported `itlNew`/`tauNew`/`delta` directly, but we CAN call the exported shims `IterationTime`/`PrefillTime`/`DecodeTime` (which hit the same arithmetic at `nc=1`) and the exported `NumIterationsPerPrefill` (which validates the `nc` table exactly for all `nc`). The golden file pins both so the Python port is checked against the Go source, not against itself. This is a test fixture, not an analyzer change (spec §6.6 forbids changing `pkg/analyzer/`, not adding read-only fixtures).

- [ ] **Step 1: Inspect the exported shim signatures and `Configuration`/`RequestSize`/`ServiceParms` structs**

```bash
sed -n '1,60p' /Users/tantawi/Projects/llm-inferno/queue-analysis/pkg/analyzer/queueanalyzer.go
grep -n "type Configuration\|type RequestSize\|type ServiceParms\|Alpha\|Beta\|Gamma\|AvgInputTokens\|AvgOutputTokens\|MaxNumTokens\|MaxBatchSize" /Users/tantawi/Projects/llm-inferno/queue-analysis/pkg/analyzer/*.go | head -40
```
Confirm field names and the module path (`head -1 go.mod`) before writing the Go file. Adjust the import path in Step 2 to match `go.mod`.

- [ ] **Step 2: Write `nous/harness/parity/dump_primitives.go`**

```go
// Command dump_primitives emits analyzer service-time primitives for a fixed
// set of (B, params) tuples so the Python port in nous/harness/formulas.py can
// be parity-checked. Read-only: imports the analyzer package, calls only
// exported methods. Run with `go run ./nous/harness/parity`.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	// IMPORTANT: replace with the module path from go.mod (Step 1).
	"github.com/llm-inferno/queue-analysis/pkg/analyzer"
)

type tuple struct {
	B      int     `json:"B"`
	Alpha  float32 `json:"alpha"`
	Beta   float32 `json:"beta"`
	Gamma  float32 `json:"gamma"`
	NIn    int     `json:"AvgInputTokens"`
	MOut   int     `json:"AvgOutputTokens"`
}

type record struct {
	tuple
	Nc        int     `json:"nc"`
	IterTime  float32 `json:"iter_time"`   // IterationTime(B), nc=1
	Prefill   float32 `json:"prefill"`     // PrefillTime(B),   nc=1
	Itl       float32 `json:"itl"`         // DecodeTime(B),    nc=1
}

func main() {
	tuples := []tuple{
		{B: 1, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 256, MOut: 1024},
		{B: 40, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 256, MOut: 1024},
		{B: 80, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 256, MOut: 1024},
		{B: 128, Alpha: 16, Beta: 0.067, Gamma: 0.000667, NIn: 256, MOut: 1024},
		{B: 200, Alpha: 4, Beta: 0.017, Gamma: 0.000167, NIn: 64, MOut: 128},
		{B: 50, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 1024, MOut: 256},
	}
	out := make([]record, 0, len(tuples))
	for _, t := range tuples {
		sp := &analyzer.ServiceParms{Alpha: t.Alpha, Beta: t.Beta, Gamma: t.Gamma}
		rs := &analyzer.RequestSize{
			AvgInputTokens:  float32(t.NIn),
			AvgOutputTokens: float32(t.MOut),
		}
		cfg := &analyzer.Configuration{
			MaxBatchSize: t.B, MaxQueueSize: 128, MaxNumTokens: 8192, ServiceParms: sp,
		}
		ncTable := analyzer.NumIterationsPerPrefill(cfg, rs)
		nc := ncTable[t.B]
		B := float32(t.B)
		out = append(out, record{
			tuple:    t,
			Nc:       nc,
			IterTime: sp.IterationTime(rs, B),
			Prefill:  sp.PrefillTime(rs, B),
			Itl:      sp.DecodeTime(rs, B),
		})
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(out); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
```

**Note:** field names (`ServiceParms.Alpha`, `RequestSize.AvgInputTokens`, `Configuration.MaxNumTokens`) MUST match Step 1's inspection. If a struct uses different capitalization or requires a constructor, adapt. If `IterationTime`/`PrefillTime`/`DecodeTime` are unexported, fall back to whatever exported accessor returns the same value (re-inspect `queueanalyzer.go:337-350`).

- [ ] **Step 3: Generate the golden file**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
go run ./nous/harness/parity > nous/harness/tests/golden_primitives.json
cat nous/harness/tests/golden_primitives.json
```
Expected: a JSON array of 6 records, each with integer `nc ≥ 1` and positive `iter_time`, `prefill`, `itl`. If `go run` fails on the import path, fix it from `go.mod` and retry.

- [ ] **Step 4: Commit**

```bash
git add nous/harness/parity/dump_primitives.go nous/harness/tests/golden_primitives.json
git commit -m "nous: Go parity fixture for formulas.py port"
```

---

### Task 2: Implement `formulas.py` against the golden fixture (TDD)

**Files:**
- Create: `nous/harness/formulas.py`
- Test: `nous/harness/tests/test_formulas.py`

- [ ] **Step 1: Write the failing test**

```python
"""Parity + unit tests for the analyzer-primitive port in formulas.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nous.harness import formulas

GOLDEN = Path(__file__).parent / "golden_primitives.json"
REL_TOL = 1e-4  # float32 round-trip tolerance


def _params(rec: dict) -> dict:
    return {
        "alpha": rec["alpha"], "beta": rec["beta"], "gamma": rec["gamma"],
        "AvgInputTokens": rec["AvgInputTokens"],
        "AvgOutputTokens": rec["AvgOutputTokens"],
        "targetITL": 20.0, "targetTTFT": 60.0, "maxQueueSize": 128,
    }


@pytest.fixture(scope="module")
def golden() -> list[dict]:
    return json.loads(GOLDEN.read_text())


def test_nc_matches_go(golden):
    for rec in golden:
        got = formulas.num_iterations_per_prefill(rec["B"], _params(rec))
        assert got == rec["nc"], f"nc B={rec['B']}: py={got} go={rec['nc']}"


def test_itl_matches_go_at_nc1(golden):
    # Go shims (IterationTime/PrefillTime/DecodeTime) use nc=1; compare only
    # the tuples whose true nc is 1, where the formula reduces identically.
    for rec in golden:
        if rec["nc"] != 1:
            continue
        got = formulas.itl(rec["B"], _params(rec))
        assert got == pytest.approx(rec["itl"], rel=REL_TOL)


def test_decode_slope_is_affine_in_target():
    # n_ITL inversion in §3.5 relies on itl(B) being affine in B: itl = a + b*B.
    p = {"alpha": 8.0, "beta": 0.033, "gamma": 0.000333,
         "AvgInputTokens": 256, "AvgOutputTokens": 1024,
         "targetITL": 20.0, "targetTTFT": 60.0, "maxQueueSize": 128}
    i10, i20, i30 = (formulas.itl(b, p) for b in (10, 20, 30))
    assert (i20 - i10) == pytest.approx(i30 - i20, rel=1e-6)


def test_tau_positive_and_monotone():
    p = {"alpha": 8.0, "beta": 0.033, "gamma": 0.000333,
         "AvgInputTokens": 256, "AvgOutputTokens": 1024,
         "targetITL": 20.0, "targetTTFT": 60.0, "maxQueueSize": 128}
    taus = [formulas.tau(b, p) for b in range(1, 64)]
    assert all(t > 0 for t in taus)
    assert taus == sorted(taus), "tau should increase in B"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
source nous/.venv/bin/activate   # per reference_nous_install memory
python -m pytest nous/harness/tests/test_formulas.py -q
```
Expected: FAIL — `ModuleNotFoundError: nous.harness.formulas`.

- [ ] **Step 3: Write `nous/harness/formulas.py`**

```python
"""Analytic service-time primitives for the queue-analysis model.

A faithful Python port of the unexported primitives in
pkg/analyzer/queueanalyzer.go:275-327 and the chunk-count logic in
pkg/analyzer/utils.go:8-47. This module is the single source of truth for the
formulas NOUS reasons about; it is parity-checked against the Go source by
tests/test_formulas.py (golden_primitives.json).

All functions take a batch size B (int) and a params dict with keys:
    alpha, beta, gamma, AvgInputTokens, AvgOutputTokens,
    targetITL, targetTTFT, maxQueueSize

The chunk budget MaxNumTokens is fixed at 8192 (analyzer DefaultMaxNumTokens);
it is NOT a params key because the /target requests never override it.
"""
from __future__ import annotations

import math

MAX_NUM_TOKENS = 8192  # matches analyzer.DefaultMaxNumTokens


# --- chunk count (port of utils.go) ---------------------------------------

def _max_batch_for_iters(num_iters: int, n_in: float, m_out: float) -> int:
    """Port of CalculateMaxBatchSizeForNumIterationsPerPrefill (utils.go:8)."""
    m = float(num_iters)
    batch = (m + m_out) * (MAX_NUM_TOKENS - n_in / m) / (n_in + m_out)
    return int(math.floor(max(0.0, batch)))


def _batch_sizes(max_batch: int, n_in: float, m_out: float) -> list[int]:
    """Port of CalculateBatchSizes (utils.go:19)."""
    sizes: list[int] = []
    batch = 0
    num_iters = 1
    while batch < max_batch:
        batch = _max_batch_for_iters(num_iters, n_in, m_out)
        sizes.append(batch)
        num_iters += 1
    return sizes


def num_iterations_per_prefill(B: int, params: dict) -> int:
    """nc at batch size B (treating maxBatchSize = B, per spec §3.1 B=M).

    Port of NumIterationsPerPrefillForBatchSize over CalculateBatchSizes
    (utils.go:31-47).
    """
    n_in = float(params["AvgInputTokens"])
    m_out = float(params["AvgOutputTokens"])
    sizes = _batch_sizes(B, n_in, m_out)
    for i, bs in enumerate(sizes):
        if bs >= B:
            return i + 1
    return len(sizes)


# --- service-time primitives (port of queueanalyzer.go) -------------------

def _w_prefill(nc: int, params: dict) -> float:
    n = float(params["AvgInputTokens"])
    return (params["beta"] + params["gamma"] * (nc + 1) / 2.0) * n


def _w_decode(params: dict) -> float:
    n = float(params["AvgInputTokens"])
    m = float(params["AvgOutputTokens"])
    return params["beta"] * m + params["gamma"] * m * (n + (m + 1) / 2.0)


def delta(B: int, params: dict) -> float:
    nc = num_iterations_per_prefill(B, params)
    m = float(params["AvgOutputTokens"])
    w_total = _w_prefill(nc, params) + _w_decode(params)
    return w_total / (nc + m)


def _t_iter(B: int, params: dict) -> float:
    return params["alpha"] + B * delta(B, params)


def tau(B: int, params: dict) -> float:
    nc = num_iterations_per_prefill(B, params)
    m = float(params["AvgOutputTokens"])
    return (nc + m) * _t_iter(B, params)


def _bg(B: int, params: dict) -> float:
    return max(0.0, params["alpha"] + (B - 1) * delta(B, params))


def ttft_prefill(B: int, params: dict) -> float:
    """Prefill component of TTFT (queue wait excluded; the M/M/1 solver adds it)."""
    nc = num_iterations_per_prefill(B, params)
    return nc * _bg(B, params) + _w_prefill(nc, params)


def itl(B: int, params: dict) -> float:
    n = float(params["AvgInputTokens"])
    m = float(params["AvgOutputTokens"])
    return _bg(B, params) + params["beta"] + params["gamma"] * (n + (m + 1) / 2.0)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest nous/harness/tests/test_formulas.py -q
```
Expected: PASS (4 tests). If `test_nc_matches_go` fails, the `_batch_sizes` loop or `MAX_NUM_TOKENS` is wrong — recheck `utils.go:19-29`. If `test_itl_matches_go_at_nc1` fails, recheck `_bg`/`_w_*` against `queueanalyzer.go:289-327`.

- [ ] **Step 5: Commit**

```bash
git add nous/harness/formulas.py nous/harness/tests/test_formulas.py
git commit -m "nous: formulas.py — Python port of analyzer primitives, parity-tested"
```

---

## Phase 2 — Per-scenario (α, β, γ, regime) schema

### Task 3: Extend the scenario schema and oracle to per-scenario constants

**Files:**
- Modify: `nous/harness/scenarios.py`
- Modify: `nous/harness/oracle.py`
- Modify: `nous/harness/tests/test_scenarios.py`

**Why:** spec §4 sweeps α/β/γ per scenario, so they move from campaign-level `constants` to per-scenario fields. A `regime` label is added for the iter-5 per-regime breakdown (spec §6.5).

- [ ] **Step 1: Update the schema tests first (failing)**

Replace `nous/harness/tests/test_scenarios.py` entirely:

```python
from pathlib import Path
import json
import pytest
from nous.harness.scenarios import Scenario, load_scenarios, scenario_to_problem


REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIOS_PATH = REPO_ROOT / "nous" / "scenarios.json"


def test_loads_six_dev_scenarios():
    scenarios = load_scenarios(SCENARIOS_PATH)
    assert [s.name for s in scenarios] == [
        "baseline", "itl-only", "ttft-only", "unbounded", "alpha-low", "alpha-high",
    ]


def test_baseline_fields():
    scenarios = load_scenarios(SCENARIOS_PATH)
    s = next(s for s in scenarios if s.name == "baseline")
    assert s.avg_input_tokens == 256
    assert s.avg_output_tokens == 1024
    assert s.target_itl == 20.0
    assert s.target_ttft == 60.0
    assert s.max_queue_size == 128
    assert s.alpha == 8.0
    assert s.regime == "crossover"


def test_scenario_to_problem_uses_per_scenario_constants():
    s = Scenario(
        name="x", avg_input_tokens=100, avg_output_tokens=200,
        target_itl=15.0, target_ttft=50.0, max_queue_size=64,
        alpha=4.0, beta=0.017, gamma=0.000167, regime="crossover",
    )
    payload = scenario_to_problem(s, max_batch_size=24)
    assert payload["maxBatchSize"] == 24
    assert payload["AvgInputTokens"] == 100
    assert payload["alpha"] == 4.0
    assert payload["beta"] == 0.017
    assert payload["gamma"] == 0.000167


def test_load_rejects_unknown_scenario_field(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "search_range": {"m_min": 1, "m_max": 256},
        "scenarios": [{"name": "x", "AvgInputTokens": 100, "AvgOutputTokens": 100,
                       "targetITL": 10.0, "targetTTFT": 30.0, "maxQueueSize": 64,
                       "alpha": 8.0, "beta": 0.033, "gamma": 0.000333,
                       "regime": "crossover", "extraneous": True}]
    }))
    with pytest.raises(ValueError):
        load_scenarios(bad)
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest nous/harness/tests/test_scenarios.py -q
```
Expected: FAIL (Scenario missing `alpha`/`regime`; six-scenario list mismatch — the new scenarios.json doesn't exist yet, written in Task 4).

- [ ] **Step 3: Rewrite `nous/harness/scenarios.py`**

```python
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
```

- [ ] **Step 4: Rewrite `make_oracle` in `nous/harness/oracle.py`** to drop the α/β/γ kwargs (now read from the scenario)

Replace the `make_oracle` signature and body header:

```python
def make_oracle(
    base_url: str,
    scenario: Scenario,
    *,
    timeout: float = 30.0,
) -> tuple[Callable[[int], dict], OracleStats]:
    """Return (target_eval, stats). target_eval(m) posts to /target using the
    scenario's own alpha/beta/gamma. HTTP 400 -> {"throughput": 0.0}, uncounted.
    """
    stats = OracleStats()
    url = f"{base_url}/target"

    def target_eval(m: int) -> dict:
        problem = scenario_to_problem(scenario, m)
        resp = requests.post(url, json=problem, timeout=timeout)
        if resp.status_code == 400:
            return {"throughput": 0.0}
        resp.raise_for_status()
        stats.calls += 1
        return resp.json()

    return target_eval, stats
```

Leave the `OracleStats` dataclass and imports as-is (the `scenario_to_problem` import already exists).

- [ ] **Step 5: Run scenario + oracle tests** (scenarios.json still missing — expect the six-scenario test to fail, others to pass)

```bash
python -m pytest nous/harness/tests/test_scenarios.py nous/harness/tests/test_oracle.py -q
```
Expected: `test_scenario_to_problem_uses_per_scenario_constants`, `test_load_rejects_unknown_scenario_field` PASS; `test_loads_six_dev_scenarios`/`test_baseline_fields` FAIL until Task 4. `test_oracle.py` may need a small edit if it passed `alpha=`/`beta=` to `make_oracle` — if it fails on a `TypeError`, remove those kwargs from the test call.

- [ ] **Step 6: Commit**

```bash
git add nous/harness/scenarios.py nous/harness/oracle.py nous/harness/tests/test_scenarios.py nous/harness/tests/test_oracle.py
git commit -m "nous: per-scenario alpha/beta/gamma + regime; oracle reads scenario constants"
```

---

### Task 4: Write the 6 dev scenarios

**Files:**
- Modify: `nous/scenarios.json` (full rewrite)

- [ ] **Step 1: Replace `nous/scenarios.json`** with the dev set from spec §4.2

```json
{
  "search_range": { "m_min": 1, "m_max": 256 },
  "scenarios": [
    { "name": "baseline", "regime": "crossover",
      "AvgInputTokens": 256, "AvgOutputTokens": 1024,
      "targetITL": 20.0, "targetTTFT": 60.0, "maxQueueSize": 128,
      "alpha": 8.0, "beta": 0.033, "gamma": 0.000333 },
    { "name": "itl-only", "regime": "itl-only",
      "AvgInputTokens": 256, "AvgOutputTokens": 4096,
      "targetITL": 15.0, "targetTTFT": 400.0, "maxQueueSize": 128,
      "alpha": 8.0, "beta": 0.033, "gamma": 0.000333 },
    { "name": "ttft-only", "regime": "ttft-only",
      "AvgInputTokens": 1024, "AvgOutputTokens": 256,
      "targetITL": 60.0, "targetTTFT": 80.0, "maxQueueSize": 128,
      "alpha": 8.0, "beta": 0.033, "gamma": 0.000333 },
    { "name": "unbounded", "regime": "unbounded",
      "AvgInputTokens": 64, "AvgOutputTokens": 128,
      "targetITL": 200.0, "targetTTFT": 2000.0, "maxQueueSize": 4,
      "alpha": 4.0, "beta": 0.017, "gamma": 0.000167 },
    { "name": "alpha-low", "regime": "crossover",
      "AvgInputTokens": 256, "AvgOutputTokens": 1024,
      "targetITL": 20.0, "targetTTFT": 60.0, "maxQueueSize": 128,
      "alpha": 4.0, "beta": 0.017, "gamma": 0.000167 },
    { "name": "alpha-high", "regime": "crossover",
      "AvgInputTokens": 256, "AvgOutputTokens": 1024,
      "targetITL": 20.0, "targetTTFT": 60.0, "maxQueueSize": 128,
      "alpha": 16.0, "beta": 0.067, "gamma": 0.000667 }
  ]
}
```

(β/γ values are α × canonical ratios: α=8→β=.033≈8/240, γ=.000333≈8/24000; α=4→β=.017, γ=.000167; α=16→β=.067, γ=.000667.)

- [ ] **Step 2: Run the scenario tests — now all pass**

```bash
python -m pytest nous/harness/tests/test_scenarios.py -q
```
Expected: PASS (4 tests).

- [ ] **Step 3: Commit**

```bash
git add nous/scenarios.json
git commit -m "nous: 6 regime-spanning dev scenarios on the (alpha,beta,gamma) manifold"
```

---

## Phase 3 — Widened strategy contract

### Task 5: Widen `search()` to `(target_eval, params, m_min, m_max)` and retrofit all strategies

**Files:**
- Modify: `nous/harness/run.py`
- Modify: all 8 files in `nous/harness/strategies/` (signature only)
- Modify: `nous/harness/tests/test_strategies_mock.py`, `nous/harness/tests/test_strategies.py`

- [ ] **Step 1: Update the mock strategy tests first (failing)**

In `nous/harness/tests/test_strategies_mock.py`, every `module.search(target_eval, m_min=..., m_max=...)` call must pass `params`. Add a shared dummy near the top (after imports):

```python
DUMMY_PARAMS = {
    "alpha": 12.0, "beta": 0.05, "gamma": 0.0005,
    "AvgInputTokens": 256, "AvgOutputTokens": 512,
    "targetITL": 20.0, "targetTTFT": 60.0, "maxQueueSize": 128,
}
```

Then change each call site:
- `strategy_module.search(target_eval, m_min=1, m_max=256)` → `strategy_module.search(target_eval, DUMMY_PARAMS, m_min=1, m_max=256)`
- `ratio_binary_search.search(target_eval, m_min=1, m_max=256)` → `ratio_binary_search.search(target_eval, DUMMY_PARAMS, m_min=1, m_max=256)`
- `module.search(target_eval, m_min=1, m_max=256)` (predictor block) → `module.search(target_eval, DUMMY_PARAMS, m_min=1, m_max=256)`

Apply the same `params`-insertion to any `search(` calls in `nous/harness/tests/test_strategies.py`.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest nous/harness/tests/test_strategies_mock.py -q
```
Expected: FAIL — `TypeError: search() got an unexpected keyword argument` / positional mismatch (strategies still have the old signature).

- [ ] **Step 3: Retrofit every strategy signature** (accept-and-ignore `params`)

Edit each file, changing only the `def search` line:

`nous/harness/strategies/adaptive_early_exit.py:16`,
`adaptive_binary.py:17`, `adaptive_interpolation.py:25`,
`example_linear_scan.py:11`, `predictor_hybrid.py:55`,
`predictor_direct.py:33`, `predictor_naive.py:28`,
`ratio_binary_search.py:15`:

```python
def search(target_eval: Callable[[int], dict], params: dict, m_min: int, m_max: int) -> int:
```

(Body unchanged; `params` is intentionally unused in the baseline cohort — these stay parameter-blind, which is exactly what iter 5 measures against `formula_guided`.) Add a one-line docstring note at the top of each `search` body is NOT required; the signature change is enough.

- [ ] **Step 4: Update `run.py` to build and pass `params`**

In `nous/harness/run.py`:

(a) Update the `load_strategy` type hints and the `hasattr` error message:

```python
def load_strategy(path: str | Path) -> Callable[[Callable[[int], dict], dict, int, int], int]:
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(f"strategy_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "search"):
        raise AttributeError(
            f"{path} must define `search(target_eval, params, m_min, m_max) -> int`")
    return module.search
```

(b) Update `run_strategy_on_scenario`: drop the α/β/γ kwargs, build `params`, pass it to `search` and `make_oracle`:

```python
from nous.harness.scenarios import Scenario, load_campaign, scenario_to_params
# ... inside run_strategy_on_scenario, replace the signature's alpha/beta/gamma
#     kwargs (remove them) and the body header:

    eval_, stats = make_oracle(base_url, scenario)
    params = scenario_to_params(scenario)
    t0 = time.monotonic()
    m_chosen = int(search(eval_, params, m_min, m_max))
```

(c) In `main`, the `make_oracle`/`run_strategy_on_scenario` calls no longer pass `config.alpha` etc. — remove those kwargs:

```python
            result = run_strategy_on_scenario(
                base_url=base_url, scenario=scenario, search=search,
                m_min=m_min, m_max=m_max, truth=truth,
                strategy_name=strategy_name,
            )
```

Also update the `search` type annotation on `run_strategy_on_scenario`'s parameter to `Callable[[Callable[[int], dict], dict, int, int], int]`.

- [ ] **Step 5: Run the full harness test suite**

```bash
python -m pytest nous/harness/tests/ -q
```
Expected: PASS. If `test_run.py` constructs `make_oracle(... alpha=)` or calls `run_strategy_on_scenario(... alpha=)`, remove those kwargs there too. If a predictor mock test now fails because `predict_m_est` uses stale constants against the synthetic scenario, that's acceptable only if the assertion was about exact M_est — re-read the failure; the synthetic scenario in the test still uses α=12 constants, so it should still pass.

- [ ] **Step 6: Commit**

```bash
git add nous/harness/run.py nous/harness/strategies/ nous/harness/tests/
git commit -m "nous: widen search() to (target_eval, params, m_min, m_max); retrofit baseline cohort"
```

---

## Phase 4 — Benchmark grid

### Task 6: LHS benchmark generator

**Files:**
- Create: `nous/harness/scenarios_benchmark.py`
- Test: `nous/harness/tests/test_scenarios_benchmark.py`
- Create (output): `nous/scenarios_benchmark.json`

- [ ] **Step 1: Confirm `scipy` availability** (LHS sampler)

```bash
python -c "from scipy.stats import qmc; print('scipy qmc ok')" || pip install scipy
```
If installed via `pip`, add `scipy>=1.11` to `nous/requirements.txt`.

- [ ] **Step 2: Write the failing test**

```python
"""Determinism + manifold tests for the benchmark generator."""
from __future__ import annotations

import json

from nous.harness.scenarios import ALLOWED_FIELDS
from nous.harness.scenarios_benchmark import generate


def test_deterministic_for_seed():
    a = generate(n=30, seed=42)
    b = generate(n=30, seed=42)
    assert a == b


def test_count_and_indexing():
    recs = generate(n=30, seed=42)
    assert len(recs) == 30
    assert recs[0]["name"] == "bench-000"
    assert recs[29]["name"] == "bench-029"
    assert all(r["regime"] == "bench" for r in recs)


def test_only_allowed_fields():
    for r in generate(n=5, seed=42):
        assert set(r) <= ALLOWED_FIELDS


def test_ratio_manifold_preserved():
    # beta = alpha * (beta/alpha-sample); ratios must stay in the §4.1 envelope.
    for r in generate(n=30, seed=42):
        assert 1 / 500 <= r["beta"] / r["alpha"] <= 1 / 100
        assert 1 / 50000 <= r["gamma"] / r["alpha"] <= 1 / 10000
```

- [ ] **Step 3: Run to verify failure**

```bash
python -m pytest nous/harness/tests/test_scenarios_benchmark.py -q
```
Expected: FAIL — `ModuleNotFoundError: nous.harness.scenarios_benchmark`.

- [ ] **Step 4: Write `nous/harness/scenarios_benchmark.py`**

```python
"""Generate the benchmark grid as a Latin-hypercube sample over the §4.1 ranges.

beta and gamma are reconstructed on the realistic-ratio manifold:
    beta  = alpha * (beta/alpha sample)
    gamma = alpha * (gamma/alpha sample)
so reproducibility is a function of (ranges, sampler, seed=42), not a hand list.

    python -m nous.harness.scenarios_benchmark --n 30 --seed 42 \
        --out nous/scenarios_benchmark.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scipy.stats import qmc

REPO_ROOT = Path(__file__).resolve().parents[2]

# Discrete choice sets from spec §4.1.
ALPHA = [4.0, 8.0, 16.0]
BETA_RATIO = [1 / 400, 1 / 240, 1 / 120]
GAMMA_RATIO = [1 / 40000, 1 / 24000, 1 / 12000]
L_IN = [64, 256, 1024, 4096]
L_OUT = [64, 256, 1024, 4096]
T_ITL = [15.0, 20.0, 30.0, 40.0, 60.0]
T_TTFT = [30.0, 60.0, 120.0, 200.0, 400.0]
Q = [4, 32, 128]

# Order of the 8 LHS dimensions; each maps a unit-interval sample to an index
# into the choice set above.
_DIMS = [ALPHA, BETA_RATIO, GAMMA_RATIO, L_IN, L_OUT, T_ITL, T_TTFT, Q]


def _pick(choices: list, u: float) -> object:
    """Map u in [0,1) to a choice index."""
    idx = min(int(u * len(choices)), len(choices) - 1)
    return choices[idx]


def generate(n: int = 30, seed: int = 42) -> list[dict]:
    sampler = qmc.LatinHypercube(d=len(_DIMS), seed=seed)
    sample = sampler.random(n=n)
    recs: list[dict] = []
    for i, row in enumerate(sample):
        alpha = _pick(ALPHA, row[0])
        beta_ratio = _pick(BETA_RATIO, row[1])
        gamma_ratio = _pick(GAMMA_RATIO, row[2])
        recs.append({
            "name": f"bench-{i:03d}",
            "regime": "bench",
            "alpha": alpha,
            "beta": round(alpha * beta_ratio, 6),
            "gamma": round(alpha * gamma_ratio, 8),
            "AvgInputTokens": _pick(L_IN, row[3]),
            "AvgOutputTokens": _pick(L_OUT, row[4]),
            "targetITL": _pick(T_ITL, row[5]),
            "targetTTFT": _pick(T_TTFT, row[6]),
            "maxQueueSize": _pick(Q, row[7]),
        })
    return recs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path,
                    default=REPO_ROOT / "nous" / "scenarios_benchmark.json")
    args = ap.parse_args()
    recs = generate(n=args.n, seed=args.seed)
    args.out.write_text(json.dumps(
        {"search_range": {"m_min": 1, "m_max": 256}, "scenarios": recs}, indent=2))
    print(f"wrote {len(recs)} benchmark scenarios to {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the test**

```bash
python -m pytest nous/harness/tests/test_scenarios_benchmark.py -q
```
Expected: PASS (4 tests). If `test_ratio_manifold_preserved` fails, the rounding in `beta`/`gamma` pushed a value just outside the envelope — widen the assertion bounds slightly or drop the rounding.

- [ ] **Step 6: Generate and commit the grid**

```bash
python -m nous.harness.scenarios_benchmark --n 30 --seed 42
python -c "import json; d=json.load(open('nous/scenarios_benchmark.json')); print(len(d['scenarios']), d['scenarios'][0])"
git add nous/harness/scenarios_benchmark.py nous/harness/tests/test_scenarios_benchmark.py nous/scenarios_benchmark.json nous/requirements.txt
git commit -m "nous: LHS benchmark grid generator (seed=42, N=30)"
```

---

## Phase 5 — Truth-cache cutover (staged)

### Task 7: Regenerate + validate the 6 dev caches

**Files:**
- Modify: `nous/harness/baseline_truth.py` (add `regime` passthrough; keep dev cache layout)
- Delete: `nous/cache/truth-{baseline,short-tight-ttft,long-loose-itl,small-queue}.json`
- Create (output): `nous/cache/truth-{baseline,itl-only,ttft-only,unbounded,alpha-low,alpha-high}.json`

- [ ] **Step 1: Update `baseline_truth.py`** — drop the campaign-level α/β/γ (oracle now reads them per scenario) and record `regime` in the payload

In `main()`, the `make_oracle` call loses its kwargs and the payload gains `regime`:

```python
        for s in config.scenarios:
            eval_, stats = make_oracle(base_url, s)
            curve = []
            best_m, best_t = m_min, 0.0
            for m in range(m_min, m_max + 1):
                out = eval_(m)
                t = float(out["throughput"])
                curve.append({"m": m, "throughput": t})
                if t > best_t:
                    best_t, best_m = t, m
            payload = {
                "scenario": s.name,
                "regime": s.regime,
                "M_truth": best_m,
                "throughput_truth": best_t,
                "f_curve": curve,
            }
            (args.cache_dir / f"truth-{s.name}.json").write_text(json.dumps(payload, indent=2))
            print(f"[{s.name}] M*={best_m} f*={best_t:.4f}  (calls={stats.calls})")
```

(The `load_campaign` import already gives `config.scenarios`; `config.alpha` is gone — remove any reference to it.)

- [ ] **Step 2: Delete the stale caches**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
rm nous/cache/truth-baseline.json nous/cache/truth-short-tight-ttft.json \
   nous/cache/truth-long-loose-itl.json nous/cache/truth-small-queue.json
```

- [ ] **Step 3: Build the Go server** (used by the truth scan)

```bash
go build -o /tmp/queue-analysis . && echo "built"
```
Expected: `/tmp/queue-analysis` exists. `baseline_truth.py` spawns the server itself via `AnalyzerServer`, so you don't need to start it manually — but the build confirms it compiles.

- [ ] **Step 4: Run the dev truth scan**

```bash
source nous/.venv/bin/activate
python -m nous.harness.baseline_truth --scenarios nous/scenarios.json --cache-dir nous/cache
```
Expected: 6 lines, one per scenario, finishing in ~1-2 min (6 × 256 calls).

- [ ] **Step 5: Validate against the spec §4.2 probe values** (the load-bearing sanity gate)

```bash
python -c "
import json, pathlib
exp = {'baseline':(80,1.92),'itl-only':(40,0.13),'ttft-only':(80,4.49),
       'unbounded':(256,122),'alpha-low':(200,5.19),'alpha-high':(40,0.28)}
for name,(m,f) in exp.items():
    d = json.load(open(f'nous/cache/truth-{name}.json'))
    print(f'{name:12s} M*={d[\"M_truth\"]:>4d} (exp {m:>4d})  f*={d[\"throughput_truth\"]:.3f} (exp {f})')
"
```
Expected: `M_truth` within a few of each probe (probes were approximate; `~80` etc.). `f*` in the right ballpark. **If any scenario is wildly off** (e.g. `unbounded` M*≠256, or an `f*` off by >2×), STOP — either a scenario row is mistyped (Task 4) or `formulas.py`/oracle has a bug. Do not proceed to the benchmark until the dev caches look sane (spec §8.3 lists truth-cache anomalies as blocking).

- [ ] **Step 6: Commit the dev caches**

```bash
git add nous/harness/baseline_truth.py nous/cache/truth-baseline.json \
  nous/cache/truth-itl-only.json nous/cache/truth-ttft-only.json \
  nous/cache/truth-unbounded.json nous/cache/truth-alpha-low.json \
  nous/cache/truth-alpha-high.json
git rm --cached --ignore-unmatch nous/cache/truth-short-tight-ttft.json \
  nous/cache/truth-long-loose-itl.json nous/cache/truth-small-queue.json 2>/dev/null || true
git commit -m "nous: regenerate 6 dev truth caches on corrected analyzer; delete stale caches"
```

---

### Task 8: Generate + validate the ~30 benchmark caches

**Files:**
- Modify: `nous/harness/baseline_truth.py` (add `--out-subdir` for `cache/bench/<idx>.json`)
- Create (output): `nous/cache/bench/bench-000.json` … `bench-029.json`

- [ ] **Step 1: Add an output-subdir + index-naming option to `baseline_truth.py`**

Add a CLI flag and use it for the cache filename. Insert an `--out-subdir` argument and change the write path:

```python
    ap.add_argument("--out-subdir", type=str, default=None,
                    help="if set, write caches under cache-dir/<subdir>/<name>.json")
    # ... after parsing:
    out_dir = args.cache_dir / args.out_subdir if args.out_subdir else args.cache_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    # ... and in the loop, replace the write target:
            (out_dir / f"truth-{s.name}.json" if not args.out_subdir
             else out_dir / f"{s.name}.json").write_text(json.dumps(payload, indent=2))
```

(So dev caches stay `cache/truth-<name>.json`; benchmark caches become `cache/bench/bench-XXX.json`, matching spec §6.4.)

- [ ] **Step 2: Spot-check 3 benchmark scenarios before the full run** (catch L=4096 hangs early — spec §8.3)

```bash
source nous/.venv/bin/activate
python -m nous.harness.baseline_truth \
  --scenarios nous/scenarios_benchmark.json --cache-dir nous/cache \
  --out-subdir bench --m-min 1 --m-max 256 &
SCAN=$!
sleep 60 && kill $SCAN 2>/dev/null
ls nous/cache/bench/ | head
```
Expected: at least a few `bench-XXX.json` written within 60s, none hanging. If the scan stalls with no output (likely an L=4096 / huge-token edge case in the analyzer), STOP and surface to the user (blocking per §8.3).

- [ ] **Step 3: Run the full benchmark scan**

```bash
python -m nous.harness.baseline_truth \
  --scenarios nous/scenarios_benchmark.json --cache-dir nous/cache --out-subdir bench
ls nous/cache/bench/ | wc -l
```
Expected: 30 files; ~10 min wall-clock (spec §10).

- [ ] **Step 4: Validate the benchmark caches**

```bash
python -c "
import json, glob
files = sorted(glob.glob('nous/cache/bench/bench-*.json'))
print('files:', len(files))
bad = [f for f in files if json.load(open(f))['throughput_truth'] <= 0]
print('zero-throughput (all-infeasible) scenarios:', bad)
"
```
Expected: 30 files. A few all-infeasible scenarios are possible (tight targets) — note them, but if >1/3 are zero-throughput the ranges or analyzer are suspect; surface to the user.

- [ ] **Step 5: Commit**

```bash
git add nous/harness/baseline_truth.py nous/cache/bench/
git commit -m "nous: benchmark truth caches (cache/bench/, 30 scenarios)"
```

---

## Phase 6 — NOUS brief

### Task 9: Rewrite `nous/description.txt`

**Files:**
- Modify: `nous/description.txt` (full rewrite per spec §7.1)

**Prep:** read the current `nous/description.txt` so the rewrite keeps the harness-mechanics paragraphs (server spawn, call counting, the +1 confirmatory eval) that are still accurate.

- [ ] **Step 1: Rewrite `nous/description.txt`** with the 8 sections from spec §7.1, in order:

1. **Background** — `/solve` + `/target` on :8080; one line that the analyzer was corrected in `99024df` and prior NOUS findings are not load-bearing.
2. **Analytic primitives** — the three formulas from the canonical-contracts block above (prefill, itl, tau) with the parameter glossary; one line: "These give per-iteration mean times. `/target` composes them through a state-dependent M/M/1 solver." State that `nous/harness/formulas.py` is an importable module implementing exactly these.
3. **Problem definition** — `f(M)`, `argmax` over `[1, 256]`; one line: "Use the analytic primitives to derive M̂(params) where possible, then refine via `/target` if needed."
4. **Scenarios** — the 6 dev scenarios from §4.2, named, with regime label. Note the benchmark grid path `nous/scenarios_benchmark.json` exists but is **not** enumerated; iter 1-4 work on the dev set.
5. **Harness contract** — the widened signature `search(target_eval, params, m_min, m_max) -> int`; `params` keys (the canonical-contracts list); prior strategies remain as the baseline cohort.
6. **Pareto axes and scoring** — unchanged: `(calls, gap_throughput_rel)`, worst-case primary; truth-cache paths `nous/cache/truth-<name>.json` (dev) and `nous/cache/bench/<idx>.json` (benchmark).
7. **Stage plan** — the 5-iter table from spec §5, with mode (observe/code_changes) and gate criteria explicit.
8. **Out of scope** — per spec §6.6.

Pull the primitive formulas verbatim from the canonical-contracts block; do not paraphrase the arithmetic.

- [ ] **Step 2: Sanity-check it mentions `formulas.py` and the new signature**

```bash
grep -n "formulas.py\|search(target_eval, params\|99024df\|bench" nous/description.txt
```
Expected: each appears at least once.

- [ ] **Step 3: Commit**

```bash
git add nous/description.txt
git commit -m "nous: rewrite description.txt for formula-guided campaign brief"
```

---

### Task 10: Rewrite `nous/campaign.yaml`

**Files:**
- Modify: `nous/campaign.yaml` (per spec §7.2)

- [ ] **Step 1: Update `research_question`, `run_id`, and prompts**

Replace the `research_question` block and `run_id` (keep `target_system` as-is):

```yaml
research_question: >
  Given the analytic primitives ITL(B), TTFT components, and τ(B) for a vLLM-style
  inference server, derive M̂(params) = argmax_M f(M) and design a formula-guided
  search that pinpoints argmax_M f via few /target calls. Score on (calls,
  gap_throughput_rel); see nous/description.txt for the full brief.

run_id: queue-throughput-formulas

max_iterations: 5
```

Leave `target_system` and `prompts` unchanged (the `repo_path` and methodology layer still apply).

- [ ] **Step 2: Verify YAML parses**

```bash
python -c "import yaml; print(yaml.safe_load(open('nous/campaign.yaml'))['run_id'])"
```
Expected: prints `queue-throughput-formulas`.

- [ ] **Step 3: Commit**

```bash
git add nous/campaign.yaml
git commit -m "nous: campaign.yaml — new run_id and formula-guided research question"
```

---

## Phase 7 — Campaign execution (5 iterations, gated)

**Format note:** these tasks are NOT TDD. Each is *run NOUS for one iteration → verify the spec §8.1 gate → review with the user → decide go/no-go*. NOUS authors the iter-4/5 strategy files (`formula_guided.py`, `naive_ternary.py`); you do not write them. Follow the `reference_nous_install` memory for the exact `nous` invocation (source `nous/.venv`; the campaign is configured by `nous/campaign.yaml` with `run_id: queue-throughput-formulas`).

**Pre-flight (run once before Task 11):**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
source nous/.venv/bin/activate
python -m pytest nous/harness/tests/ -q          # full suite green
go build -o /tmp/queue-analysis . && echo built  # server compiles
```
Expected: all tests pass, server builds. If not, fix before launching NOUS.

### Task 11: Iter 1 (observe) — derive M̂(params)

- [ ] **Step 1: Run iter 1** (observe mode; no oracle calls, no code changes). Use the `nous run` invocation from `reference_nous_install`, capped at the first iteration.

- [ ] **Step 2: Verify the gate (spec §8.1, iter 1)**

NOUS must produce: a **closed-form M̂(params) for at least one binding case** (most likely the ITL constraint: `n_ITL = (TargetITL − a)/b` from the affine `itl(B) = a + b·B`) **with an explicit derivation**, and open cases listed as "needs case analysis."

- [ ] **Step 3: Cross-check the ITL inversion numerically**

```bash
python -c "
from nous.harness import formulas, scenarios
sc = scenarios.load_scenarios('nous/scenarios.json')
s = next(x for x in sc if x.name=='baseline'); p = scenarios.scenario_to_params(s)
# itl is affine in B; invert at the baseline target and compare to M_truth=~80.
i1, i2 = formulas.itl(1,p), formulas.itl(2,p); b = i2-i1; a = i1-b
import json; mt = json.load(open('nous/cache/truth-baseline.json'))['M_truth']
print('n_ITL ~', (p['targetITL']-a)/b, ' M_truth', mt)
"
```
Expected: `n_ITL` lands in a plausible relation to `M_truth` (it bounds the ITL-feasible batch). If NOUS's derivation contradicts this arithmetic, push back before moving on.

- [ ] **Step 4: Review with user.** If the gate fails (no closed form on ANY case), the formulas may be wrong or the problem isn't analytically tractable — HALT and reconsider (spec §8.1). Otherwise commit NOUS's iter-1 artifacts and proceed.

```bash
git add -A && git commit -m "nous: iter 1 — derive M-hat(params), ITL closed form"
```

### Task 12: Iter 2 (observe) — regime partition

- [ ] **Step 1: Run iter 2.**

- [ ] **Step 2: Verify the gate** — a regime partition (**≤ 5 regimes**) with boundary equations in (params), covering **≥ 3 regimes from the dev set** (itl-only, ttft-only, crossover, unbounded are the candidates). This directly answers spec §8.2.4 ("is K=4 enough?") with a number.

- [ ] **Step 3: Review.** If the partition collapses to "always ITL" or "depends on everything," that's a finding (the formulas don't separate cleanly) — record it, don't force a partition. Commit artifacts.

```bash
git add -A && git commit -m "nous: iter 2 — regime partition + boundary equations"
```

### Task 13: Iter 3 (observe) — validate M̂ against `/target`

- [ ] **Step 1: Run iter 3** (oracle calls allowed; NOT counted against any algorithm budget — spec §5).

- [ ] **Step 2: Verify the gate** — a per-dev-scenario error table with `gap_M = |M̂ − M_truth|` and `gap_f = (f_truth − f_M̂)/f_truth`, with **worst-case `gap_f ≤ 20%` on ≥ 4/6 scenarios**.

- [ ] **Step 3: Decision point.** Record whether the predictor is usable alone or needs search refinement (drives iter-4 design). If loose everywhere, iter 4 falls back to formula-as-bracket-only. Commit artifacts.

```bash
git add -A && git commit -m "nous: iter 3 — predictor validation vs /target on dev set"
```

### Task 14: Iter 4 (code_changes) — `formula_guided.py` + `naive_ternary.py`

- [ ] **Step 1: Run iter 4** (code_changes; NOUS adds strategy files under `nous/harness/strategies/`).

- [ ] **Step 2: Verify the new strategies obey the contract**

```bash
source nous/.venv/bin/activate
python -c "
from nous.harness.run import load_strategy
for f in ('formula_guided','naive_ternary'):
    s = load_strategy(f'nous/harness/strategies/{f}.py'); print(f, 'loaded', s)
"
```
Expected: both load and expose `search(target_eval, params, m_min, m_max)`. If `load_strategy` raises (wrong signature), have NOUS fix the signature before scoring.

- [ ] **Step 3: Run both on the dev set and check the gate**

```bash
for arm in formula_guided naive_ternary; do
  python -m nous.harness.run --scenarios nous/scenarios.json \
    --strategy nous/harness/strategies/$arm.py \
    --out nous/results/dev-$arm.json
done
python -c "
import json
for arm in ('formula_guided','naive_ternary'):
    rs=json.load(open(f'nous/results/dev-{arm}.json'))
    wc_calls=max(r['calls'] for r in rs); wc_gap=max(r['gap_throughput_rel'] for r in rs)
    print(f'{arm:14s} worst-calls={wc_calls} worst-gap={wc_gap:.4f}')
"
```
Gate (spec §8.1, iter 4): `formula_guided` predicted **worst-case calls ≤ 8** and **gap_f ≤ 5%** on the dev set. If the run misses these, report honestly — no retry-fudging; iter 5 still runs.

- [ ] **Step 4: Review + commit**

```bash
git add nous/harness/strategies/formula_guided.py nous/harness/strategies/naive_ternary.py nous/results/
git commit -m "nous: iter 4 — formula_guided + naive_ternary strategies"
```

### Task 15: Iter 5 (code_changes) — benchmark Pareto + per-regime breakdown

- [ ] **Step 1: Run all arms on the benchmark grid.** The benchmark caches live in `cache/bench/<idx>.json`, so the run needs `--cache-dir` pointed appropriately. Confirm `run.py`'s `load_truth_for` resolves `bench-XXX` names — benchmark scenario names are `bench-XXX` and dev caches are `truth-<name>.json`, so for the benchmark run point `--cache-dir nous/cache/bench` and confirm `load_truth_for` looks for `truth-bench-XXX.json` vs `bench-XXX.json`. **If the names don't line up, that's a one-line fix in `load_truth_for` (or a `--truth-prefix` flag) — make it before scoring.**

```bash
for arm in formula_guided naive_ternary predictor_direct predictor_hybrid predictor_naive \
           adaptive_binary adaptive_early_exit adaptive_interpolation ratio_binary_search example_linear_scan; do
  python -m nous.harness.run --scenarios nous/scenarios_benchmark.json \
    --strategy nous/harness/strategies/$arm.py \
    --cache-dir nous/cache/bench --out nous/results/bench-$arm.json
done
```

- [ ] **Step 2: Verify the gate** — NOUS produces a **Pareto plot on the benchmark grid**, a **per-regime table** (regime × worst-calls, worst-gap; regime taken from each scenario's `regime` field, with `bench` rows sub-classified post-hoc), and an **honest comparison** to the prior strategies.

- [ ] **Step 3: Confirm campaign-level success (spec §8.2)**

The campaign succeeds if: (1) M̂ has a stated form backed by derivation; (2) the regime partition is empirically validated; (3) **`formula_guided` strictly Pareto-dominates `naive_ternary` on worst-case (calls, gap)**; (4) "is K=4 enough?" gets a number. Record which of 1-4 hold (1-3 holding with 4 missing = partial success).

- [ ] **Step 4: Final campaign commit**

```bash
git add nous/results/ nous/harness/strategies/ .nous/ 2>/dev/null || git add nous/results/ nous/harness/strategies/
git commit -m "nous: iter 5 — benchmark Pareto, per-regime breakdown, comparison report"
```

---

## Phase 8 — Post-campaign

### Task 16: Memory + handoff updates

**Files:** memory files under `~/.claude/projects/.../memory/` (no repo files)

- [ ] **Step 1: Update `project_nous_campaign_status.md`** — new `run_id queue-throughput-formulas` supersedes the prior run; corrected-analyzer findings are now load-bearing. Link `[[project_analyzer_double_count_fix]]`.

- [ ] **Step 2: Update `project_paper_analysis_section.md`** — paper revival is unblocked; the analysis/predictor/algorithm sections rebuild on the new derivation (spec §9.1). Note the old `paper/sections/analysis.tex` skeleton's quantitative values (`M*=40`, `f*=2.17`) are stale and replaced by the new dev-set truths (e.g. baseline `M*≈80`).

- [ ] **Step 3: Add a new memory** capturing the campaign's headline findings (M̂ form, regime count, whether formula_guided dominated) and link it from `MEMORY.md`.

- [ ] **Step 4: Confirm branch/PR plan with the user** — whether `nous-formula-campaign` merges to `main` via PR now, or stays open until the paper sections rebuild (spec §9.4).

---

## Self-Review Checklist (run before declaring harness-prep done)

- [ ] `formulas.py` parity test (`test_formulas.py`) passes against the committed `golden_primitives.json` — the port is checked against Go, not itself.
- [ ] `MAX_NUM_TOKENS = 8192` in `formulas.py` matches `analyzer.DefaultMaxNumTokens` (`queueanalyzer.go:17`).
- [ ] `Scenario` fields, `ALLOWED_FIELDS`, and the `params` dict keys are identical across `scenarios.py`, `run.py`, `formulas.py`, and the strategy tests (no `alpha` vs `Alpha` drift).
- [ ] The widened `search(target_eval, params, m_min, m_max)` signature is in all 8 retrofitted strategies AND `run.py` builds `params` via `scenario_to_params` and passes it positionally.
- [ ] `make_oracle` and `baseline_truth.py` no longer take campaign-level α/β/γ (they read per-scenario).
- [ ] Full `pytest nous/harness/tests/` is green after Task 5 and again after Task 8.
- [ ] Dev truth caches validated against spec §4.2 probes before the benchmark scan ran (staged, per decision #3).
- [ ] Old caches (`truth-short-tight-ttft`, `truth-long-loose-itl`, `truth-small-queue`) are deleted; new layout has dev `truth-<name>.json` + `cache/bench/bench-XXX.json`.
- [ ] `description.txt` states the primitives verbatim from the canonical-contracts block and names `formulas.py` as importable.
- [ ] `campaign.yaml` `run_id` is `queue-throughput-formulas` (no collision with the prior `queue-throughput` state).
- [ ] No NOUS-authored files (`formula_guided.py`, `naive_ternary.py`) were pre-written in Phases 1-6 — those are iter-4 deliverables.
