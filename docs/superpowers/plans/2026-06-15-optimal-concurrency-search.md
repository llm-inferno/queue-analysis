# Optimal-Concurrency Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optimal-concurrency feature to the Go queue analyzer that, given model + workload + SLO targets, returns the minimum concurrency (max batch size) `M*` achieving near-peak throughput under the SLO.

**Architecture:** Port the validated formula-guided onset search (`nous/harness/strategies/formula_guided.py`, shipped commit `85ab6b7`) into an injectable-oracle `ConcurrencyOptimizer` in `pkg/analyzer`. The closed-form bracket (`M_ITL`, `M_TPF`) reuses existing `itlNew`/`prefillNew` primitives; the oracle `f(M)` defaults to "build analyzer at `MaxBatchSize=M`, call `Size()`, return throughput". A thin `LLMQueueAnalyzer.OptimalConcurrency` method, a `POST /optimize` REST endpoint, and a demo sit on top. A golden parity test reproduces all 36 `formula_guided` results.

**Tech Stack:** Go 1.24, gin (REST), Go's built-in `testing` + `net/http/httptest`.

**Reference spec:** `docs/superpowers/specs/2026-06-15-optimal-concurrency-search-design.md`

---

## File Structure

- **Create** `pkg/analyzer/concurrency.go` — `ConcurrencyOptimizer`, `ConcurrencyResult`, `ConcurrencyOracle`, defaults, closed-form bracket, pure `onsetSearch`, `Find`, default `Size()` oracle, and the `LLMQueueAnalyzer.OptimalConcurrency` method. One responsibility: optimal-concurrency search.
- **Create** `pkg/analyzer/concurrency_test.go` — unit tests for `largestFeasibleBatch`, `onsetSearch`, and `Find` edge cases (infeasible, unbounded) via injected oracles.
- **Create** `pkg/analyzer/concurrency_parity_test.go` — golden parity test against `paper/data/eval_results.json` using cache-backed oracles.
- **Modify** `pkg/service/analyzer.go` — add `OptimizeData`, the `optimize` handler, and register `POST /optimize`.
- **Create** `pkg/service/optimize_test.go` — httptest coverage for `/optimize`.
- **Create** `demos/concurrency/main.go` — end-to-end demo.

All test files use `package analyzer` / `package service` (white-box) to reach unexported helpers, matching `pkg/analyzer/primitives_parity_test.go`.

---

## Task 1: Optimizer types, defaults, closed-form bracket, and the pure onset search

**Files:**
- Create: `pkg/analyzer/concurrency.go`
- Test: `pkg/analyzer/concurrency_test.go`

- [ ] **Step 1: Write the failing tests for the two pure helpers**

Create `pkg/analyzer/concurrency_test.go`:

```go
package analyzer

import "testing"

func TestLargestFeasibleBatch(t *testing.T) {
	// metric(B) = B (monotone increasing); largest B<=target.
	metric := func(B int) float32 { return float32(B) }

	if got := largestFeasibleBatch(metric, 10, 256); got != 10 {
		t.Errorf("target 10: got %d, want 10", got)
	}
	if got := largestFeasibleBatch(metric, 5.5, 256); got != 5 {
		t.Errorf("target 5.5: got %d, want 5", got)
	}
	// even B=1 infeasible -> floor at 1 (matches _largest_feasible default).
	if got := largestFeasibleBatch(metric, 0.5, 256); got != 1 {
		t.Errorf("target 0.5: got %d, want 1", got)
	}
	// nothing binds within range -> capped at mMax.
	if got := largestFeasibleBatch(metric, 1000, 256); got != 256 {
		t.Errorf("target 1000: got %d, want 256", got)
	}
}

func TestOnsetSearchFindsSmallestAboveThreshold(t *testing.T) {
	// Monotone-to-plateau curve: f(m) = min(m, 50)/50 (rises, then flat at 1.0).
	f := func(m int) float32 {
		v := m
		if v > 50 {
			v = 50
		}
		return float32(v) / 50.0
	}
	// threshold 0.99 -> smallest m with f(m) >= 0.99 is m=50 (f(49)=0.98).
	got := onsetSearch(f, 0.99, 1, 256, 6)
	if got != 50 {
		t.Errorf("got %d, want 50", got)
	}
}

func TestOnsetSearchRespectsBracketAndIterCap(t *testing.T) {
	f := func(m int) float32 { return 1.0 } // everything passes
	// lo==hi -> returns hi with no iterations.
	if got := onsetSearch(f, 0.5, 7, 7, 6); got != 7 {
		t.Errorf("degenerate bracket: got %d, want 7", got)
	}
}
```

