# Overload Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow `Analyze()` to accept arrival rates above the current stability cap, returning valid metrics with a new `OfferedRate` field so callers can observe overload (dropped traffic = OfferedRate − Throughput) instead of receiving a nil/error.

**Architecture:** The underlying finite-K birth-death model already handles any arrival rate correctly — excess load is absorbed as blocking probability `p[K]`, and throughput saturates at the server capacity. The only change needed in the core is removing the `requestRate > rateRange.Max` guard and recording `OfferedRate` in the returned metrics. Downstream repos need only minor cleanup: the duplicate guard in model-trainer is removed, the service layer exposes the new field, and documentation is updated.

**Tech Stack:** Go 1.22+, Gin HTTP framework, `github.com/llm-inferno/queue-analysis` as the shared library.

---

## File Map

| File | Change |
|---|---|
| `queue-analysis/pkg/analyzer/queueanalyzer.go` | Add `OfferedRate` to `AnalysisMetrics`; remove overload guard in `Analyze()` |
| `queue-analysis/pkg/service/analyzer.go` | Add `OfferedRPS` to `AnalysisData`; populate in `/solve` handler |
| `queue-analysis/demos/overload/main.go` | Remove the manual guard-bypass; call `Analyze()` directly |
| `queue-analysis/pkg/analyzer/README.md` | Document overload semantics and new `OfferedRate` field |
| `model-trainer/pkg/core/approx.go` | Remove duplicate `requestRate > rateRange.Max` guard |
| `server-sim/queue-analysis-evaluator/handler.go` | Remove now-dead `err != nil` branch for overload |

---

### Task 1: Add `OfferedRate` to `AnalysisMetrics` and remove the guard

**Files:**
- Modify: `queue-analysis/pkg/analyzer/queueanalyzer.go`

- [ ] **Step 1: Add `OfferedRate` field to `AnalysisMetrics`**

In `queueanalyzer.go`, the struct starts at line 59. Add the new field after `Throughput`:

```go
type AnalysisMetrics struct {
	OfferedRate    float32 // offered arrival rate (requests/sec); equals Throughput when not overloaded
	Throughput     float32 // effective throughput / goodput (requests/sec)
	AvgRespTime    float32 // average request response time (aka latency) (msec)
	AvgWaitTime    float32 // average request queueing time (msec)
	AvgNumInServ   float32 // average number of requests in service
	AvgPrefillTime float32 // average request prefill time (msec)
	AvgTokenTime   float32 // average token decode time (msec)
	AvgTTFT        float32 // average time to first token (msec)
	MaxRate        float32 // maximum throughput (requests/sec)
	Rho            float32 // utilization
}
```

- [ ] **Step 2: Remove the overload guard and set `OfferedRate` in `Analyze()`**

Replace the guard block and the metrics return in `Analyze()` (lines 136–169):

```go
func (qa *LLMQueueAnalyzer) Analyze(requestRate float32) (metrics *AnalysisMetrics, err error) {
	if requestRate <= 0 {
		return nil, fmt.Errorf("invalid request rate %v", requestRate)
	}
	model := qa.Model
	rateRange := qa.RateRange

	//solve model
	model.Solve(requestRate/1000, 1)
	if !model.IsValid() {
		err = fmt.Errorf("invalid model %s", model)
		return nil, err
	}

	// get statistics
	avgNumInServ := model.GetAvgNumInServers()
	avgPrefillTime := qa.ServiceParms.PrefillTime(qa.RequestSize, avgNumInServ)
	avgDecodeTime := (model.GetAvgServTime() - avgPrefillTime) / qa.RequestSize.AvgOutputTokens
	avgTTFT := model.GetAvgWaitTime() + avgPrefillTime + avgDecodeTime

	rho := avgNumInServ / float32(qa.MaxBatchSize)
	rho = min(max(rho, 0), 1)

	// return solution
	metrics = &AnalysisMetrics{
		OfferedRate:    requestRate,
		Throughput:     model.GetThroughput() * 1000,
		AvgRespTime:    model.GetAvgRespTime(),
		AvgWaitTime:    model.GetAvgWaitTime(),
		AvgNumInServ:   avgNumInServ,
		AvgPrefillTime: avgPrefillTime,
		AvgTokenTime:   avgDecodeTime,
		AvgTTFT:        avgTTFT,
		MaxRate:        rateRange.Max,
		Rho:            rho,
	}
	return metrics, nil
}
```

- [ ] **Step 3: Build to confirm no compile errors**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis && go build ./...
```

Expected: no output (success).

- [ ] **Step 4: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add pkg/analyzer/queueanalyzer.go
git commit -m "feat(analyzer): handle overload gracefully, add OfferedRate to AnalysisMetrics

Remove the requestRate > rateRange.Max guard in Analyze(). The finite-K
birth-death model is well-defined for any arrival rate: excess load
increases blocking probability p[K] and throughput saturates naturally.
Add OfferedRate field so callers can compute dropped traffic as
OfferedRate - Throughput."
```

