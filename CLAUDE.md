# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the REST server locally
go run main.go

# Build
go build ./...

# Run tests
go test ./...

# Run a single test
go test ./pkg/queue/... -run TestName

# Run a demo
go run demos/mm1state/main.go

# Build and run with Docker
docker build -t queue-analyzer .
docker run -d -p 8080:8080 --name queue-analyzer queue-analyzer
```

## Architecture

This is a Go REST service that performs analytical queuing-theory modeling of LLM inference servers. The service exposes two endpoints (`POST /solve` and `POST /target`) on port 8080.

### Layer structure

```
pkg/service/   → HTTP layer (Gin): ProblemData (input) / AnalysisData (output) structs, request binding
pkg/analyzer/  → Domain logic: LLMQueueAnalyzer, builds the queueing model, Analyze() and Size() methods
pkg/queue/     → Queueing models (math): QueueModel base → MM1KModel → MM1ModelStateDependent
pkg/utils/     → BinarySearch utility used for finding target arrival rates
demos/         → Standalone CLI programs exercising the packages directly
```

### Key design patterns

**Queue model hierarchy** uses function pointers as a pseudo-virtual-method pattern (no Go interfaces). `QueueModel` stores `ComputeRho`, `GetRhoMax`, and `computeStatistics` as fields, overridden by each subclass.

**State-dependent service rates**: The core model `MM1ModelStateDependent` embeds `MM1KModel` (finite-capacity M/M/1/K queue) and adds a `servRate[]` slice where `servRate[n-1]` is the service rate when `n` requests are concurrently in service. This models batch inference: rate depends on batch occupancy.

**Rate units**: Request rates are stored internally in requests/millisecond (divided by 1000 from RPS). The service layer converts at the boundary (`requestRate/1000` on input, `*1000` on output).

**LLM timing model**: Iteration time = `alpha + batchSize*(beta*tokensCompute + gamma*tokensMemory)`. Prefill and decode times are derived from this, and service rates for each batch size are pre-computed in `BuildModel()`.

**Size() / target endpoint**: Uses binary search over the arrival rate range to find the maximum rate satisfying TTFT and ITL targets. The binding constraint (min of the two rates) is then used to compute full metrics.

**Overload handling**: `Analyze()` accepts any positive arrival rate, including rates above `RateRange.Max`. The finite-K model absorbs excess load via blocking probability `p[K]`; throughput saturates naturally. `AnalysisMetrics.OfferedRate` records the requested rate; dropped traffic = `OfferedRate - Throughput`. An error is returned only for `requestRate <= 0`.

### Key types

- `ServiceParms{Alpha, Beta, Gamma}` — GPU/server timing coefficients
- `RequestSize{AvgInputTokens, AvgOutputTokens}` — workload characteristics
- `Configuration{MaxBatchSize, MaxQueueSize, ServiceParms}` — queue setup
- `AnalysisMetrics` — output of `Analyze()`: `OfferedRate`, `Throughput` (goodput), latencies, TTFT, ITL
- `TargetPerf / TargetRate` — input/output of `Size()`
