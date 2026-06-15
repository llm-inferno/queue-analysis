# Optimal-Concurrency Search in the Go Queue Analyzer

**Date:** 2026-06-15
**Branch:** `optimal-concurrency-search`
**Status:** Approved design

## Goal

Given model and workload characteristics (service parameters α/β/γ, average
input/output tokens) and SLO targets (TTFT, ITL), compute the **minimum request
concurrency level** (max batch size) `M*` that achieves **near-maximum request
throughput while still meeting the SLO**.

Operating below `M*` compromises throughput; operating above `M*` over-provisions
concurrency, which hurts performance robustness when traffic surges. `M*` is the
*onset* of the throughput plateau, not the strict argmax.

## Background: this algorithm is already designed and validated

The algorithm is the **formula-guided onset search** documented in
`paper/sections/algorithm.tex` (Algorithm 1, `FormulaGuidedOnsetSearch`) and
validated by an automated formula-discovery (NOUS) campaign. This feature ports
that validated algorithm into Go and exposes it as a first-class queue-analyzer
capability.

### Port provenance (pinned — do not drift)

The **canonical** reference implementation is:

```
nous/harness/strategies/formula_guided.py   (shipped on commit 85ab6b7)
```

This is the file `paper/scripts/eval_strategies.py` imports to generate the
golden results in `paper/data/eval_results.json`, so it is by definition the
behavior our parity test checks against.

There are **stale candidates** under
`.nous/queue-throughput-formulas/runs/iter-5/inputs/` (`formula_guided_v2.py`,
`formula_guided_v3.py`, `formula_guided_ablate_*.py`, `formula_guided_hmain.py`)
and a leftover `formula_guided_bidir` — **do not port any of these.** Commit
`85ab6b7` ("ship v3 onset search + reconcile") promoted a *reconciled* v3. The
only behavioral difference between the raw iter-5 `v3` candidate and the shipped
version is the infeasible-everywhere return value: the candidate returned
`m_max`; the shipped/canonical version returns **`m_min`** (matching the truth
convention `M_truth = m_min` and `algorithm.tex`). Everything else is identical.

### The oracle `f(M)`

