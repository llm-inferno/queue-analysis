package analyzer

import (
	"encoding/json"
	"os"
	"testing"
)

// primitiveTuple mirrors the (B, params) tuples consumed by the Python port's
// parity test in nous/harness/tests/test_formulas.py.
type primitiveTuple struct {
	B     int     `json:"B"`
	Alpha float32 `json:"alpha"`
	Beta  float32 `json:"beta"`
	Gamma float32 `json:"gamma"`
	NIn   int     `json:"AvgInputTokens"`
	MOut  int     `json:"AvgOutputTokens"`
}

type primitiveRecord struct {
	primitiveTuple
	Nc       int     `json:"nc"`
	IterTime float32 `json:"iter_time"`
	Prefill  float32 `json:"prefill"`
	Itl      float32 `json:"itl"`
	Tau      float32 `json:"tau"`
}

// TestGeneratePrimitivesGolden regenerates nous/harness/tests/golden_primitives.json,
// the parity fixture for the Python port in nous/harness/formulas.py.
//
// Unlike the exported IterationTime/PrefillTime/DecodeTime shims (queueanalyzer.go:337-350),
// which hardcode nc=1 and therefore cannot serve as a reference for chunked-prefill
// batch sizes, this white-box test calls the unexported primitives (tIter, prefillNew,
// itlNew, tauNew) at the REAL chunk count nc from NumIterationsPerPrefill. Every emitted
// row — nc=1 and nc>1 — is thus a faithful Go reference.
//
// It is read-only (mutates no analyzer state) and a no-op under a normal `go test`
// run; set GOLDEN_OUT to regenerate the fixture:
//
//	GOLDEN_OUT=nous/harness/tests/golden_primitives.json \
//	    go test ./pkg/analyzer -run TestGeneratePrimitivesGolden
func TestGeneratePrimitivesGolden(t *testing.T) {
	out := os.Getenv("GOLDEN_OUT")
	if out == "" {
		t.Skip("set GOLDEN_OUT to regenerate nous/harness/tests/golden_primitives.json")
	}

	const maxNumTokens = 8192 // analyzer DefaultMaxNumTokens; /target never overrides it

	tuples := []primitiveTuple{
		// nc=1 cases: the per-prefill chunk threshold far exceeds B for these token
		// counts, so nc=1. These also exercise the exported nc=1 shims' arithmetic.
		{B: 1, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 256, MOut: 1024},
		{B: 40, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 256, MOut: 1024},
		{B: 80, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 256, MOut: 1024},
		{B: 128, Alpha: 16, Beta: 0.067, Gamma: 0.000667, NIn: 256, MOut: 1024},
		{B: 200, Alpha: 4, Beta: 0.017, Gamma: 0.000167, NIn: 64, MOut: 128},
		{B: 50, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 1024, MOut: 256},
		// nc>1 cases: high AvgInputTokens with low AvgOutputTokens drives the chunk
		// threshold below B even at the production budget of 8192 (the L_in=4096 corner
		// of the benchmark grid). These cover the chunk-table-dependent service times.
		{B: 128, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 4096, MOut: 64},
		{B: 200, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 4096, MOut: 64},
	}

	recs := make([]primitiveRecord, 0, len(tuples))
	for _, tp := range tuples {
		sp := &ServiceParms{Alpha: tp.Alpha, Beta: tp.Beta, Gamma: tp.Gamma}
		rs := &RequestSize{AvgInputTokens: float32(tp.NIn), AvgOutputTokens: float32(tp.MOut)}
		cfg := &Configuration{
			MaxBatchSize: tp.B, MaxQueueSize: 128, MaxNumTokens: maxNumTokens, ServiceParms: sp,
		}
		nc := NumIterationsPerPrefill(cfg, rs)[tp.B]
		B := float32(tp.B)
		recs = append(recs, primitiveRecord{
			primitiveTuple: tp,
			Nc:             nc,
			IterTime:       tIter(sp, rs, B, nc),
			Prefill:        prefillNew(sp, rs, B, nc),
			Itl:            itlNew(sp, rs, B, nc),
			Tau:            tauNew(sp, rs, tp.B, nc),
		})
	}

	data, err := json.MarshalIndent(recs, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(out, append(data, '\n'), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Logf("wrote %d records to %s", len(recs), out)
}
