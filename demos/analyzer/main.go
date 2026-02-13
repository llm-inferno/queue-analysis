package main

import (
	"fmt"

	"github.com/llm-inferno/queue-analysis/pkg/analyzer"
)

func main() {

	// queue configuration
	maxBatchSize := 256
	maxQueueSize := 0

	// prefill and decode parameters
	alpha := float32(6.71134)
	beta := float32(0.02417)
	gamma := float32(0.04538 * 1e-3)

	// request rate
	requestRate := float32(2.16)

	// request size
	avgInputTokens := float32(4096)
	avgOutputTokens := float32(1024)

	// target values
	targetTTFT := float32(140)
	targetITL := float32(16.5)
	targetTPS := float32(8 * 1024)

	// create queue analyzer
	config := &analyzer.Configuration{
		MaxBatchSize: maxBatchSize,
		MaxQueueSize: maxQueueSize,
		ServiceParms: &analyzer.ServiceParms{
			Alpha: alpha,
			Beta:  beta,
			Gamma: gamma,
		},
	}

	requestSize := &analyzer.RequestSize{
		AvgInputTokens:  avgInputTokens,
		AvgOutputTokens: avgOutputTokens,
	}

	targetPerf := &analyzer.TargetPerf{
		TargetTTFT: targetTTFT,
		TargetITL:  targetITL,
		TargetTPS:  targetTPS,
	}

	fmt.Println()
	fmt.Printf("configuration=%v\n", config)
	fmt.Printf("requestSize=%v\n", requestSize)
	fmt.Println()

	queueAnalyzer, err := analyzer.NewLLMQueueAnalyzer(config, requestSize)
	if err != nil {
		fmt.Printf("NewLLMQueueAnalyzer() failed: %v\n", err)
		return
	}

	// analyze queue under a given load
	fmt.Printf("Analyzing at request rate = %v req/sec ...\n", requestRate)
	metrics, err := queueAnalyzer.Analyze(requestRate)
	if err != nil {
		fmt.Printf("Analyze() %v\n", err)
		return
	}
	fmt.Printf("model=%v\n", queueAnalyzer.Model)
	fmt.Printf("metrics=%v\n", metrics)
	fmt.Println()

	// size queue for given targets
	fmt.Printf("Sizing for targets ...\n")
	fmt.Printf("targetPerf=%v\n", targetPerf)
	if targetRate, metrics, targetPerf, err := queueAnalyzer.Size(targetPerf); err != nil {
		fmt.Printf("Size() %v\n", err)
		return
	} else {
		fmt.Printf("achieved=%v\n", targetPerf)
		fmt.Printf("targetRate=%v\n", targetRate)
		fmt.Printf("metrics=%v\n", metrics)
		fmt.Println()
	}
}
