package main

import (
	"fmt"

	"github.com/llm-inferno/queue-analysis/pkg/queue"
)

func main() {

	// Service: tau(n) = alpha + n * beta
	var alpha float32 = 12.251 //10.875 //9.1689 //8.989 //11.09 // msec
	var beta float32 = 0.212   //0.8772  //0.6504  //0.612 //0.6244 // msec

	// max batch size
	var maxBatchSize int = 250

	// avg number of tokens per request
	var minTokens int = 256
	var maxTokens int = 2048
	var tokens int = (minTokens + maxTokens) / 2
	// tokens := 256

	var occupancyUpperBound int = 100 * maxBatchSize

	// calculate state-dependent service rate
	servRate := make([]float32, maxBatchSize)
	for n := 1; n <= maxBatchSize; n++ {
		servRate[n-1] = float32(n) / (float32(tokens) * (alpha + beta*float32(n)))
	}

	// limits
	var delta float32 = 0.001
	lambdaMax := servRate[maxBatchSize-1] * (1 - delta)
	maxRPM := lambdaMax * 1000 * 60

	fmt.Println("Parameters:")
	fmt.Printf("maxBatchSize=%d; avgTokens=%d \n", maxBatchSize, tokens)
	fmt.Printf("alpha=%v; beta=%v \n", alpha, beta)
	fmt.Printf("maxRPM=%.2f \n", maxRPM)
	fmt.Println()

	model := queue.NewMM1ModelStateDependent(occupancyUpperBound, servRate)

	// requests per min
	var rpmMin float32 = 25
	var rpmMax float32 = maxRPM
	var rpmInc float32 = 25

	fmt.Println("rpm \t tput \t avgRT(sec) \t avgWT(sec) \t avgBatch \t ITL(msec)")
	r := rpmMin
	for r <= rpmMax {
		// request per msec
		lambda := r / 1000 / 60
		model.Solve(lambda, 1)

		tput := model.GetThroughput() * 1000 * 60
		avgRespTime := model.GetAvgRespTime() / 1000
		avgWaitTime := model.GetAvgWaitTime() / 1000
		avgNumInServ := model.GetAvgNumInServers()
		avgTokenTime := model.GetAvgServTime() / float32(tokens)

		fmt.Printf("%5.1f \t %5.1f \t %6.2f \t %6.2f \t %6.2f \t %6.2f \n",
			r, tput, avgRespTime, avgWaitTime, avgNumInServ, avgTokenTime)
		// fmt.Println(model)

		r += rpmInc
	}
}
