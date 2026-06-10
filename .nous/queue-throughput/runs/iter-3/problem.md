# Problem Framing — Iteration 3: Closed-Form Predictor for M*

## Research Question

Can M* = argmax_M f(M) be predicted from the scenario input parameters alone (without oracle calls) with accuracy |M_est - M*| ≤ 5?

The mechanism under study is the min(lambdaStarTTFT, lambdaStarITL) interaction at `pkg/analyzer/queueanalyzer.go:242` which creates the two-phase structure. From iter-1 and iter-2, we know M* is the crossover point where RPSTargetTTFT(M) first exceeds RPSTargetITL(M). The predictor exploits the relationship between DecodeTime linearity (`pkg/analyzer/queueanalyzer.go:278-280`) and the TTFT budget structure.

## System Interface

- **Build command:** `go build -o /tmp/queue-analysis .` (repo root)
- **Run predictor test:** `python3 .nous/queue-throughput/runs/iter-3/inputs/run_predictor.py`
- **Run ablation:** `python3 .nous/queue-throughput/runs/iter-3/inputs/run_predictor.py --no-wait-budget`
- **Run harness strategy:** `source nous/.venv/bin/activate && python -m nous.harness.run --scenarios nous/scenarios.json --strategy nous/harness/strategies/<name>.py --out <results>.json`
- **Code evidence:**
  - `pkg/analyzer/queueanalyzer.go:263-266` — IterationTime formula: `alpha + batchSize*(beta*tokensCompute + gamma*tokensMemory)`
  - `pkg/analyzer/queueanalyzer.go:278-280` — DecodeTime formula: `IterationTime(batchSize) + beta + gamma*(avgIn + (avgOut+1)/2)`. Linear in batchSize (= avg number in service). This is the basis of the n_ITL derivation.
  - `pkg/analyzer/queueanalyzer.go:270-274` — PrefillTime formula: `IterationTime(batchSize) + (beta+gamma)*avgInputTokens`
  - `pkg/analyzer/queueanalyzer.go:242` — `lambda := min(lambdaStarTTFT, lambdaStarITL, lambdaStarTPS)`. The crossover mechanism.
  - `pkg/analyzer/queueanalyzer.go:300-309` — EvalITL function: binary search for max lambda where avgDecodeTime <= targetITL.
  - `nous/harness/run.py:53-98` — Harness execution and confirmatory call.
  - `nous/cache/truth-*.json` — Ground truth M* values for comparison.

## Baseline Command

```bash
python3 .nous/queue-throughput/runs/iter-3/inputs/run_predictor.py
```

## Baseline Validation

Exit code 0. Output is JSON showing:
- baseline: M_est=38, M_truth=40, error=2
- short-tight-ttft: correctly identified as no-crossover (wait_budget=-11.29ms)
- long-loose-itl: M_est=91, M_truth=93, error=2
- small-queue: M_est=38, M_truth=38, error=0
- max_error=2, all_within_5=True

## Experimental Conditions

### h-main: Full predictor accuracy
Run `run_predictor.py` (default mode). Verify |M_est - M*| ≤ 5 for all crossover scenarios. Report max error, per-scenario breakdown, and component contributions (n_ITL, buffer term, wait term).

### h-ablation: Remove wait_budget correction
Run `run_predictor.py --no-wait-budget`. This sets the wait_budget coefficient to 0, leaving only `M_est = n_ITL + 3.0*sqrt(n_ITL)`. Prediction should degrade specifically for long-loose-itl (large wait_budget=107ms) while baseline and small-queue remain unaffected (small wait_budget=7ms).

### h-control-negative: No-crossover detection
The predictor should detect short-tight-ttft as having no crossover (wait_budget < 0). Verify that:
1. wait_budget = targetTTFT - targetITL - PrefillTime(n_ITL) < 0 for short-tight-ttft
2. The sign correctly separates crossover (baseline, long-loose-itl, small-queue) from no-crossover (short-tight-ttft)

### h-robustness: Predictor-guided search achieves gap=0 with reduced calls
A strategy that searches [M_est-5, M_est+5] using binary search on ratio R(M) should find M* exactly (gap=0) in at most ceil(log2(11))+1 = 5 total calls, compared to 9 for the full binary search. Test by running a strategy that uses the pre-computed M_est as initial bounds.

## Success Criteria

1. **Predictor accuracy:** max |M_est - M*| ≤ 5 across all crossover scenarios (baseline, long-loose-itl, small-queue).
2. **Crossover detection:** wait_budget sign correctly classifies all 4 scenarios.
3. **Ablation effect:** removing wait_budget term increases error for long-loose-itl by > 4 (from 2 to 8).
4. **Mechanism validation:** the two dominant components (n_ITL base and 3*sqrt(n_ITL) buffer) account for > 95% of M_est for scenarios with small wait_budget.

## Constraints

- Do not modify the Go analyzer code.
- Do not add new scenarios.
- Predictor must use only the fixed parameters {alpha, beta, gamma, avgIn, avgOut, targetITL, targetTTFT} — not the oracle output.
- The predictor is validated against truth cache M* values, not live oracle calls.

## Prior Knowledge

- **RP-2:** M* coincides with the binding-constraint crossover (RPSTargetTTFT = RPSTargetITL). This is the fundamental identity the predictor exploits.
- **RP-5:** The optimization is a plateau-onset detection problem. For no-crossover cases (TTFT always binding), M* is any point on the plateau.
- **RP-6:** M* is findable in O(log N) calls via ratio binary search. The predictor aims to improve this to O(log(width)) where width ≈ 10.
- **RP-7:** The two-phase structure is caused entirely by min(TTFT, ITL) at queueanalyzer.go:242.
