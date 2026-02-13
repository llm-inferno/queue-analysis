package main

import (
	"fmt"

	"github.com/llm-inferno/queue-analysis/pkg/analyzer"
)

func main() {
	L := 4096
	K := 512
	M := 4200
	N := 256

	cfg := &analyzer.Configuration{
		MaxBatchSize: N,
		MaxNumTokens: M,
	}

	req := &analyzer.RequestSize{
		AvgInputTokens:  float32(L),
		AvgOutputTokens: float32(K),
	}

	batchSize := analyzer.CalculateMaxBatchSizeForNumIterationsPerPrefill(cfg, req, 1)
	println("Calculated max batch size for one iteration:", batchSize)

	batchSizes := analyzer.CalculateBatchSizes(cfg, req)
	fmt.Printf("Calculated batch sizes: %v\n", batchSizes)

	numIters := analyzer.NumIterationsPerPrefill(cfg, req)
	fmt.Printf("Number of iterations per prefill: %v\n", numIters)
}
