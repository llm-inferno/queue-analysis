package analyzer

import (
	"fmt"

	"github.com/llm-inferno/queue-analysis/pkg/queue"
	"github.com/llm-inferno/queue-analysis/pkg/utils"
)

// small disturbance around a value
const Epsilon = float32(0.001)

// fraction of maximum server throughput to provide stability (running this fraction below the maximum)
const StabilitySafetyFraction = float32(0.1)

// maximum number of tokens per batch (iteration)
const DefaultMaxNumTokens = 8192

// Analyzer of inference server queue
type LLMQueueAnalyzer struct {
	MaxBatchSize int                           // maximum batch size
	MaxNumTokens int                           // maximum number of tokens per batch
	MaxQueueSize int                           // maximum queue size
	ServiceParms *ServiceParms                 // request processing parameters
	RequestSize  *RequestSize                  // number of input and output tokens per request
	Model        *queue.MM1ModelStateDependent // queueing model
	RateRange    *RateRange                    // range of request rates for model stability
	NumChunks    []int                         // NumChunks[B] = number of prefill chunks at batch size B
}

// queue configuration parameters
type Configuration struct {
	MaxBatchSize int           // maximum batch size (limit on the number of requests concurrently receiving service >0)
	MaxNumTokens int           // maximum number of tokens per batch (limit on the number of tokens per batch >0)
	MaxQueueSize int           // maximum queue size (limit on the number of requests queued for servive >=0)
	ServiceParms *ServiceParms // request processing parameters
}

// request processing parameters:
// iterationTime = alpha + beta * computeTime + gamma * memoryAccessTime
type ServiceParms struct {
	Alpha float32 // base
	Beta  float32 // slope for compute time
	Gamma float32 // slope for memory access time
}

// request tokens data
type RequestSize struct {
	AvgInputTokens  float32 // average number of input tokens per request
	AvgOutputTokens float32 // average number of output tokens per request
}

// range of request rates (requests/sec)
type RateRange struct {
	Min float32 // lowest rate (slightly larger than zero)
	Max float32 // highest rate (slightly less than maximum service rate)
}

// analysis solution metrics data
type AnalysisMetrics struct {
	OfferedRate    float32 // offered arrival rate (requests/sec); equals Throughput when not overloaded
	Throughput     float32 // effective throughput / goodput (requests/sec)
	AvgRespTime    float32 // average request response time (aka latency) (msec)
	AvgWaitTime    float32 // average request queueing time (msec)
	AvgNumInServ   float32 // average number of requests in service
	AvgPrefillTime float32 // average request prefill time (msec)
	AvgTokenTime   float32 // average token decode time (msec)
	AvgTTFT        float32 // average time to first token (msec)
	MaxRate        float32 // maximum throughput (requests/sec)
	Rho            float32 // utilization
}

// queue performance targets
type TargetPerf struct {
	TargetTTFT float32 // target time to first token (queueing + prefill) (msec)
	TargetITL  float32 // target inter-token latency (msec)
	TargetTPS  float32 // target token generation throughtput (tokens/sec)
}

// queue max request rates to achieve performance targets
type TargetRate struct {
	RateTargetTTFT float32 // max request rate for target TTFT (requests/sec)
	RateTargetITL  float32 // max request rate for target ITL (requests/sec)
	RateTargetTPS  float32 // max request rate for target TPS (requests/sec)
}

// create a new queue analyzer from config
func NewLLMQueueAnalyzer(qConfig *Configuration, requestSize *RequestSize) (*LLMQueueAnalyzer, error) {
	if err := qConfig.check(); err != nil {
		return nil, err
	}
	if err := requestSize.check(); err != nil {
		return nil, err
	}
	// build queueing model
	return BuildModel(qConfig, requestSize), nil
}