- [ ] **Step 2: Run the tests to verify they fail to compile**

Run: `go test ./pkg/analyzer/ -run 'TestLargestFeasibleBatch|TestOnsetSearch' -v`
Expected: FAIL — `undefined: largestFeasibleBatch`, `undefined: onsetSearch`.

- [ ] **Step 3: Create `concurrency.go` with types, defaults, bracket, and pure search**

Create `pkg/analyzer/concurrency.go`:

```go
package analyzer

import "fmt"

// Onset-search defaults (paper: epsilon = 0.02, MaxIters = 6, bounds [1, 256]).
const (
	DefaultOnsetEpsilon  = float32(0.02)
	DefaultOnsetMaxIters = 6
	DefaultMMin          = 1
	DefaultMMax          = 256
)

// ConcurrencyOracle returns the throughput f(M) sustainable at concurrency cap
// M while meeting the SLO. feasible == false means the SLO is unreachable at M
// (mirrors /target HTTP 400 -> throughput 0); such a reading is uncounted.
type ConcurrencyOracle func(m int) (throughput float32, feasible bool)

// ConcurrencyOptimizer finds the minimum concurrency M* achieving near-peak
// throughput under the SLO, via the formula-guided onset search.
type ConcurrencyOptimizer struct {
	ServiceParms *ServiceParms
	RequestSize  *RequestSize
	Target       *TargetPerf
	MaxNumTokens int // chunk math; default DefaultMaxNumTokens
	MaxQueueSize int
	MMin         int     // default DefaultMMin
	MMax         int     // default DefaultMMax; also the high anchor
	Epsilon      float32 // default DefaultOnsetEpsilon
	MaxIters     int     // default DefaultOnsetMaxIters
	Oracle       ConcurrencyOracle // nil => Size()-based default oracle

	oracleIsDefault bool // set in applyDefaults; gates Metrics population
}

// ConcurrencyResult is the outcome of a search.
type ConcurrencyResult struct {
	Concurrency      int              // M*: min concurrency for near-peak throughput under SLO
	Throughput       float32          // f(M*), confirmatory (from the oracle)
	Metrics          *AnalysisMetrics // full metrics at M* (default-oracle path only; else nil)
	MITL             int              // closed-form ITL-binding bracket
	MTPF             int              // closed-form TTFT-prefill-binding bracket
	AnchorThroughput float32          // f* probed at m_max
	Calls            int              // feasible oracle calls (incl. confirmatory)
	Probes           []int            // probe sequence (diagnostics)
	Feasible         bool
}

func (o *ConcurrencyOptimizer) applyDefaults() {
	if o.MaxNumTokens <= 0 {
		o.MaxNumTokens = DefaultMaxNumTokens
	}
	if o.MMin <= 0 {
		o.MMin = DefaultMMin
	}
	if o.MMax <= 0 {
		o.MMax = DefaultMMax
	}
	if o.Epsilon <= 0 {
		o.Epsilon = DefaultOnsetEpsilon
	}
	if o.MaxIters <= 0 {
		o.MaxIters = DefaultOnsetMaxIters
	}
	if o.Oracle == nil {
		o.Oracle = o.defaultOracle
		o.oracleIsDefault = true
	}
}

// largestFeasibleBatch returns the largest B in [1, mMax] with metric(B) <=
// target, or 1 if none qualifies. Mirrors formula_guided.py:_largest_feasible
// (which floors at 1). metric is monotone non-decreasing in B in practice.
func largestFeasibleBatch(metric func(B int) float32, target float32, mMax int) int {
	best := 1
	found := false
	for B := 1; B <= mMax; B++ {
		if metric(B) <= target {
			best = B
			found = true
		}
	}
	if !found {
		return 1
	}
	return best
}

// onsetSearch returns the smallest m in [lo, hi] with oracle(m) >= threshold,
// using at most maxIters probes. Pure bounded monotone-predicate bisection;
// call counting / probe recording is the caller's responsibility (via the
// oracle closure it passes in).
func onsetSearch(oracle func(m int) float32, threshold float32, lo, hi, maxIters int) int {
	iters := 0
	for lo < hi && iters < maxIters {
		mid := (lo + hi) / 2
		if oracle(mid) >= threshold {
			hi = mid
		} else {
			lo = mid + 1
		}
		iters++
	}
	return hi
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `go test ./pkg/analyzer/ -run 'TestLargestFeasibleBatch|TestOnsetSearch' -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add pkg/analyzer/concurrency.go pkg/analyzer/concurrency_test.go
git commit -m "feat: onset-search types, closed-form bracket, pure search (#18)"
```

---

## Task 2: `Find`, the closed-form bracket wiring, and the default `Size()` oracle

**Files:**
- Modify: `pkg/analyzer/concurrency.go`
- Test: `pkg/analyzer/concurrency_test.go`

- [ ] **Step 1: Write failing edge-case tests for `Find`**

Append to `pkg/analyzer/concurrency_test.go`:

```go
// baselineParts returns realistic params (the "baseline" dev scenario) so the
// closed-form bracket computes against real primitives.
func baselineParts() (*ServiceParms, *RequestSize) {
	return &ServiceParms{Alpha: 8, Beta: 0.033, Gamma: 0.000333},
		&RequestSize{AvgInputTokens: 256, AvgOutputTokens: 1024}
}

