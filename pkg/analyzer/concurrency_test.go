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
	// hi=64 reflects the pre-narrowed bracket that Find() computes via
	// the closed-form M_ITL/M_TPF bounds (3*U narrowing); [1,64] converges
	// to exactly 50 in 6 iterations, whereas [1,256] needs 7.
	got := onsetSearch(f, 0.99, 1, 64, 6)
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
