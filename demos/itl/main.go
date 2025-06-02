package main

import (
	"fmt"

	"github.com/llm-inferno/queue-analysis/pkg/queue"
	"github.com/llm-inferno/queue-analysis/pkg/utils"
)

func main() {

	// Service: tau(n) = alpha + n * beta
	var alpha float32 = 11.09 // msec
	var beta float32 = 0.6244 // msec

	// SLO for average request waiting in secs
	targetAvgQueueingSeconds := float32(1.0)

	// limits
	var delta float32 = 0.001

	fmt.Println("Parameters:")
	fmt.Printf("alpha=%v; beta=%v; ", alpha, beta)
	fmt.Printf("targetAvgQueueingSeconds=%v \n", targetAvgQueueingSeconds)
	fmt.Println()

	// range of batch size and number of tokens per request
	batchSizes := []int{32, 64, 128, 256}
	tokens := []int{128, 256, 512, 1024}

	for _, maxBatchSize := range batchSizes {
		fmt.Printf("maxBatchSize=%d \n", maxBatchSize)
		fmt.Println("\t numTokens \t capacityRPS")
		var occupancyUpperBound int = 1000 * maxBatchSize

		for _, numTokens := range tokens {
			targetWaitTime := 1000 * targetAvgQueueingSeconds / float32(numTokens)

			// calculate state-dependent service rate
			servRate := make([]float32, maxBatchSize)
			for n := 1; n <= maxBatchSize; n++ {
				servRate[n-1] = float32(n) / (alpha + beta*float32(n))
			}

			model := queue.NewMM1ModelStateDependent(occupancyUpperBound, servRate)

			// bounds on arrival rate
			lambdaMin := servRate[0] * delta
			lambdaMax := servRate[maxBatchSize-1] * (1 - delta)
			utils.Model = model

			lambdaStar, ind, err := utils.BinarySearch(lambdaMin, lambdaMax, targetWaitTime, utils.EvalWaitingTime)

			if err == nil {
				model.Solve(lambdaStar, 1)
				capacityRPS := 1000 * lambdaStar / float32(numTokens)
				fmt.Printf("\t %d \t %v", numTokens, capacityRPS)
				if ind != 0 {
					fmt.Printf("\t (ind=%d)", ind)
				}
				fmt.Println()

				// fmt.Println("Model details:")
				// fmt.Printf("targetWaitTime=%v, lambdaMin=%v; lambdaMax=%v; lambdaStar=%v; indicator=%d \n",
				// 	targetWaitTime, lambdaMin, lambdaMax, lambdaStar, ind)
				// fmt.Println(model)
			} else {
				fmt.Println(err.Error())
			}
		}
	}

}