---

### Task 2: Expose `OfferedRPS` in the queue-analysis REST service layer

**Files:**
- Modify: `queue-analysis/pkg/service/analyzer.go`

- [ ] **Step 1: Add `OfferedRPS` to `AnalysisData`**

In `analyzer.go`, the `AnalysisData` struct (lines 25–35). Add the new field:

```go
type AnalysisData struct {
	OfferedRPS    float32 `json:"offeredRPS"`    // offered arrival rate (requests/sec)
	Throughput    float32 `json:"throughput"`    // effective throughput (requests/sec)
	AvgRespTime   float32 `json:"avgRespTime"`   // average response time (sec)
	AvgWaitTime   float32 `json:"avgWaitTime"`   // average queueing time (sec)
	AvgNumInServ  float32 `json:"avgNumInServ"`  // average number of requests in system
	AvgTTFT       float32 `json:"avgTTFT"`       // average time to first token (msec)
	AvgITL        float32 `json:"avgITL"`        // average inter-token latency (msec)
	MaxRPS        float32 `json:"maxRPS"`        // maximum throughput (requests/sec)
	RPSTargetTTFT float32 `json:"RPSTargetTTFT"` // throughput to achieve target TTFT (requests/sec)
	RPSTargetITL  float32 `json:"RPSTargetITL"`  // throughput to achieve target ITL (requests/sec)
}
```

- [ ] **Step 2: Populate `OfferedRPS` in the `/solve` handler and remove the now-dead error branch**

Replace the `solve` handler's `Analyze` call block and result construction (lines 96–112):

```go
	// analyze queue under a given load
	metrics, err := queueAnalyzer.Analyze(pd.RPS)
	if err != nil {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "Analyze() failed: " + err.Error()})
		return
	}

	// return solution
	analysisData := &AnalysisData{
		OfferedRPS:   metrics.OfferedRate,
		Throughput:   metrics.Throughput,
		AvgRespTime:  metrics.AvgRespTime,
		AvgWaitTime:  metrics.AvgWaitTime,
		AvgNumInServ: metrics.AvgNumInServ,
		AvgTTFT:      metrics.AvgTTFT,
		AvgITL:       metrics.AvgTokenTime,
		MaxRPS:       metrics.MaxRate,
	}
	c.IndentedJSON(http.StatusOK, analysisData)
```

Note: the `if err != nil` branch is kept because `Analyze()` still returns an error for `requestRate <= 0`.

- [ ] **Step 3: Build**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis && go build ./...
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add pkg/service/analyzer.go
git commit -m "feat(service): expose OfferedRPS in /solve response"
```

---

### Task 3: Clean up the overload demo

**Files:**
- Modify: `queue-analysis/demos/overload/main.go`

- [ ] **Step 1: Rewrite the demo to call `Analyze()` directly**

Replace the entire file content — the guard-bypass block is no longer needed:

```go
package main

import (
	"fmt"

	"github.com/llm-inferno/queue-analysis/pkg/analyzer"
)

func main() {
	config := &analyzer.Configuration{
		MaxBatchSize: 256,
		MaxQueueSize: 0,
		ServiceParms: &analyzer.ServiceParms{
			Alpha: 6.71134,
			Beta:  0.02417,
			Gamma: 0.04538 * 1e-3,
		},
	}
	requestSize := &analyzer.RequestSize{
		AvgInputTokens:  4096,
		AvgOutputTokens: 1024,
	}

	qa, err := analyzer.NewLLMQueueAnalyzer(config, requestSize)
	if err != nil {
		fmt.Printf("NewLLMQueueAnalyzer failed: %v\n", err)
		return
	}

	maxRate := qa.RateRange.Max
	fmt.Printf("RateRange: min=%.4f  max=%.4f req/sec\n\n", qa.RateRange.Min, maxRate)

	factors := []float32{0.5, 0.8, 0.95, 1.0, 1.05, 1.2, 1.5, 2.0}

	fmt.Printf("%-8s %-12s %-12s %-12s %-12s %-12s %-10s\n",
		"factor", "offered(rps)", "throughput", "dropped(rps)", "TTFT(ms)", "ITL(ms)", "rho")
	fmt.Println("-----------------------------------------------------------------------------------------------")

	for _, f := range factors {
		rate := f * maxRate
		metrics, err := qa.Analyze(rate)
		if err != nil {
			fmt.Printf("%-8.2f %-12.4f error: %v\n", f, rate, err)
			continue
		}
		dropped := metrics.OfferedRate - metrics.Throughput
		fmt.Printf("%-8.2f %-12.4f %-12.4f %-12.4f %-12.2f %-12.4f %-10.4f\n",
			f, metrics.OfferedRate, metrics.Throughput, dropped,
			metrics.AvgTTFT, metrics.AvgTokenTime, metrics.Rho)
	}
}
```

- [ ] **Step 2: Run the demo to confirm correct output**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis && go run demos/overload/main.go
```