func TestFindFullyInfeasibleReturnsMMin(t *testing.T) {
	sp, rs := baselineParts()
	o := &ConcurrencyOptimizer{
		ServiceParms: sp, RequestSize: rs,
		Target:   &TargetPerf{TargetTTFT: 60, TargetITL: 20},
		MMin:     1, MMax: 256,
		Oracle:   func(m int) (float32, bool) { return 0, false }, // infeasible everywhere
	}
	res, err := o.Find()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Concurrency != 1 || res.Feasible || res.Calls != 0 {
		t.Errorf("got M=%d feasible=%v calls=%d, want 1/false/0",
			res.Concurrency, res.Feasible, res.Calls)
	}
}

func TestFindUnboundedReturnsMMaxInTwoCalls(t *testing.T) {
	sp, rs := baselineParts()
	// Huge targets => nothing binds => M_ITL = M_TPF = MMax => lo == hi == 256,
	// no descent: anchor + confirmatory = 2 feasible calls, M* = 256.
	o := &ConcurrencyOptimizer{
		ServiceParms: sp, RequestSize: rs,
		Target:   &TargetPerf{TargetTTFT: 1e9, TargetITL: 1e9},
		MMin:     1, MMax: 256,
		Oracle:   func(m int) (float32, bool) { return 1.0, true }, // flat plateau
	}
	res, err := o.Find()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Concurrency != 256 || !res.Feasible || res.Calls != 2 {
		t.Errorf("got M=%d feasible=%v calls=%d, want 256/true/2",
			res.Concurrency, res.Feasible, res.Calls)
	}
	if res.MITL != 256 || res.MTPF != 256 {
		t.Errorf("brackets: got M_ITL=%d M_TPF=%d, want 256/256", res.MITL, res.MTPF)
	}
}

func TestFindRejectsMissingInputs(t *testing.T) {
	o := &ConcurrencyOptimizer{} // no ServiceParms/RequestSize/Target
	if _, err := o.Find(); err == nil {
		t.Error("expected error for missing inputs, got nil")
	}
}
```

- [ ] **Step 2: Run the tests to verify they fail to compile**

Run: `go test ./pkg/analyzer/ -run TestFind -v`
Expected: FAIL — `o.Find undefined`.

- [ ] **Step 3: Implement `Find`, `closedFormBrackets`, `check`, and the default oracle**

Append to `pkg/analyzer/concurrency.go`:

```go
func (o *ConcurrencyOptimizer) check() error {
	if o.ServiceParms == nil || o.RequestSize == nil || o.Target == nil {
		return fmt.Errorf("optimizer requires ServiceParms, RequestSize, and Target")
	}
	if err := o.RequestSize.check(); err != nil {
		return err
	}
	return o.Target.check()
}

// closedFormBrackets computes (M_ITL, M_TPF) from the service model alone — the
// largest batch sizes in [1, MMax] whose closed-form itl / ttft-prefill stays
// within target. Zero oracle calls. Reuses itlNew / prefillNew at the real
// per-B chunk count from NumIterationsPerPrefill.
func (o *ConcurrencyOptimizer) closedFormBrackets() (mITL, mTPF int) {
	cfg := &Configuration{
		MaxBatchSize: o.MMax,
		MaxNumTokens: o.MaxNumTokens,
		MaxQueueSize: o.MaxQueueSize,
		ServiceParms: o.ServiceParms,
	}
	numChunks := NumIterationsPerPrefill(cfg, o.RequestSize)
	itl := func(B int) float32 {
		return itlNew(o.ServiceParms, o.RequestSize, float32(B), numChunks[B])
	}
	tpf := func(B int) float32 {
		return prefillNew(o.ServiceParms, o.RequestSize, float32(B), numChunks[B])
	}
	mITL = largestFeasibleBatch(itl, o.Target.TargetITL, o.MMax)
	mTPF = largestFeasibleBatch(tpf, o.Target.TargetTTFT, o.MMax)
	return mITL, mTPF
}

