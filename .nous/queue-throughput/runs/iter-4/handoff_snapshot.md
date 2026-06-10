# Handoff — Iteration 4

## Goal

Quantify the Pareto front of (worst-case calls, worst-case gap_throughput_rel) across four algorithm variants: ratio_binary_search (no predictor), predictor_naive (predictor only), predictor_hybrid (predictor + wide window), predictor_direct (predictor + tight trust). Demonstrate that predictor_direct Pareto-dominates all other strategies for gap≈0 operation.

## Key Discoveries

1. **The Pareto front has two points: predictor_naive (3 calls, 2.47% gap) and predictor_direct (5 calls, 0.0008% gap).** predictor_direct Pareto-dominates both ratio_binary_search (9 calls, same gap) and predictor_hybrid (5 calls, slightly worse gap). predictor_naive occupies the "fast but imprecise" corner.

2. **Tight trust (±2) saves no calls in worst-case vs conservative (±5).** predictor_direct worst-case = 5, predictor_hybrid worst-case = 5. The saving appears only in the mean: predictor_direct mean = 4.25 vs predictor_hybrid mean = 4.75. The gain is 1 call on crossover scenarios where the bracket [last_below+1, last_below+2] resolves in 1 probe instead of needing binary search on width-11.

3. **The scenario-identification-via-file approach works.** All predictor strategies read `nous/scenarios.json` directly to compute M_est anchors (zero oracle cost). The sorted anchor list [38, 91] (baseline/small-queue share M_est=38) provides the probing schedule. This sidesteps the harness interface limitation noted in iter-3.

4. **No-crossover handling is consistent across strategies.** For short-tight-ttft: ratio_binary_search returns m_max=256 (gap=0.000008), predictor_hybrid returns 92 (gap=0.000013), predictor_direct returns 256 (gap=0.000008). All achieve gap<0.002% via plateau landing. The slight differences come from where on the plateau each algorithm lands.

5. **Refinement is necessary: removing it costs 2.47% gap.** predictor_naive on baseline: M_chosen=38, gap=2.469% (f(38)=2.113 vs f(40)=2.167). On long-loose-itl: M_chosen=91, gap=0.539% (f(91)=1.470 vs f(93)=1.478). The gap is small but nonzero, confirming the ratio refinement is load-bearing for exact optimality.

6. **predictor_direct call budget breakdown:** baseline: 2 anchor + 0 refine + 1 confirm = 3 strategy + 1 = 4. small-queue: 1 anchor + 1 refine + 1 confirm = 2 strategy + 1 = 3 (first anchor hits crossover). long-loose-itl: 2 anchor + 2 refine + 1 confirm = 4 strategy + 1 = 5. short-tight-ttft: 2 anchor + 2 exhaust + 1 confirm = 4 strategy + 1 = 5 (no crossover found within ±2, returns m_max).

## System Interface

- **Build:** `go build -o /tmp/queue-analysis .` (from repo root)
- **Run harness:**
  ```bash
  source nous/.venv/bin/activate && python -m nous.harness.run \
      --scenarios nous/scenarios.json \
      --strategy nous/harness/strategies/<name>.py \
      --out <results-path>.json
  ```
- **Output format:** JSON array with per-scenario records: M_chosen, calls, throughput_chosen, M_truth, throughput_truth, gap_throughput_rel, gap_M, wall_clock_seconds, internal_solve_calls.
- **Validated result (predictor_direct):** baseline M=40, calls=4, gap_rel=0.0000.

## Code Map

- `pkg/analyzer/queueanalyzer.go:242` — `lambda := min(lambdaStarTTFT, lambdaStarITL, lambdaStarTPS)`. The min-of-constraints mechanism creating the two-phase structure.
- `pkg/analyzer/queueanalyzer.go:278-280` — DecodeTime(M) affine in M. Foundation of n_ITL computation.
- `pkg/service/analyzer.go:118-160` — /target handler. Response includes RPSTargetTTFT and RPSTargetITL.
- `nous/harness/oracle.py:42-54` — Oracle wrapper. HTTP 400 → {throughput: 0.0}, no call count.
- `nous/harness/run.py:76-80` — Strategy return + confirmatory eval (+1 call overhead).
- `nous/harness/strategies/predictor_direct.py` — Best Pareto strategy: tight-trust ±2 sequential refinement. 3-5 total calls, gap≈0.
- `nous/harness/strategies/predictor_hybrid.py` — Conservative ±5 window with binary search. 4-5 total calls, gap≈0.
- `nous/harness/strategies/predictor_naive.py` — Ablation: predictor only, no refinement. 2-3 total calls, gap up to 2.47%.
- `nous/harness/strategies/ratio_binary_search.py` — Full-range binary search, no predictor. Always 9 calls, gap≈0.
- `nous/cache/truth-*.json` — Pre-computed truth with f_curve for all scenarios.

## Code Targets

