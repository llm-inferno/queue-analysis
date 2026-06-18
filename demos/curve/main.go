package main

import (
	"fmt"
	"os"

	"github.com/llm-inferno/queue-analysis/pkg/analyzer"
)

// Generate a delay-throughput curve for a given LLM queue model.
//
// The analyzer computes a stable rate range when the model is built; the upper
// bound RateRange.Max is the maximum sustainable request rate (req/s). We sweep
// the offered rate from 0.05*max to 0.95*max in steps of 0.05*max and report the
// resulting throughput together with the two delay metrics: TTFT (time to first
// token) and ITL (inter-token latency / per-token decode time).
func main() {
	// queue configuration
	config := &analyzer.Configuration{
		MaxBatchSize: 256,
		MaxQueueSize: 128,
		ServiceParms: &analyzer.ServiceParms{
			Alpha: 8,
			Beta:  0.016,
			Gamma: 0.0005,
		},
	}
	requestSize := &analyzer.RequestSize{
		AvgInputTokens:  2048,
		AvgOutputTokens: 1024,
	}

	qa, err := analyzer.NewLLMQueueAnalyzer(config, requestSize)
	if err != nil {
		fmt.Printf("NewLLMQueueAnalyzer failed: %v\n", err)
		return
	}

	maxRate := qa.RateRange.Max // req/s

	// Context goes to stderr so stdout is clean CSV ready for `> curve.csv`.
	fmt.Fprintln(os.Stderr, "# config:", config)
	fmt.Fprintln(os.Stderr, "# requestSize:", requestSize)
	fmt.Fprintf(os.Stderr, "# rateRange (req/s): %v\n", qa.RateRange)

	fmt.Println("frac,offered_rps,throughput_rps,rho,ttft_msec,itl_msec")
	for frac := float32(0.05); frac <= 0.951; frac += 0.05 {
		rate := frac * maxRate
		m, err := qa.Analyze(rate)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Analyze failed at frac=%.2f: %v\n", frac, err)
			continue
		}
		fmt.Printf("%.2f,%.4f,%.4f,%.4f,%.3f,%.3f\n",
			frac, m.OfferedRate, m.Throughput, m.Rho, m.AvgTTFT, m.AvgTokenTime)
	}
}
