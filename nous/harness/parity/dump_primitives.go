// Command dump_primitives emits analyzer service-time primitives for a fixed
// set of (B, params) tuples so the Python port in nous/harness/formulas.py can
// be parity-checked. Read-only: imports the analyzer package, calls only
// exported methods. Run with `go run ./nous/harness/parity`.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/llm-inferno/queue-analysis/pkg/analyzer"
)

// maxNumTokens is fixed at the analyzer's DefaultMaxNumTokens. /target never
// overrides it, so formulas.py treats it as the constant 8192; the fixture must
// use the same value or the nc parity check would compare against a budget the
// Python port never sees.
const maxNumTokens = 8192

type tuple struct {
	B     int     `json:"B"`
	Alpha float32 `json:"alpha"`
	Beta  float32 `json:"beta"`
	Gamma float32 `json:"gamma"`
	NIn   int     `json:"AvgInputTokens"`
	MOut  int     `json:"AvgOutputTokens"`
}

type record struct {
	tuple
	Nc       int     `json:"nc"`
	IterTime float32 `json:"iter_time"` // IterationTime(B), nc=1
	Prefill  float32 `json:"prefill"`   // PrefillTime(B),   nc=1
	Itl      float32 `json:"itl"`       // DecodeTime(B),    nc=1
}

func main() {
	tuples := []tuple{
		// nc=1 cases: at MaxNumTokens=8192 the per-prefill chunk threshold far
		// exceeds these batch sizes for the given token counts, so nc=1. These
		// validate the service-time arithmetic against the exported nc=1 shims.
		{B: 1, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 256, MOut: 1024},
		{B: 40, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 256, MOut: 1024},
		{B: 80, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 256, MOut: 1024},
		{B: 128, Alpha: 16, Beta: 0.067, Gamma: 0.000667, NIn: 256, MOut: 1024},
		{B: 200, Alpha: 4, Beta: 0.017, Gamma: 0.000167, NIn: 64, MOut: 128},
		{B: 50, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 1024, MOut: 256},
		// nc>1 cases: high AvgInputTokens with low AvgOutputTokens drives the
		// chunk threshold below the batch size even at the production budget of
		// 8192 (this is the L_in=4096 corner of the benchmark grid). These
		// validate the chunk-table logic that the nc=1 shims cannot exercise.
		{B: 128, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 4096, MOut: 64},
		{B: 200, Alpha: 8, Beta: 0.033, Gamma: 0.000333, NIn: 4096, MOut: 64},
	}
	out := make([]record, 0, len(tuples))
	for _, t := range tuples {
		sp := &analyzer.ServiceParms{Alpha: t.Alpha, Beta: t.Beta, Gamma: t.Gamma}
		rs := &analyzer.RequestSize{
			AvgInputTokens:  float32(t.NIn),
			AvgOutputTokens: float32(t.MOut),
		}
		cfg := &analyzer.Configuration{
			MaxBatchSize: t.B, MaxQueueSize: 128, MaxNumTokens: maxNumTokens, ServiceParms: sp,
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