Expected: table with 8 rows, no errors, dropped(rps) > 0 for factors above 1.0.

- [ ] **Step 3: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add demos/overload/main.go
git commit -m "demo: simplify overload demo now that Analyze() handles high rates natively"
```

---

### Task 4: Remove duplicate overload guard in model-trainer

**Files:**
- Modify: `model-trainer/pkg/core/approx.go`

Context: `approx.go` has its own wrapper `Analyze()` that duplicates the `requestRate > rateRange.Max` check at lines 14–18. That guard is now redundant and misleading. The `denom <= 0` stability check on lines 30–34 is independent math for the approximation formula and must be kept.

- [ ] **Step 1: Remove the redundant guard**

Replace lines 10–18 (the function opening and the rate guard):

```go
func Analyze(qa *analyzer.LLMQueueAnalyzer, requestRate float32) (metrics *analyzer.AnalysisMetrics, err error) {
	if requestRate <= 0 {
		return nil, fmt.Errorf("invalid request rate %v", requestRate)
	}
	rateRange := qa.RateRange
```

(Remove the block: `if requestRate > rateRange.Max { ... return nil, err }`)

- [ ] **Step 2: Build model-trainer**

```bash
cd /Users/tantawi/Projects/llm-inferno/model-trainer && go build ./...
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/model-trainer
git add pkg/core/approx.go
git commit -m "refactor(core): remove redundant overload guard in Analyze wrapper

queue-analysis Analyze() now handles rates above rateRange.Max natively."
```

---

### Task 5: Remove dead error branch in server-sim queue-analysis-evaluator

**Files:**
- Modify: `server-sim/queue-analysis-evaluator/handler.go`

Context: lines 56–60 return HTTP 500 when `Analyze()` errors. With the overload guard gone, this branch can only be reached for `RPS <= 0` (already validated upstream as `RPS >= 0` by the caller). The branch should stay to handle genuine errors, but the comment should be updated.

- [ ] **Step 1: Update the error message to reflect that this is no longer triggered by overload**

Replace lines 56–60:

```go
		metrics, err := qa.Analyze(pd.RPS)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "analyze: " + err.Error()})
			return
		}
```

No functional change — just verify it compiles and note in the commit that overload now produces valid metrics instead of a 500.

- [ ] **Step 2: Build server-sim**

```bash
cd /Users/tantawi/Projects/llm-inferno/server-sim && go build ./...
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/server-sim
git add queue-analysis-evaluator/handler.go
git commit -m "fix(evaluator): overload no longer returns HTTP 500; Analyze() handles it natively

Previously, a request rate above rateRange.Max caused a 500 response.
Now the analytical model absorbs overload via finite-K blocking and
returns valid metrics with Throughput < OfferedRate."
```

---

### Task 6: Update documentation

**Files:**
- Modify: `queue-analysis/pkg/analyzer/README.md`

- [ ] **Step 1: Add overload section and document `OfferedRate`**

Append after the "Units of performance metrics" section:

```markdown
## Overload behavior

When the offered arrival rate exceeds the server capacity (`RateRange.Max`),
`Analyze()` still returns valid metrics rather than an error. The finite
queue naturally absorbs excess load: requests are dropped when the queue
is full, and throughput saturates at the server capacity.

- `OfferedRate`: the arrival rate passed to `Analyze()` (requests/sec)
- `Throughput`: the accepted / departure rate (requests/sec); always ≤ `OfferedRate`
- Dropped traffic = `OfferedRate − Throughput`
- `Rho` approaches 1 as the server saturates

`Analyze()` returns an error only for invalid input (`requestRate ≤ 0`).
```

Also update the metric definitions list to include `OfferedRate`:

```markdown
- OfferedRate: offered arrival rate (requests/sec); equals Throughput when not overloaded
- Throughput: effective departure rate / goodput (requests/sec)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add pkg/analyzer/README.md
git commit -m "docs(analyzer): document overload handling and OfferedRate field"
```

---

## Self-Review

**Spec coverage:**
- [x] Remove overload guard from `Analyze()` → Task 1
- [x] Add `OfferedRate` to `AnalysisMetrics` → Task 1
- [x] Expose in service REST layer → Task 2
- [x] Clean up demo → Task 3
- [x] model-trainer duplicate guard removed → Task 4
- [x] server-sim evaluator handler verified → Task 5
- [x] Documentation → Task 6
- model-tuner and optimizer-light callers: their `if err != nil` blocks remain valid for the `requestRate <= 0` error case; no changes required.

**Placeholder scan:** None found.

**Type consistency:** `OfferedRate float32` in `AnalysisMetrics` ↔ `OfferedRPS float32` in `AnalysisData` (different names by design: the service layer uses the RPS naming convention already established by `MaxRPS`, `RPSTargetTTFT`, etc.).
