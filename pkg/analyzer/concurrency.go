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
	for B := 1; B <= mMax; B++ {
		if metric(B) <= target {
			best = B
		}
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

// check validates that the required input pointers are set and well-formed.
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
		// Re-solve at M* for full metrics: the ConcurrencyOracle contract
		// returns only throughput, so the default oracle's solve at mStar is
		// not reused here. One extra deterministic solve; acceptable.
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
