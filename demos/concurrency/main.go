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