// build queueing model using service rates, leaving arrival rate as parameter.
//
// Limited (chunked-prefill) case + new analysis. For each batch size B,
// the per-request service time is tau(B) = (c+m)*T_iter(B) where c=c(B) is
// the number of prefill chunks and T_iter(B) = alpha + B*delta. The OLD
// analysis had tau(B) = prefill_old(B) + m*decode_old(B) which expands to
// (c+m)*(alpha + (B+1)*delta), double-counting the focal request's own work;
// removing that double count is the defining change of the new analysis.
func BuildModel(c *Configuration, r *RequestSize) (modelData *LLMQueueAnalyzer) {
	parms := c.ServiceParms

	numChunks := NumIterationsPerPrefill(c, r)

	servRate := make([]float32, c.MaxBatchSize)
	for B := 1; B <= c.MaxBatchSize; B++ {
		nc := numChunks[B]
		tau := tauNew(parms, r, B, nc)
		servRate[B-1] = float32(B) / tau
	}

	// set and check limits
	lambdaMin := servRate[0] * Epsilon
	lambdaMax := servRate[c.MaxBatchSize-1] * (1 - Epsilon)
	rateRange := &RateRange{Min: lambdaMin * 1000, Max: lambdaMax * 1000}

	// create and solve model
	occupancyUpperBound := c.MaxQueueSize + c.MaxBatchSize
	model := queue.NewMM1ModelStateDependent(occupancyUpperBound, servRate)

	return &LLMQueueAnalyzer{
		MaxBatchSize: c.MaxBatchSize,
		MaxNumTokens: c.MaxNumTokens,
		MaxQueueSize: c.MaxQueueSize,
		ServiceParms: parms,
		RequestSize:  r,
		Model:        model,
		RateRange:    rateRange,
		NumChunks:    numChunks,
	}
}

// evaluate performance metrics given request rate
func (qa *LLMQueueAnalyzer) Analyze(requestRate float32) (metrics *AnalysisMetrics, err error) {
	if requestRate <= 0 {
		return nil, fmt.Errorf("invalid request rate %v", requestRate)
	}
	model := qa.Model

	// No upper-bound guard: the finite-K birth-death model handles any arrival rate.
	// Excess load increases blocking probability p[K]; throughput saturates naturally.
	// Callers can detect overload via: metrics.OfferedRate > metrics.Throughput
	model.Solve(requestRate/1000, 1)
	if !model.IsValid() {
		err = fmt.Errorf("invalid model %s", model)
		return nil, err
	}

	// mean-field at the in-service mean batch size X
	avgNumInServ := model.GetAvgNumInServers()
	nc := qa.numChunksAt(avgNumInServ)
	avgPrefillTime := prefillNew(qa.ServiceParms, qa.RequestSize, avgNumInServ, nc)
	avgDecodeTime := (model.GetAvgServTime() - avgPrefillTime) / qa.RequestSize.AvgOutputTokens
	avgTTFT := model.GetAvgWaitTime() + avgPrefillTime + avgDecodeTime

	rho := avgNumInServ / float32(qa.MaxBatchSize)
	rho = min(max(rho, 0), 1)

	// return solution
	metrics = &AnalysisMetrics{
		OfferedRate:    requestRate,
		Throughput:     model.GetThroughput() * 1000,
		AvgRespTime:    model.GetAvgRespTime(),
		AvgWaitTime:    model.GetAvgWaitTime(),
		AvgNumInServ:   avgNumInServ,
		AvgPrefillTime: avgPrefillTime,
		AvgTokenTime:   avgDecodeTime,
		AvgTTFT:        avgTTFT,
		MaxRate:        qa.RateRange.Max,
		Rho:            rho,
	}
	return metrics, nil
}

// numChunksAt returns the number of prefill chunks for a (possibly fractional)
// batch size, reading it off the precomputed table at the rounded index.
func (qa *LLMQueueAnalyzer) numChunksAt(batchSize float32) int {
	return numChunksAtFromTable(qa.NumChunks, batchSize, qa.MaxBatchSize)
}

// model and parameters used in functional evaluation
type EvalFuncData struct {
	model        *queue.MM1ModelStateDependent // queueing model
	requestSize  *RequestSize                  // number of input and output tokens per request
	serviceParms *ServiceParms                 // request processing parameters for prefill and decode stages
	maxBatchSize int                           // max batch size
	numChunks    []int                         // NumChunks[B] for B = 1..maxBatchSize
}