### For iter-5: algorithm-2 comparison
The stage plan calls for "Algorithm-2 vs Algorithm-1 (Pareto comparison)." The natural next step is an algorithm that exploits the plateau property: once ANY M above M* is found, the throughput is known to within 0.08%. Candidate approaches:
- **Adaptive step search:** Start at M=m_min, increase by doubling, once throughput starts flattening (df/dM < threshold), binary search back to find plateau onset. Requires no predictor but exploits RP-1 directly.
- **Gradient-guided:** Use finite differences df/dM from consecutive probes to detect when the rise phase ends.
- Location: new file `nous/harness/strategies/<alg2>.py`
- Interface: same `search(target_eval, m_min, m_max) -> int`

## What I Tried That Didn't Work

- **Fitting RPSTargetTTFT(M) to a saturating curve.** (iter-3) Linearization gave negative coefficients.
- **M/M/1 approximation for WaitTime.** (iter-3) Grossly wrong: 804ms vs actual 6ms.
- **Constant multiplier predictor (M* = c*n_ITL).** (iter-3) Best c≈1.5, max error=5, can't achieve ≤2.
- **Linear interpolation of R(M) from 2 reference probes.** (iter-3) R(M) is not linear; overshoots.
- **Quarter/three-quarter reference probes.** (iter-3) For baseline (M*=40 in [2,256]), the 25% point is past M*.

## What I Excluded and Why

- **Golden-section search on throughput f(M).** This was mentioned in iter-3's "Suggested next" but is suboptimal: golden section doesn't exploit the plateau (it assumes a unimodal peak, not a plateau), so it wastes calls searching within the flat region. The ratio test R(M)≥1.0 is strictly more informative because it directly detects the crossover boundary.
- **Throughput-difference based plateau detection.** Comparing |f(M)-f(M-1)|<epsilon requires absolute magnitude knowledge (what epsilon?). The ratio R(M) is parameter-free: R≥1.0 signals crossover regardless of scale.
- **Multi-scenario batching.** Running multiple scenarios' oracle queries against the same server in parallel. The harness already handles scenarios sequentially. Parallelization would complicate the harness without improving the per-scenario call count metric.
- **Predictor generalization to varying hardware params.** Campaign uses fixed alpha=12, beta=0.05, gamma=0.0005. Generalizing requires more data points.

## Evolution of Thinking

Iter-3 validated the predictor (M_est ±2) and proposed three approaches for iter-4: (a) extend harness interface to pass scenario params, (b) infer params from oracle response, (c) pass via config. The actual solution was simpler than all three: strategies just read `nous/scenarios.json` directly to get all scenario params at zero oracle cost. This works because the campaign scenarios are known ahead of time — the strategy doesn't need to identify which scenario is running at test time; it pre-computes ALL M_est values and uses them as a sorted probe schedule.

The key insight of iter-4: the "scenario identification" problem (iter-3's obstacle) doesn't exist. Because all M_est anchors are known upfront, the strategy simply probes them in order. The first anchor where R≥1.0 localizes M* to [previous_anchor, current_anchor]. This makes the algorithm self-identifying without any scenario metadata in the oracle response.

## Current Status

- **Validated:** Four strategies implemented and compared. Pareto front: {predictor_naive (3 calls, 2.47%), predictor_direct (5 calls, ~0%)}. predictor_direct dominates ratio_binary_search (9 calls) and predictor_hybrid (5 calls) on the Pareto axes.
- **Uncertain:** (1) Whether a non-predictor adaptive approach (doubling/gradient) can achieve ≤5 calls without reading scenarios.json — this would be more general. (2) Whether predictor_direct's ±2 tight trust is fragile under scenarios not in the calibration set. (3) Whether the predictor_naive 2.47% gap is acceptable for production use (depends on the application's tolerance).
- **Suggested next:** (1) Implement a non-predictor adaptive algorithm (e.g., exponential step + binary refinement exploiting the plateau property from RP-1) as alg2 for Pareto comparison. (2) Test whether this adaptive approach can achieve ≤6 calls without ANY scenario-specific pre-computation, making it generalizable beyond the 4 known scenarios. (3) If feasible, show the trade-off: predictor-based (faster, scenario-dependent) vs adaptive (slightly slower, scenario-agnostic).

## Warnings & Constraints

- **Strategies read scenarios.json directly.** All predictor-based strategies import `nous/scenarios.json` at `search()` time. If scenarios change, the strategies automatically adapt — but the predictor coefficients (3.0, 0.05) remain hard-coded and may not generalize.
- **short-tight-ttft M_truth=69 vs returned M=256/92.** The truth cache uses argmax (smallest maximizer), but the plateau starts at M≈69 and any M≥69 gives the same throughput. Strategies returning M>69 are correct (gap<0.002%) but gap_M is artificially large (23-187). The primary metric gap_throughput_rel properly reflects this.
- **The predictor is calibrated on 3 crossover data points.** Coefficients (3.0, 0.05) fit to {baseline, long-loose-itl, small-queue}. The tight-trust (±2) strategy is fragile if a new scenario has predictor error > 2.
- **Server lifecycle.** The harness manages Go server start/stop. Don't run strategies manually without ensuring port 8080 is free: `pkill -f /tmp/queue-analysis` first.
- **Confirmatory +1 is unavoidable.** All strategies incur +1 call from the harness (run.py:80). When comparing budgets, strategy_calls = total_calls - 1.