// Find runs the formula-guided onset search and returns M* with diagnostics.
func (o *ConcurrencyOptimizer) Find() (*ConcurrencyResult, error) {
	if err := o.check(); err != nil {
		return nil, err
	}
	o.applyDefaults()

	res := &ConcurrencyResult{Probes: []int{}}
	res.MITL, res.MTPF = o.closedFormBrackets()

	// A counting wrapper: records every probe; counts a call only when the
	// reading is feasible (throughput > 0), matching the Python harness.
	probe := func(m int) float32 {
		res.Probes = append(res.Probes, m)
		thr, _ := o.Oracle(m)
		if thr > 0 {
			res.Calls++
		}
		return thr
	}

	// High anchor: f* at m_max, always on the plateau for a monotone-to-plateau
	// f. A constraint-endpoint seed can undershoot the peak (RP-2).
	seed := o.MMax
	fstar := probe(seed)
	res.AnchorThroughput = fstar
	if fstar <= 0 {
		// Infeasible everywhere: truth convention sets M_truth = m_min.
		res.Concurrency = o.MMin
		res.Feasible = false
		return res, nil
	}

	threshold := (1 - o.Epsilon/2) * fstar
	lo := max(o.MMin, min(res.MITL, res.MTPF))
	U := max(res.MITL, res.MTPF)
	hi := min(seed, max(3*U, lo+1), o.MMax)
	hi = max(lo, hi)

	hi = onsetSearch(probe, threshold, lo, hi, o.MaxIters)

	mStar := max(o.MMin, min(o.MMax, hi))
	res.Concurrency = mStar

	// Confirmatory call through the oracle (counted if feasible).
	res.Throughput = probe(mStar)
	res.Feasible = res.Throughput > 0
	if res.Feasible && o.oracleIsDefault {
		res.Metrics = o.sizeAt(mStar)
	}
	return res, nil
}

// defaultOracle: f(M) = throughput from Size() at MaxBatchSize = M.
func (o *ConcurrencyOptimizer) defaultOracle(m int) (float32, bool) {
	metrics := o.sizeAt(m)
	if metrics == nil || metrics.Throughput <= 0 {
		return 0, false
	}
	return metrics.Throughput, true
}

