package main

import (
	"fmt"

	"github.com/llm-inferno/queue-analysis/pkg/queue"
)

func main() {
	lambda := float32(7.5)
	mu := float32(1.0)
	K := 10

	model := queue.NewMM1KModel(K)
	model.Solve(lambda, mu)
	fmt.Println(model)
}
