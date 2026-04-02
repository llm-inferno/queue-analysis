package service

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/llm-inferno/queue-analysis/pkg/analyzer"
)

// problem input data
type ProblemData struct {
	RPS             float32 `json:"RPS"`             // request arrival rate (requests/sec)
	MaxBatchSize    int     `json:"maxBatchSize"`    // maximum batch size
	AvgInputTokens  float32 `json:"avgInputTokens"`  // average number of input tokens per request
	AvgOutputTokens float32 `json:"avgOutputTokens"` // average number of output tokens per request
	Alpha           float32 `json:"alpha"`           // base iteration time (msec)
	Beta            float32 `json:"beta"`            // slope for compute time (msec/token)
	Gamma           float32 `json:"gamma"`           // slope for memory access time (msec/token*2)
	MaxQueueSize    int     `json:"maxQueueSize"`    // maximum queue size
	TargetTTFT      float32 `json:"targetTTFT"`      // target time to first token (msec)
	TargetITL       float32 `json:"targetITL"`       // target inter-token interval (msec)
}

// analysis solution output data
type AnalysisData struct {
	OfferedRPS    float32 `json:"offeredRPS"`    // offered arrival rate (requests/sec)
	Throughput    float32 `json:"throughput"`    // effective throughput (requests/sec)
	AvgRespTime   float32 `json:"avgRespTime"`   // average response time (sec)
	AvgWaitTime   float32 `json:"avgWaitTime"`   // average queueing time (sec)
	AvgNumInServ  float32 `json:"avgNumInServ"`  // average number of requests in system
	AvgTTFT       float32 `json:"avgTTFT"`       // average time to first token (msec)
	AvgITL        float32 `json:"avgITL"`        // average inter-token latency (msec)
	MaxRPS        float32 `json:"maxRPS"`        // maximum throughput (requests/sec)
	RPSTargetTTFT float32 `json:"RPSTargetTTFT"` // throughput to achieve target TTFT (requests/sec)
	RPSTargetITL  float32 `json:"RPSTargetITL"`  // throughput to achieve target ITL (requests/sec)
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
	return pd.RPS >= 0 &&
		pd.MaxBatchSize > 0 &&
		pd.AvgInputTokens >= 0 &&
		pd.AvgOutputTokens >= 0 &&
		pd.Alpha >= 0 &&
		pd.Beta >= 0 &&
		pd.Gamma >= 0 &&
		pd.MaxQueueSize >= 0 &&
		pd.TargetTTFT >= 0 &&
		pd.TargetITL >= 0
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
	if !IsValid(&pd) {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "data error: invalid input data"})
		return
	}

	// create queue analyzer
	queueAnalyzer := CreateQueueAnalyzer(&pd)
	if queueAnalyzer == nil {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "NewLLMQueueAnalyzer() failed"})
		return
	}

	// analyze queue under a given load
	metrics, err := queueAnalyzer.Analyze(pd.RPS)
	if err != nil {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "Analyze() failed: " + err.Error()})
		return
	}

	// return solution
	analysisData := &AnalysisData{
		OfferedRPS:   metrics.OfferedRate,
		Throughput:   metrics.Throughput,
		AvgRespTime:  metrics.AvgRespTime,
		AvgWaitTime:  metrics.AvgWaitTime,
		AvgNumInServ: metrics.AvgNumInServ,
		AvgTTFT:      metrics.AvgTTFT,
		AvgITL:       metrics.AvgTokenTime,
		MaxRPS:       metrics.MaxRate,
	}
	c.IndentedJSON(http.StatusOK, analysisData)
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

	// create queue analyzer
	queueAnalyzer := CreateQueueAnalyzer(&pd)
	if queueAnalyzer == nil {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "NewLLMQueueAnalyzer() failed"})
		return
	}

	// size queue for given targets
	targetPerf := &analyzer.TargetPerf{
		TargetTTFT: pd.TargetTTFT,
		TargetITL:  pd.TargetITL,
		TargetTPS:  0, // not used in this service
	}
	targetRate, metrics, targetPerf, err := queueAnalyzer.Size(targetPerf)
	if err != nil {
		c.IndentedJSON(http.StatusBadRequest, gin.H{"message": "Size() failed: " + err.Error()})
		return
	}

	// return solution
	analysisData := &AnalysisData{
		OfferedRPS:    metrics.OfferedRate,
		Throughput:    metrics.Throughput,
		AvgRespTime:   metrics.AvgRespTime,
		AvgWaitTime:   metrics.AvgWaitTime,
		AvgNumInServ:  metrics.AvgNumInServ,
		AvgTTFT:       metrics.AvgTTFT,
		AvgITL:        metrics.AvgTokenTime,
		MaxRPS:        metrics.MaxRate,
		RPSTargetTTFT: targetRate.RateTargetTTFT,
		RPSTargetITL:  targetRate.RateTargetITL,
	}
	c.IndentedJSON(http.StatusOK, analysisData)
}

// create queue analyzer from problem data
func CreateQueueAnalyzer(pd *ProblemData) *analyzer.LLMQueueAnalyzer {
	// create queue analyzer
	config := &analyzer.Configuration{
		MaxBatchSize: pd.MaxBatchSize,
		MaxQueueSize: pd.MaxQueueSize,
		ServiceParms: &analyzer.ServiceParms{
			Alpha: pd.Alpha,
			Beta:  pd.Beta,
			Gamma: pd.Gamma,
		},
	}

	requestSize := &analyzer.RequestSize{
		AvgInputTokens:  pd.AvgInputTokens,
		AvgOutputTokens: pd.AvgOutputTokens,
	}

	queueAnalyzer, _ := analyzer.NewLLMQueueAnalyzer(config, requestSize)
	return queueAnalyzer
}