// sizeAt builds an analyzer at MaxBatchSize = m and returns its SLO-bound
// operating-point metrics, or nil if construction / sizing fails (mirrors
// /target HTTP 400).
func (o *ConcurrencyOptimizer) sizeAt(m int) *AnalysisMetrics {
	cfg := &Configuration{
		MaxBatchSize: m,
		MaxNumTokens: o.MaxNumTokens,
		MaxQueueSize: o.MaxQueueSize,
		ServiceParms: o.ServiceParms,
	}
	qa, err := NewLLMQueueAnalyzer(cfg, o.RequestSize)
	if err != nil {
		return nil
	}
	_, metrics, _, err := qa.Size(o.Target)
	if err != nil {
		return nil
	}
	return metrics
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `go test ./pkg/analyzer/ -run TestFind -v`
Expected: PASS (3 tests). Run the whole package too: `go test ./pkg/analyzer/` → PASS.

- [ ] **Step 5: Commit**

```bash
git add pkg/analyzer/concurrency.go pkg/analyzer/concurrency_test.go
git commit -m "feat: Find() with closed-form bracket and Size() oracle (#18)"
```

---

## Task 3: `LLMQueueAnalyzer.OptimalConcurrency` method

**Files:**
- Modify: `pkg/analyzer/concurrency.go`
- Test: `pkg/analyzer/concurrency_test.go`

- [ ] **Step 1: Write the failing test**

Append to `pkg/analyzer/concurrency_test.go`:

```go
func TestOptimalConcurrencyMethodBaseline(t *testing.T) {
	sp, rs := baselineParts()
	cfg := &Configuration{MaxBatchSize: 256, MaxQueueSize: 128, ServiceParms: sp}
	qa, err := NewLLMQueueAnalyzer(cfg, rs)
	if err != nil {
		t.Fatalf("NewLLMQueueAnalyzer: %v", err)
	}
	res, err := qa.OptimalConcurrency(&TargetPerf{TargetTTFT: 60, TargetITL: 20})
	if err != nil {
		t.Fatalf("OptimalConcurrency: %v", err)
	}
	if !res.Feasible {
		t.Fatal("baseline should be feasible")
	}
	if res.Concurrency < 1 || res.Concurrency > 256 {
		t.Errorf("M*=%d out of [1,256]", res.Concurrency)
	}
	if res.Metrics == nil {
		t.Error("default-oracle path should populate Metrics")
	}
	if res.Calls > 8 {
		t.Errorf("call budget exceeded: %d > 8", res.Calls)
	}
}
```

- [ ] **Step 2: Run to verify it fails to compile**

Run: `go test ./pkg/analyzer/ -run TestOptimalConcurrencyMethodBaseline -v`
Expected: FAIL — `qa.OptimalConcurrency undefined`.

- [ ] **Step 3: Implement the method**

Append to `pkg/analyzer/concurrency.go`:

```go
// OptimalConcurrency finds the minimum concurrency (max batch size) achieving
// near-peak throughput under the given SLO targets. It uses the analyzer's own
// service/request parameters and its MaxBatchSize as the upper bound m_max.
func (qa *LLMQueueAnalyzer) OptimalConcurrency(target *TargetPerf) (*ConcurrencyResult, error) {
	opt := &ConcurrencyOptimizer{
		ServiceParms: qa.ServiceParms,
		RequestSize:  qa.RequestSize,
		Target:       target,
		MaxNumTokens: qa.MaxNumTokens,
		MaxQueueSize: qa.MaxQueueSize,
		MMin:         DefaultMMin,
		MMax:         qa.MaxBatchSize,
	}
	return opt.Find()
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `go test ./pkg/analyzer/ -run TestOptimalConcurrencyMethodBaseline -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pkg/analyzer/concurrency.go pkg/analyzer/concurrency_test.go
git commit -m "feat: LLMQueueAnalyzer.OptimalConcurrency method (#18)"
```

---

## Task 4: Golden parity test against the campaign results

**Files:**
- Create: `pkg/analyzer/concurrency_parity_test.go`

This test proves the Go port reproduces every `formula_guided` `M_chosen` and `calls` value the campaign recorded. The oracle is the per-scenario cached `f_curve` (a cache lookup IS the oracle value), exactly as `paper/scripts/eval_strategies.py` replays it.

- [ ] **Step 1: Write the parity test**

Create `pkg/analyzer/concurrency_parity_test.go`:

```go
package analyzer

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// Go test working directory is the package dir (pkg/analyzer); repo root is two
// levels up. Mirrors how the campaign fixtures are laid out at the repo root.
const parityRepoRoot = "../.."

type parityScenario struct {
	Name            string  `json:"name"`
	AvgInputTokens  float32 `json:"AvgInputTokens"`
	AvgOutputTokens float32 `json:"AvgOutputTokens"`
	TargetITL       float32 `json:"targetITL"`
	TargetTTFT      float32 `json:"targetTTFT"`
	MaxQueueSize    int     `json:"maxQueueSize"`
	Alpha           float32 `json:"alpha"`
	Beta            float32 `json:"beta"`
	Gamma           float32 `json:"gamma"`
}

type parityScenarioFile struct {
	Scenarios []parityScenario `json:"scenarios"`
}

type fCurvePoint struct {
	M          int     `json:"m"`
	Throughput float32 `json:"throughput"`
}

type truthCache struct {
	FCurve []fCurvePoint `json:"f_curve"`
}

type goldenRecord struct {
	Strategy string `json:"strategy"`
	Scenario string `json:"scenario"`
	Set      string `json:"set"`
	MChosen  int    `json:"M_chosen"`
	Calls    int    `json:"calls"`
	Feasible bool   `json:"feasible"`
}

type evalResults struct {
	Records []goldenRecord `json:"records"`
}

func readJSON(t *testing.T, parts ...string) []byte {
	t.Helper()
	p := filepath.Join(append([]string{parityRepoRoot}, parts...)...)
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatalf("read %s: %v", p, err)
	}
	return b
}

func cacheOracle(c *truthCache) ConcurrencyOracle {
	f := make(map[int]float32, len(c.FCurve))
	for _, pt := range c.FCurve {
		f[pt.M] = pt.Throughput
	}
	return func(m int) (float32, bool) {
		thr := f[m] // absent => 0
		return thr, thr > 0
	}
}

