package analyzer

import (
	"fmt"
	"math"
)

func CalculateMaxBatchSizeForNumIterationsPerPrefill(cfg *Configuration, req *RequestSize, numIters int) int {
	L := req.AvgInputTokens
	K := req.AvgOutputTokens
	M := float32(cfg.MaxNumTokens)
	m := float32(numIters)

	batchSize := (m + K) * (M - L/m) / (L + K)
	batchSize = max(0, batchSize)
	return int(math.Floor(float64(batchSize)))
}

func CalculateBatchSizes(cfg *Configuration, req *RequestSize) []int {
	batchSizes := []int{}
	batchSize := 0
	numIters := 1
	for batchSize < cfg.MaxBatchSize {
		batchSize = CalculateMaxBatchSizeForNumIterationsPerPrefill(cfg, req, numIters)
		batchSizes = append(batchSizes, batchSize)
		numIters++
	}
	return batchSizes
}

func NumIterationsPerPrefillForBatchSize(batchSizes []int, batchSize int) int {
	for i, bs := range batchSizes {
		if bs >= batchSize {
			return i + 1
		}
	}
	return len(batchSizes)
}

func NumIterationsPerPrefill(cfg *Configuration, req *RequestSize) []int {
	batchSizes := CalculateBatchSizes(cfg, req)
	numIters := make([]int, cfg.MaxBatchSize+1)
	for batchSize := 1; batchSize <= cfg.MaxBatchSize; batchSize++ {
		numIters[batchSize] = NumIterationsPerPrefillForBatchSize(batchSizes, batchSize)
	}
	return numIters
}

// NumChunks returns the number of prefill chunks nc for a request given
// batch size N, token budget M, input tokens n, and output tokens m.
// Solves the token budget constraint at equality for nc:
//
//	M*nc^2 + Phi*nc - n*m = 0,  where Phi = m*(M-N) - n*(N+1)
//
// The unique positive root is nc* = (-Phi + sqrt(Phi^2 + 4*M*n*m)) / (2*M),
// and nc = ceil(nc*). The result is always >= 1.
func NumChunks(N, M int, n, m float32) int {
	phi := m*float32(M-N) - n*float32(N+1)
	disc := phi*phi + 4*float32(M)*n*m
	nc := (-phi + float32(math.Sqrt(float64(disc)))) / (2 * float32(M))
	return max(1, int(math.Ceil(float64(nc))))
}

// check validity of configuration parameters
func (c *Configuration) check() error {
	if c.MaxBatchSize <= 0 || c.MaxQueueSize < 0 || c.MaxNumTokens < 0 ||
		c.ServiceParms == nil {
		return fmt.Errorf("invalid configuration %s", c)
	}
	if c.MaxNumTokens == 0 {
		c.MaxNumTokens = DefaultMaxNumTokens
	}
	return nil
}

// check validity of request size
func (rq *RequestSize) check() error {
	if rq.AvgInputTokens < 0 || rq.AvgOutputTokens < 1 {
		return fmt.Errorf("invalid request size %s", rq)
	}
	return nil
}

// check validity of target values
func (targetPerf *TargetPerf) check() error {
	if targetPerf.TargetITL < 0 ||
		targetPerf.TargetTTFT < 0 ||
		targetPerf.TargetTPS < 0 {
		return fmt.Errorf("invalid target data values %s", targetPerf)
	}
	return nil
}

/*
 * toString() functions
 */

func (c *Configuration) String() string {
	return fmt.Sprintf("{maxBatch=%d, maxNumTokens=%d, maxQueue=%d, servParms:%s}",
		c.MaxBatchSize, c.MaxNumTokens, c.MaxQueueSize, c.ServiceParms)
}

func (qa *LLMQueueAnalyzer) String() string {
	return fmt.Sprintf("{maxBatch=%d, maxNumTokens=%d, maxQueue=%d, servParms:%s, reqSize:%s, model:%s, rates:%s}",
		qa.MaxBatchSize, qa.MaxNumTokens, qa.MaxQueueSize, qa.ServiceParms, qa.RequestSize, qa.Model, qa.RateRange)
}

func (sp *ServiceParms) String() string {
	return fmt.Sprintf("{alpha=%.3f, beta=%.5f, gamma=%.5f}", sp.Alpha, sp.Beta, sp.Gamma)
}

func (rq *RequestSize) String() string {
	return fmt.Sprintf("{inTokens=%.1f, outTokens=%.1f}", rq.AvgInputTokens, rq.AvgOutputTokens)
}

func (rr *RateRange) String() string {
	return fmt.Sprintf("[%.3f, %.3f]", rr.Min, rr.Max)
}

func (am *AnalysisMetrics) String() string {
	return fmt.Sprintf("{tput=%.3f, lat=%.3f, wait=%.3f, conc=%.3f, ttft=%.3f, itl=%.3f, maxRate=%.3f, rho=%0.3f}",
		am.Throughput, am.AvgRespTime, am.AvgWaitTime, am.AvgNumInServ, am.AvgTTFT, am.AvgTokenTime, am.MaxRate, am.Rho)
}

func (tp *TargetPerf) String() string {
	return fmt.Sprintf("{TTFT=%.3f, ITL=%.3f, TPS=%.3f}",
		tp.TargetTTFT, tp.TargetITL, tp.TargetTPS)
}

func (tr *TargetRate) String() string {
	return fmt.Sprintf("{rateTTFT=%.3f, rateITL=%.3f, rateTPS=%.3f}",
		tr.RateTargetTTFT, tr.RateTargetITL, tr.RateTargetTPS)
}