// evaluate max request rates to achieve a given target performance
func (qa *LLMQueueAnalyzer) Size(targetPerf *TargetPerf) (targetRate *TargetRate, metrics *AnalysisMetrics, achieved *TargetPerf, err error) {
	if err := targetPerf.check(); err != nil {
		return nil, nil, nil, err
	}
	targetTTFT := targetPerf.TargetTTFT
	targetITL := targetPerf.TargetITL
	targetTPS := targetPerf.TargetTPS

	lambdaMin := qa.RateRange.Min / 1000
	lambdaMax := qa.RateRange.Max / 1000

	var ind int

	lambdaStarTTFT := lambdaMax
	if targetTTFT > 0 {
		evalTTF := EvalTTFT(&EvalFuncData{
			model:        qa.Model,
			requestSize:  qa.RequestSize,
			serviceParms: qa.ServiceParms,
			maxBatchSize: qa.MaxBatchSize,
			numChunks:    qa.NumChunks,
		})
		lambdaStarTTFT, ind, err = utils.BinarySearch(lambdaMin, lambdaMax, targetTTFT, evalTTF)
		if ind < 0 {
			err = fmt.Errorf("target is below the bounded region")
		}
		if err != nil {
			return nil, nil, nil, fmt.Errorf("failed to calculate lambdaStarTTFT, targetTTFT=%v, range=%s, ind=%d, err=%v",
				targetTTFT, qa.RateRange, ind, err)
		}
	}

	lambdaStarITL := lambdaMax
	if targetITL > 0 {
		evalITL := EvalITL(&EvalFuncData{
			model:        qa.Model,
			requestSize:  qa.RequestSize,
			serviceParms: qa.ServiceParms,
			maxBatchSize: qa.MaxBatchSize,
			numChunks:    qa.NumChunks,
		})
		lambdaStarITL, ind, err = utils.BinarySearch(lambdaMin, lambdaMax, targetITL, evalITL)
		if ind < 0 {
			err = fmt.Errorf("target is below the bounded region")
		}
		if err != nil {
			return nil, nil, nil, fmt.Errorf("failed to calculate lambdaStarITL, targetITL=%v, range=%s, ind=%d, err=%v",
				targetITL, qa.RateRange, ind, err)
		}
	}

	lambdaStarTPS := lambdaMax
	if targetTPS > 0 {
		lambdaStarTPS = lambdaMax * (1 - StabilitySafetyFraction)
	}

	lambda := min(lambdaStarTTFT, lambdaStarITL, lambdaStarTPS)
	requestRate := lambda * 1000
	if metrics, err = qa.Analyze(requestRate); err != nil {
		return nil, nil, nil, err
	}

	targetRate = &TargetRate{
		RateTargetTTFT: lambdaStarTTFT * 1000,
		RateTargetITL:  lambdaStarITL * 1000,
		RateTargetTPS:  lambdaStarTPS * 1000,
	}

	achieved = &TargetPerf{
		TargetTTFT: metrics.AvgTTFT,
		TargetITL:  metrics.AvgTokenTime,
		TargetTPS:  metrics.Throughput * qa.RequestSize.AvgOutputTokens,
	}
	return targetRate, metrics, achieved, nil
}

// ---------------------------------------------------------------------------
// New-analysis primitives. The work decomposition (w_prefill, w_decode, delta)
// is unchanged from the per-iteration work model. The state-dependent service
// time, prefill latency, and per-token decode latency follow the new analysis:
//
//   prefill(B) = c * (alpha + (B-1)*delta) + w_prefill
//   itl(B)     = alpha + (B-1)*delta + beta + gamma*(n + (m+1)/2)
//   tau(B)     = (c+m) * (alpha + B*delta)
//
// alpha + (B-1)*delta is the "background" iteration time (overhead plus the
// c-1 co-resident requests, with the focal request's own contribution
// removed); the focal request's own work is charged explicitly via w_prefill
// and the marginal decode term.
// ---------------------------------------------------------------------------

func wPrefill(p *ServiceParms, r *RequestSize, nc int) float32 {
	return (p.Beta + p.Gamma*float32(nc+1)/2) * r.AvgInputTokens
}

func wDecode(p *ServiceParms, r *RequestSize) float32 {
	return p.Beta*r.AvgOutputTokens + p.Gamma*r.AvgOutputTokens*(r.AvgInputTokens+(r.AvgOutputTokens+1)/2)
}