func optimizerFor(s parityScenario, oracle ConcurrencyOracle) *ConcurrencyOptimizer {
	return &ConcurrencyOptimizer{
		ServiceParms: &ServiceParms{Alpha: s.Alpha, Beta: s.Beta, Gamma: s.Gamma},
		RequestSize:  &RequestSize{AvgInputTokens: s.AvgInputTokens, AvgOutputTokens: s.AvgOutputTokens},
		Target:       &TargetPerf{TargetTTFT: s.TargetTTFT, TargetITL: s.TargetITL},
		MaxQueueSize: s.MaxQueueSize,
		MMin:         1,
		MMax:         256,
		Oracle:       oracle,
	}
}

// TestFormulaGuidedParity reproduces every formula_guided M_chosen and calls
// value in paper/data/eval_results.json from the Go onset search.
func TestFormulaGuidedParity(t *testing.T) {
	var golden evalResults
	if err := json.Unmarshal(readJSON(t, "paper", "data", "eval_results.json"), &golden); err != nil {
		t.Fatalf("parse eval_results.json: %v", err)
	}

	// Load scenario params for both sets, keyed by name.
	scen := map[string]parityScenario{} // name -> params (names are unique across sets)
	for _, f := range []string{"scenarios.json", "scenarios_benchmark.json"} {
		var sf parityScenarioFile
		if err := json.Unmarshal(readJSON(t, "nous", f), &sf); err != nil {
			t.Fatalf("parse %s: %v", f, err)
		}
		for _, s := range sf.Scenarios {
			scen[s.Name] = s
		}
	}

	// cache path differs by set.
	cachePath := func(set, name string) []string {
		if set == "benchmark" {
			return []string{"nous", "cache", "bench", name + ".json"}
		}
		return []string{"nous", "cache", "truth-" + name + ".json"}
	}

	checked := 0
	for _, g := range golden.Records {
		if g.Strategy != "formula_guided" {
			continue
		}
		s, ok := scen[g.Scenario]
		if !ok {
			t.Fatalf("scenario %q not found in scenario files", g.Scenario)
		}
		var cache truthCache
		if err := json.Unmarshal(readJSON(t, cachePath(g.Set, g.Scenario)...), &cache); err != nil {
			t.Fatalf("parse cache for %s/%s: %v", g.Set, g.Scenario, err)
		}

		res, err := optimizerFor(s, cacheOracle(&cache)).Find()
		if err != nil {
			t.Fatalf("Find %s/%s: %v", g.Set, g.Scenario, err)
		}
		if res.Concurrency != g.MChosen {
			t.Errorf("%s/%s: M_chosen got %d, want %d", g.Set, g.Scenario, res.Concurrency, g.MChosen)
		}
		if res.Calls != g.Calls {
			t.Errorf("%s/%s: calls got %d, want %d", g.Set, g.Scenario, res.Calls, g.Calls)
		}
		if res.Feasible != g.Feasible {
			t.Errorf("%s/%s: feasible got %v, want %v", g.Set, g.Scenario, res.Feasible, g.Feasible)
		}
		checked++
	}
	if checked != 36 {
		t.Errorf("checked %d formula_guided records, want 36", checked)
	}
}
```

- [ ] **Step 2: Run the parity test**

Run: `go test ./pkg/analyzer/ -run TestFormulaGuidedParity -v`
Expected: PASS — 36 records reproduced (M_chosen, calls, feasible all match). The 5 infeasible scenarios (bench-005/013/022/028/029) assert `M=1, calls=0, feasible=false`; `unbounded`/bench-015/016/021 assert `M=256, calls=2`.

- [ ] **Step 3: Commit**

```bash
git add pkg/analyzer/concurrency_parity_test.go
git commit -m "test: golden parity vs campaign formula_guided results (#18)"
```

---

## Task 5: `POST /optimize` REST endpoint

**Files:**
- Modify: `pkg/service/analyzer.go`
- Test: `pkg/service/optimize_test.go`

- [ ] **Step 1: Write the failing endpoint test**

Create `pkg/service/optimize_test.go`:

```go
package service

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func postJSON(t *testing.T, a *Analyzer, path string, body any) *httptest.ResponseRecorder {
	t.Helper()
	b, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	req := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	a.router.ServeHTTP(w, req)
	return w
}

