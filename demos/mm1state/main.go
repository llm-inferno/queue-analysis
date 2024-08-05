package main

import (
	"fmt"

	"github.ibm.com/tantawi/queue-analysis/pkg/queue"
	"github.ibm.com/tantawi/queue-analysis/pkg/utils"
)

var model *queue.MM1ModelStateDependent

// Limits: N max number in service; K max number in system
// Arrival: constant rate lambda
// Service: avg service time given state n (0 < n <= N) is tau(n) = alpha + n * beta
func main() {
	N := 10
	K := 100
	var alpha float32 = 1.0
	var beta float32 = 0.5

	// calculate state-dependent service rate
	servRate := make([]float32, N)
	for n := 1; n <= N; n++ {
		servRate[n-1] = float32(n) / (alpha + beta*float32(n))
	}

	// (1) Solve for a given lambda
	lambda := float32(1.0)

	model = queue.NewMM1ModelStateDependent(K, servRate)
	model.Solve(lambda, 1)
	fmt.Println(model)
	fmt.Println()

	// (2) Find rate lambda at which the average service time is equal to the target service time
	targetServTime := float32(2.0)

	delta := float32(0.001)
	lambdaMin := servRate[0] * delta
	lambdaMax := servRate[N-1] * (1 - delta)

	lambdaStar, ind, err := utils.BinarySearch(lambdaMin, lambdaMax, targetServTime, EvalServTime)
	if err == nil {
		fmt.Printf("targetServTime=%v, lambdaMin=%v; lambdaMax=%v; lambdaStar=%v; indicator=%d \n",
			targetServTime, lambdaMin, lambdaMax, lambdaStar, ind)
		model.Solve(lambdaStar, 1)
		fmt.Println(model)
	} else {
		fmt.Println(err.Error())
	}
	fmt.Println()

	// (3) Find rate lambda at which the average waiting time is equal to the target waiting time
	targetWaitTime := float32(1.0)

	lambdaStar, ind, err = utils.BinarySearch(lambdaMin, lambdaMax, targetWaitTime, EvalWaitingTime)
	if err == nil {
		fmt.Printf("targetWaitTime=%v, lambdaMin=%v; lambdaMax=%v; lambdaStar=%v; indicator=%d \n",
			targetWaitTime, lambdaMin, lambdaMax, lambdaStar, ind)
		model.Solve(lambdaStar, 1)
		fmt.Println(model)
	} else {
		fmt.Println(err.Error())
	}
}

func EvalServTime(x float32) (float32, error) {
	model.Solve(x, 1)
	if !model.IsValid() {
		return 0, fmt.Errorf("invalid model %v", model)
	}
	return model.GetAvgServTime(), nil
}

// Function used in binary search (target waiting time)
func EvalWaitingTime(x float32) (float32, error) {
	model.Solve(x, 1)
	if !model.IsValid() {
		return 0, fmt.Errorf("invalid model %v", model)
	}
	return model.GetAvgWaitTime(), nil
}

// Function used in binary search (target service time)