`f(M)` = throughput sustainable at concurrency cap `M` while meeting the SLO.
Concretely: build an analyzer with `MaxBatchSize = M`, call `Size(targetPerf)`,
return `metrics.Throughput`. This is exactly what the campaign used via the
`/target` REST endpoint. An infeasible reading (`Size()` error or throughput
`<= 0`, mirroring `/target`'s HTTP 400) is treated as `feasible = false` and is
**uncounted** in the call budget.

## Architecture

Approach: an **injectable-oracle optimizer** in `pkg/analyzer`, with the
user-facing analyzer method and REST endpoint as thin adapters over it. The
injectable oracle is the key design lever — it lets the search be unit-tested
against synthetic f-curves and parity-tested against the campaign's cached truth,
proving the Go port reproduces the validated results.

### 1. `pkg/analyzer/concurrency.go` — the core

```go
const (
    DefaultOnsetEpsilon  = float32(0.02) // ε in the near-peak objective
    DefaultOnsetMaxIters = 6             // bounds worst-case oracle calls at 8
    DefaultMMin          = 1
    DefaultMMax          = 256
)

// ConcurrencyOracle returns throughput f(M) at concurrency cap M.
// feasible == false means the SLO is unreachable at M (uncounted, mirrors
// /target HTTP 400 -> throughput 0).
type ConcurrencyOracle func(m int) (throughput float32, feasible bool)

type ConcurrencyOptimizer struct {
    ServiceParms *ServiceParms
    RequestSize  *RequestSize
    Target       *TargetPerf
    MaxNumTokens int     // chunk math; default DefaultMaxNumTokens
    MaxQueueSize int
    MMin, MMax   int     // default 1, 256
    Epsilon      float32 // default 0.02
    MaxIters     int     // default 6
    Oracle       ConcurrencyOracle // nil => Size()-based default
}

type ConcurrencyResult struct {
    Concurrency      int              // M*: min concurrency for near-peak throughput under SLO
    Throughput       float32          // f(M*), confirmatory
    Metrics          *AnalysisMetrics // full metrics at M*
    MITL, MTPF       int              // closed-form brackets (zero oracle calls)
    AnchorThroughput float32          // f* probed at m_max
    Calls            int              // feasible oracle calls incl. confirmatory
    Probes           []int            // probe sequence (diagnostics)
    Feasible         bool
}
```

#### `Find()` — faithful port of the canonical `search()`

1. `M_ITL` = largest `B ∈ [1, MMax]` with `itlNew(B) <= TargetITL` (else `1`);
   `M_TPF` = largest `B ∈ [1, MMax]` with `prefillNew(B) <= TargetTTFT` (else
   `1`). Reuses the existing `itlNew` / `prefillNew` primitives plus a
   `NumIterationsPerPrefill` chunk table built once at `MMax`. Zero oracle calls.
   **Note:** the canonical strategy uses its `_largest_feasible` scan (default
   `1` when none feasible) — *not* the `m_tpf` helper in `primitives.py` (which
   defaults to `0`). Port the scan with the `1` default.
2. `seed = MMax`; `f* = oracle(seed)`. If infeasible or `f* <= 0` → return
   `{Concurrency: MMin, Feasible: false}` (infeasible-everywhere convention).
3. `θ = (1 − Epsilon/2) · f*`.
4. `lo = max(MMin, min(M_ITL, M_TPF))`; `U = max(M_ITL, M_TPF)`;
   `hi = min(seed, max(3U, lo+1), MMax)`; then `hi = max(lo, hi)`.
5. Bounded monotone-predicate bisection on `[lo, hi]`, at most `MaxIters` probes:
   `mid = (lo+hi)/2`; if `f(mid) >= θ` then `hi = mid` else `lo = mid+1`.
6. `M* = clamp(hi, MMin, MMax)`; one confirmatory call `o.Oracle(M*)` whose
   result is counted in `Calls` if feasible (matches the harness's
   `calls = strategy_calls + 1` accounting). `Calls` counts feasible evaluations
   — anchor + search probes + this confirmatory call.

**Confirmatory call vs. `Metrics` (resolves the injected-oracle ambiguity).**
The confirmatory step always goes through `o.Oracle` so the call budget is
correct regardless of which oracle is wired in — this is what keeps the parity
test's `Calls` exact. The full `AnalysisMetrics` is a *presentation extra*: it is
populated only when `M*` is feasible **and** the optimizer can produce it,
namely on the default `Size()`-based path (where the optimizer does an additional,
uncounted `Size(Target)` at `M*` to fill `Metrics`). When a custom oracle is
injected (e.g. the cache-backed parity test), `Metrics` may be `nil` and only
`Concurrency` / `Throughput` / `Calls` are asserted.

#### Default oracle

Builds `Configuration{MaxBatchSize: m, MaxQueueSize, MaxNumTokens, ServiceParms}`,
constructs an `LLMQueueAnalyzer`, calls `Size(Target)`, and returns
`(metrics.Throughput, err == nil && metrics.Throughput > 0)`.

### 2. Analyzer method (user-facing "analyzer method")

```go
// OptimalConcurrency uses the analyzer's own ServiceParms/RequestSize and its
// MaxBatchSize as m_max; constructs a ConcurrencyOptimizer and runs Find().
func (qa *LLMQueueAnalyzer) OptimalConcurrency(target *TargetPerf) (*ConcurrencyResult, error)
```

### 3. REST endpoint — `POST /optimize` (`pkg/service/analyzer.go`)

Reuses `ProblemData` as the request body (`maxBatchSize` is interpreted as
`m_max`; `RPS` is ignored). New response struct:

```go
type OptimizeData struct {
    Concurrency  int     `json:"concurrency"`  // M*
    Throughput   float32 `json:"throughput"`
    AvgRespTime  float32 `json:"avgRespTime"`  // average response time at M*
    AvgWaitTime  float32 `json:"avgWaitTime"`  // average queueing time at M*
    AvgNumInServ float32 `json:"avgNumInServ"`
    AvgTTFT      float32 `json:"avgTTFT"`
    AvgITL       float32 `json:"avgITL"`
    MaxRPS       float32 `json:"maxRPS"`
    MITL         int     `json:"M_ITL"`
    MTPF         int     `json:"M_TPF"`
    Calls        int     `json:"oracleCalls"`
    Feasible     bool    `json:"feasible"`
}
```

The metric fields (`Throughput` … `MaxRPS`) mirror `AnalysisData`'s order and
JSON names so `/solve`, `/target`, and `/optimize` report a consistent
operating-point block; `/optimize` then adds the concurrency-specific fields
(`concurrency`, `M_ITL`, `M_TPF`, `oracleCalls`, `feasible`). All metric fields
are populated from the confirmatory `Metrics` at `M*` when feasible, else zero.

Registered alongside `/solve` and `/target` in `NewAnalyzer()`.

### 4. Demo — `demos/concurrency/main.go`

Mirrors `demos/analyzer`: a sample scenario, prints `M*`, its metrics, the
`M_ITL` / `M_TPF` brackets, and the oracle-call count.

## Testing

The injectable oracle makes both tests possible:

- **`pkg/analyzer/concurrency_test.go` — unit:** inject synthetic
  monotone-to-plateau f-curves; assert `M*`, the bracket, and the call budget
  (≤ 8). Edge cases: fully infeasible → `MMin` in 1 call; `unbounded` → `MMax`
  in 2 calls.
- **`pkg/analyzer/concurrency_parity_test.go` — golden parity:** for each
  scenario in `nous/scenarios.json` and `nous/scenarios_benchmark.json`, load its
  `f_curve` from the truth cache (`nous/cache/truth-<name>.json` and
  `nous/cache/bench/<name>.json`) as a cache-backed oracle (throughput per `m`;
  `feasible = throughput > 0`), run `Find()`, and assert `Concurrency` and
  `Calls` exactly match the `formula_guided` records in
  `paper/data/eval_results.json` (36 scenarios). This proves the Go port
  reproduces the validated campaign results.

The closed-form primitives (`itl`, `ttft_prefill`) are already parity-tested by
`pkg/analyzer/primitives_parity_test.go`.

## Scope / non-goals

- No change to `/solve`, `/target`, `Size()`, or the queueing model.
- Single high-anchor only; a multi-probe `f*` for large chunk-count jumps is
  future work, per `algorithm.tex` §Guarantees.
- Constants are overridable but default to the paper's ε = 0.02, MaxIters = 6,
  bounds `[1, 256]`.

## Acceptance criteria

1. `ConcurrencyOptimizer.Find()` and `LLMQueueAnalyzer.OptimalConcurrency()`
   implemented in `pkg/analyzer`.
2. `POST /optimize` endpoint returns `OptimizeData`.
3. `demos/concurrency/main.go` runs end-to-end.
4. Unit tests pass, including the edge cases above.
5. The golden parity test reproduces all 36 `formula_guided` `M_chosen` and
   `calls` values from `paper/data/eval_results.json`.
6. `go build ./...` and `go test ./...` are clean.
