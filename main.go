package main

import "github.ibm.com/modeling-analysis/queue-analysis/pkg/service"

// create and run an LLM inference server queue analyzer service
func main() {
	analyzer := service.NewAnalyzer()
	analyzer.Run()
}
