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