func wTotal(p *ServiceParms, r *RequestSize, nc int) float32 {
	return wPrefill(p, r, nc) + wDecode(p, r)
}

func delta(p *ServiceParms, r *RequestSize, nc int) float32 {
	return wTotal(p, r, nc) / (float32(nc) + r.AvgOutputTokens)
}

func tIter(p *ServiceParms, r *RequestSize, batchSize float32, nc int) float32 {
	return p.Alpha + batchSize*delta(p, r, nc)
}

func tauNew(p *ServiceParms, r *RequestSize, batchSize int, nc int) float32 {
	return (float32(nc) + r.AvgOutputTokens) * tIter(p, r, float32(batchSize), nc)
}

func prefillNew(p *ServiceParms, r *RequestSize, batchSize float32, nc int) float32 {
	bg := p.Alpha + (batchSize-1)*delta(p, r, nc)
	if bg < 0 {
		bg = 0
	}
	return float32(nc)*bg + wPrefill(p, r, nc)
}

func itlNew(p *ServiceParms, r *RequestSize, batchSize float32, nc int) float32 {
	bg := p.Alpha + (batchSize-1)*delta(p, r, nc)
	if bg < 0 {
		bg = 0
	}
	return bg + p.Beta + p.Gamma*(r.AvgInputTokens+(r.AvgOutputTokens+1)/2)
}

// ---------------------------------------------------------------------------
// Backwards-compat shims. Out-of-tree callers may use ServiceParms.IterationTime
// / PrefillTime / DecodeTime directly; those keep working but degenerate to the
// unlimited (c=1) case because the chunked formulas need a numChunks input
// that the bare-method signature cannot supply. New code should call the
// analyzer-level helpers above.
// ---------------------------------------------------------------------------

func (p *ServiceParms) IterationTime(r *RequestSize, batchSize float32) float32 {
	return tIter(p, r, batchSize, 1)
}

func (p *ServiceParms) PrefillTime(r *RequestSize, batchSize float32) float32 {
	if r.AvgInputTokens == 0 {
		return 0
	}
	return prefillNew(p, r, batchSize, 1)
}

func (p *ServiceParms) DecodeTime(r *RequestSize, batchSize float32) float32 {
	return itlNew(p, r, batchSize, 1)
}

// Function used in binary search (target TTFT)
//   - x is lambda req/msec
func EvalTTFT(data *EvalFuncData) func(x float32) (float32, error) {
	return func(x float32) (float32, error) {
		data.model.Solve(x, 1)
		if !data.model.IsValid() {
			return 0, fmt.Errorf("invalid model %s", data.model)
		}
		B := data.model.GetAvgNumInServers()
		nc := numChunksAtFromTable(data.numChunks, B, data.maxBatchSize)
		avgPrefillTime := prefillNew(data.serviceParms, data.requestSize, B, nc)
		avgDecodeTime := (data.model.GetAvgServTime() - avgPrefillTime) / data.requestSize.AvgOutputTokens
		ttft := data.model.GetAvgWaitTime() + avgPrefillTime + avgDecodeTime
		return ttft, nil
	}
}

// Function used in binary search (target ITL)
//   - x is lambda req/msec
func EvalITL(data *EvalFuncData) func(x float32) (float32, error) {
	return func(x float32) (float32, error) {
		data.model.Solve(x, 1)
		if !data.model.IsValid() {
			return 0, fmt.Errorf("invalid model %s", data.model)
		}
		B := data.model.GetAvgNumInServers()
		nc := numChunksAtFromTable(data.numChunks, B, data.maxBatchSize)
		avgPrefillTime := prefillNew(data.serviceParms, data.requestSize, B, nc)
		avgDecodeTime := (data.model.GetAvgServTime() - avgPrefillTime) / data.requestSize.AvgOutputTokens
		return avgDecodeTime, nil
	}
}

func numChunksAtFromTable(table []int, batchSize float32, maxBatchSize int) int {
	idx := int(batchSize + 0.5)
	if idx < 1 {
		idx = 1
	}
	if idx > maxBatchSize {
		idx = maxBatchSize
	}
	return table[idx]
}
