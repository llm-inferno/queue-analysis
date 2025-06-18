package service

import (
	"fmt"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/llm-inferno/queue-analysis/pkg/queue"
	"github.com/llm-inferno/queue-analysis/pkg/utils"
)

// parameters
var delta float32 = 0.001 // small number

// problem input data
type ProblemData struct {
	RPM          float32 `json:"RPM"`          // request arrival rate (requests/min)
	MaxBatchSize int     `json:"maxBatchSize"` // maximum batch size
	AvgNumTokens int     `json:"avgNumTokens"` // average number of tokens per request
	Alpha        float32 `json:"alpha"`        // tau(n) = alpha + n * beta (msec)
	Beta         float32 `json:"beta"`         // tau(n) = alpha + n * beta (msec)
	MaxQueueSize int     `json:"maxQueueSize"` // maximum queue size
	TargetWait   float32 `json:"targetWait"`   // target queueing time (sec)
	TargetITL    float32 `json:"targetITL"`    // target inter-token interval (msec)
}

// analysis solution output data
type AnalysisData struct {
	Throughput    float32 `json:"throughput"`    // effective throughput (requests/min)
	AvgRespTime   float32 `json:"avgRespTime"`   // average response time (sec)
	AvgWaitTime   float32 `json:"avgWaitTime"`   // average queueing time (sec)
	AvgNumInServ  float32 `json:"avgNumInServ"`  // average number of requests in system
	AvgTokenTime  float32 `json:"avgTokenTime"`  // average token time (msec)
	MaxRPM        float32 `json:"maxRPM"`        // maximum throughput (requests/min)
	RMPTargetWait float32 `json:"RMPTargetWait"` // RPM for target queueing time (requests/min)
	RPMTargetITL  float32 `json:"RPMTargetITL"`  // RPM for target ITL (requests/min)
}

// REST server for llm inference server analysis
type Analyzer struct {
	router *gin.Engine
}

// create a new Analyzer
func NewAnalyzer() *Analyzer {
	analyzer := &Analyzer{
		router: gin.Default(),
	}
	analyzer.router.POST("/solve", solve)
	analyzer.router.POST("/target", target)
	return analyzer
}

// start service
func (analyzer *Analyzer) Run() {
	analyzer.router.Run(":8080")
}

// check validity of input data
func IsValid(pd *ProblemData) bool {
	return pd.RPM >= 0 &&
		pd.MaxBatchSize > 0 &&
		pd.AvgNumTokens > 0 &&
		pd.Alpha >= 0 &&
		pd.Beta >= 0 &&
		pd.Alpha+pd.Beta > 0 &&
		pd.MaxQueueSize >= 0 &&
		pd.TargetWait >= 0 &&
		pd.TargetITL >= 0
}

// analyze model given parameters
func analyzeModel(model *queue.MM1ModelStateDependent, avgNumTokens int,
	lambda, maxRPM, lambdaStarWait, lambdaStarService float32) *AnalysisData {

	//solve model
	model.Solve(lambda, 1)

	// get statistics
	tput := model.GetThroughput() * 1000 * 60
	avgRespTime := model.GetAvgRespTime() / 1000
	avgWaitTime := model.GetAvgWaitTime() / 1000
	avgNumInServ := model.GetAvgNumInServers()
	avgTokenTime := model.GetAvgServTime() / float32(avgNumTokens)

	// return solution
	return &AnalysisData{
		Throughput:    tput,
		AvgRespTime:   avgRespTime,
		AvgWaitTime:   avgWaitTime,
		AvgNumInServ:  avgNumInServ,
		AvgTokenTime:  avgTokenTime,
		MaxRPM:        maxRPM,
		RMPTargetWait: lambdaStarWait * 1000 * 60,
		RPMTargetITL:  lambdaStarService * 1000 * 60,
	}
}

/*
 * Handlers for REST API calls
 */

// analyze queue
func solve(c *gin.Context) {
	// get problem data
	pd := ProblemData{}
	if err := c.BindJSON(&pd); err != nil {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "binding error: " + err.Error()})
		return
	}
	if !IsValid(&pd) || pd.RPM == 0 {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "data error: invalid input data"})
		return
	}

	// calculate state-dependent service rate
	servRate := make([]float32, pd.MaxBatchSize)
	for n := 1; n <= pd.MaxBatchSize; n++ {
		servRate[n-1] = float32(n) / (float32(pd.AvgNumTokens) * (pd.Alpha + pd.Beta*float32(n)))
	}

	// set and check limits
	lambdaMax := servRate[pd.MaxBatchSize-1] * (1 - delta)
	maxRPM := lambdaMax * 1000 * 60
	if pd.RPM > maxRPM {
		c.IndentedJSON(http.StatusBadRequest,
			gin.H{"message": "limit error: " + fmt.Sprintf("RPM=%v greater than maxRPM=%v", pd.RPM, maxRPM)})
		return
	}
	occupancyUpperBound := pd.MaxQueueSize + pd.MaxBatchSize

	// create and solve model
	model := queue.NewMM1ModelStateDependent(occupancyUpperBound, servRate)
	// request per msec
	lambda := pd.RPM / 1000 / 60
	sol := analyzeModel(model, pd.AvgNumTokens, lambda, maxRPM, 0, 0)
	c.IndentedJSON(http.StatusOK, sol)
}

// find arrival rate to achieve target values
func target(c *gin.Context) {
	// get problem data
	pd := ProblemData{}
	if err := c.BindJSON(&pd); err != nil {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "binding error: " + err.Error()})
		return
	}
	if !IsValid(&pd) {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "data error: invalid input data"})
		return
	}

	// calculate state-dependent service rate
	servRate := make([]float32, pd.MaxBatchSize)
	for n := 1; n <= pd.MaxBatchSize; n++ {
		servRate[n-1] = float32(n) / (float32(pd.AvgNumTokens) * (pd.Alpha + pd.Beta*float32(n)))
	}

	// set and check limits
	lambdaMin := servRate[0] * delta
	lambdaMax := servRate[pd.MaxBatchSize-1] * (1 - delta)
	maxRPM := lambdaMax * 1000 * 60
	occupancyUpperBound := pd.MaxQueueSize + pd.MaxBatchSize
	targetServTime := pd.TargetITL * float32(pd.AvgNumTokens)
	targetWaitTime := pd.TargetWait * 1000

	// create model
	model := queue.NewMM1ModelStateDependent(occupancyUpperBound, servRate)
	utils.Model = model

	// find max rate to achieve target service time
	lambdaStarService, ind, err := utils.BinarySearch(lambdaMin, lambdaMax, targetServTime, utils.EvalServTime)
	if err != nil {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "service target analysis error: ind=" + string(ind)})
		return
	}

	// find max rate to achieve target wait time
	lambdaStarWait, ind, err := utils.BinarySearch(lambdaMin, lambdaMax, targetWaitTime, utils.EvalWaitingTime)
	if err != nil {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "wait target analysis error: ind=" + string(ind)})
		return
	}

	// analyze queue with smaller of two rates
	lambda := lambdaStarService
	if lambdaStarWait < lambdaStarService {
		lambda = lambdaStarWait
	}
	sol := analyzeModel(model, pd.AvgNumTokens, lambda, maxRPM, lambdaStarWait, lambdaStarService)
	c.IndentedJSON(http.StatusOK, sol)
}
