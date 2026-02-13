# Queue Analyzer

The queue analyzer is used to analyze and size inference servers.
It utilizes a queueing model which captures the queueing and processing (prefill and decode) statistical behavior of requests.

The configuration of the model includes:

- queueing parameters: max batch size and max queue length
- processing parameters: constants used to calculate prefill and decode times

The traffic load on the model includes:

- request rate
- average request size (average number of input and output tokens)

The model is used for:

- analysis: evaluate performance metrics given load
- sizing: evaluate max request rate to achieve a given target performance

The model may be used for different scenarios by setting the number of tokens:

- prefill only: inputTokens > 0, outputTokens = 1
- decode only: inputTokens = 0, outputTokens > 0
- mixed: inputTokens > 0, outputTokens > 1

Units of performance metrics:

- rate: requests/sec, except internal to the queueing model (lambda)
- time: msec

Timing metrics are defined as follows:

- AvgRespTime: average request response time (aka latency)
- AvgWaitTime: average request queueing time
- AvgPrefillTime: average request prefill time (processing input tokens)
- AvgTokenTime: average token decode time (generating time of an output token)
- TTFT: AvgWaitTime + AvgPrefillTime + AvgTokenTime
- ITL: AvgTokenTime

Target metrics are defined as follows:

- TTFT: max average Time-To-First-Token (msec)
- ITL: max average Inter-Token-Latency (msec)
- TPS: min token generation rate (tokens/sec)

Target values are positive, if zero then target not considered.