func TestOptimizeEndpointBaseline(t *testing.T) {
	gin.SetMode(gin.TestMode)
	a := NewAnalyzer()

	pd := ProblemData{
		MaxBatchSize: 256, MaxQueueSize: 128,
		AvgInputTokens: 256, AvgOutputTokens: 1024,
		Alpha: 8, Beta: 0.033, Gamma: 0.000333,
		TargetTTFT: 60, TargetITL: 20,
	}
	w := postJSON(t, a, "/optimize", pd)
	if w.Code != http.StatusOK {
		t.Fatalf("status got %d, want 200; body=%s", w.Code, w.Body.String())
	}
	var out OptimizeData
	if err := json.Unmarshal(w.Body.Bytes(), &out); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}
	if !out.Feasible {
		t.Error("baseline should be feasible")
	}
	if out.Concurrency < 1 || out.Concurrency > 256 {
		t.Errorf("concurrency %d out of [1,256]", out.Concurrency)
	}
	if out.Throughput <= 0 {
		t.Errorf("throughput should be > 0, got %v", out.Throughput)
	}
}

func TestOptimizeEndpointRejectsInvalid(t *testing.T) {
	gin.SetMode(gin.TestMode)
	a := NewAnalyzer()
	pd := ProblemData{MaxBatchSize: 0} // invalid: maxBatchSize must be > 0
	w := postJSON(t, a, "/optimize", pd)
	if w.Code != http.StatusBadRequest {
		t.Errorf("status got %d, want 400", w.Code)
	}
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `go test ./pkg/service/ -run TestOptimizeEndpoint -v`
Expected: FAIL — `undefined: OptimizeData` and route returns 404 (so the baseline subtest's status assertion fails).

- [ ] **Step 3: Add `OptimizeData`, the handler, and register the route**

In `pkg/service/analyzer.go`, add the response struct after `AnalysisData` (around line 36):

```go
// optimal-concurrency output data
type OptimizeData struct {
	Concurrency  int     `json:"concurrency"`  // M*: min concurrency for near-peak throughput under SLO
	Throughput   float32 `json:"throughput"`   // f(M*) (requests/sec)
	AvgRespTime  float32 `json:"avgRespTime"`  // average response time at M* (msec)
	AvgWaitTime  float32 `json:"avgWaitTime"`  // average queueing time at M* (msec)
	AvgNumInServ float32 `json:"avgNumInServ"` // average number of requests in service at M*
	AvgTTFT      float32 `json:"avgTTFT"`      // average time to first token at M* (msec)
	AvgITL       float32 `json:"avgITL"`       // average inter-token latency at M* (msec)
	MaxRPS       float32 `json:"maxRPS"`       // maximum throughput at M* (requests/sec)
	MITL         int     `json:"M_ITL"`        // closed-form ITL-binding bracket
	MTPF         int     `json:"M_TPF"`        // closed-form TTFT-prefill-binding bracket
	Calls        int     `json:"oracleCalls"`  // feasible oracle calls
	Feasible     bool    `json:"feasible"`
}
```

Register the route in `NewAnalyzer()` (after the `/target` line):

```go
	analyzer.router.POST("/optimize", optimize)
```

Add the handler (after the `target` handler, before `CreateQueueAnalyzer`):

```go
// find minimum concurrency for near-peak throughput under SLO targets
func optimize(c *gin.Context) {
	pd := ProblemData{}
	if err := c.BindJSON(&pd); err != nil {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "binding error: " + err.Error()})
		return
	}
	if !IsValid(&pd) {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "data error: invalid input data"})
		return
	}

	// maxBatchSize is interpreted as the search upper bound m_max.
	queueAnalyzer := CreateQueueAnalyzer(&pd)
	if queueAnalyzer == nil {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "NewLLMQueueAnalyzer() failed"})
		return
	}

	targetPerf := &analyzer.TargetPerf{
		TargetTTFT: pd.TargetTTFT,
		TargetITL:  pd.TargetITL,
		TargetTPS:  0, // not used in this service
	}
	result, err := queueAnalyzer.OptimalConcurrency(targetPerf)
	if err != nil {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "OptimalConcurrency() failed: " + err.Error()})
		return
	}

	data := &OptimizeData{
		Concurrency: result.Concurrency,
		Throughput:  result.Throughput,
		MITL:        result.MITL,
		MTPF:        result.MTPF,
		Calls:       result.Calls,
		Feasible:    result.Feasible,
	}
	if result.Metrics != nil {
		data.AvgRespTime = result.Metrics.AvgRespTime
		data.AvgWaitTime = result.Metrics.AvgWaitTime
		data.AvgNumInServ = result.Metrics.AvgNumInServ
		data.AvgTTFT = result.Metrics.AvgTTFT
		data.AvgITL = result.Metrics.AvgTokenTime
		data.MaxRPS = result.Metrics.MaxRate
	}
	c.IndentedJSON(http.StatusOK, data)
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `go test ./pkg/service/ -run TestOptimizeEndpoint -v`
Expected: PASS (2 subtests).

- [ ] **Step 5: Commit**

```bash
git add pkg/service/analyzer.go pkg/service/optimize_test.go
git commit -m "feat: POST /optimize endpoint (#18)"
```

---

## Task 6: `demos/concurrency` demo program

**Files:**
- Create: `demos/concurrency/main.go`

- [ ] **Step 1: Write the demo**

Create `demos/concurrency/main.go`:

```go
package main

import (
	"fmt"

	"github.com/llm-inferno/queue-analysis/pkg/analyzer"
)

func main() {
	// queue configuration (maxBatchSize is the search upper bound m_max)
	config := &analyzer.Configuration{
		MaxBatchSize: 256,
		MaxQueueSize: 128,
		ServiceParms: &analyzer.ServiceParms{
			Alpha: 8,
			Beta:  0.033,
			Gamma: 0.000333,
		},
	}
	requestSize := &analyzer.RequestSize{
		AvgInputTokens:  256,
		AvgOutputTokens: 1024,
	}
	targetPerf := &analyzer.TargetPerf{
		TargetTTFT: 60,
		TargetITL:  20,
	}

	qa, err := analyzer.NewLLMQueueAnalyzer(config, requestSize)
	if err != nil {
		fmt.Printf("NewLLMQueueAnalyzer failed: %v\n", err)
		return
	}

	res, err := qa.OptimalConcurrency(targetPerf)
	if err != nil {
		fmt.Printf("OptimalConcurrency failed: %v\n", err)
		return
	}

	fmt.Println()
	fmt.Printf("config=%v\n", config)
	fmt.Printf("requestSize=%v\n", requestSize)
	fmt.Printf("targets=%v\n", targetPerf)
	fmt.Println()
	fmt.Printf("optimal concurrency M* = %d  (feasible=%v)\n", res.Concurrency, res.Feasible)
	fmt.Printf("closed-form brackets: M_ITL=%d, M_TPF=%d\n", res.MITL, res.MTPF)
	fmt.Printf("anchor f(m_max)=%.4f, throughput at M*=%.4f req/s\n", res.AnchorThroughput, res.Throughput)
	fmt.Printf("oracle calls=%d, probes=%v\n", res.Calls, res.Probes)
	if res.Metrics != nil {
		fmt.Printf("metrics at M*: %v\n", res.Metrics)
	}
	fmt.Println()
}
```

- [ ] **Step 2: Build and run the demo**

Run: `go run ./demos/concurrency/`
Expected: prints a feasible `M*` in [1, 256] with non-zero throughput, the brackets, and the probe sequence (no panic, no error).

- [ ] **Step 3: Verify the whole module builds and all tests pass**

Run: `go build ./... && go test ./...`
Expected: clean build; all packages PASS (including the parity test).

- [ ] **Step 4: Commit**

```bash
git add demos/concurrency/main.go
git commit -m "feat: optimal-concurrency demo (#18)"
```

---

## Self-Review

**Spec coverage:**
- Core `ConcurrencyOptimizer` + `Find` + injectable oracle → Tasks 1–2.
- Closed-form `M_ITL`/`M_TPF` via existing primitives → Task 2 (`closedFormBrackets`).
- High anchor, threshold `(1−ε/2)f*`, `lo/hi/3U` bracket, `MaxIters=6` bisection, infeasible→`m_min` → Task 2 (`Find`), faithful to the canonical `formula_guided.py`.
- Confirmatory call vs `Metrics` gating (default-oracle only) → Task 2 (`oracleIsDefault`).
- `LLMQueueAnalyzer.OptimalConcurrency` method → Task 3.
- `POST /optimize` + `OptimizeData` (with `AvgRespTime`/`AvgWaitTime`, `AnalysisData`-aligned order) → Task 5.
- Demo → Task 6.
- Unit tests (synthetic curves, infeasible→`MMin`, unbounded→`MMax` in 2 calls) → Tasks 1–2; golden parity over 36 records → Task 4.
- Constants default to ε=0.02, MaxIters=6, bounds [1,256] → Task 1.

**Placeholder scan:** none — every code/test/command step is concrete.

**Type consistency:** `ConcurrencyOptimizer`, `ConcurrencyResult`, `ConcurrencyOracle`, `largestFeasibleBatch`, `onsetSearch`, `closedFormBrackets`, `Find`, `defaultOracle`, `sizeAt`, `OptimalConcurrency`, `OptimizeData` are used with identical names/signatures across tasks. `OptimizeData` fields match the handler assignments in Task 5; `ConcurrencyResult` fields match their reads in Tasks 4–6.
