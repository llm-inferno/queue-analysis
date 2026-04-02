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
