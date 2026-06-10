# Handoff — Iteration 3

## Goal

Validate a closed-form predictor for M* that requires zero oracle calls, achieving |M_est - M*| ≤ 5 for all crossover scenarios, and correctly detecting the no-crossover case via the sign of wait_budget.

## Key Discoveries

1. **At the crossover M*, the ITL constraint forces avg batch occupancy to n_ITL = (targetITL - d_intercept) / d_slope.** Verified via /solve: baseline avgNumInServ=22.26 vs predicted n_ITL=23.25 (error < 1 unit). DecodeTime is affine in batch size, so the ITL target directly determines the operating point. (`pkg/analyzer/queueanalyzer.go:278-280`)

2. **M* exceeds n_ITL by a "stochastic buffer" proportional to sqrt(n_ITL) plus a wait-budget correction.** The formula M_est = round(n_ITL + 3.0*sqrt(n_ITL) + 0.05*wait_budget) achieves max error = 2 across all 3 crossover scenarios: baseline (error=2), long-loose-itl (error=2), small-queue (error=0).

3. **Queue occupancy at the crossover is near zero.** From /solve at (M*, lambda=f*): baseline N_queue=0.016, long-loose-itl N_queue=0.159, small-queue N_queue=0.016. The system runs well below M* capacity at the crossover rate, so the buffer term is purely about stochastic fluctuation headroom — not actual queueing.

4. **Crossover existence is determined by sign(wait_budget).** wait_budget = targetTTFT - targetITL - PrefillTime(n_ITL). Positive for all 3 crossover scenarios (7.38, 107.51, 7.38 ms). Negative for short-tight-ttft (-11.29 ms). Perfect classification.

5. **Ablation confirms wait_budget term is load-bearing.** Without it: long-loose-itl error jumps from 2 to 8 (the only scenario with large wait_budget=107ms). Baseline and small-queue unaffected (their 0.05*7.38 ≈ 0.37 rounds to nothing).

6. **L_ITL (limiting ITL rate) is predictable from n_ITL.** L_ITL ≈ n_ITL / ServiceTime(n_ITL) * 1000. Error: baseline 4.5%, long-loose-itl 1.6%. The ITL rate limit is insensitive to M (confirmed by iter-2) and insensitive to queueSize (baseline=small-queue have identical L_ITL).

7. **The predictor enables a 44% call reduction.** If |M_est - M*| ≤ 2, a binary search on [M_est-5, M_est+5] (width 11) finds M* in ceil(log2(11))=4 calls. Total: 4+1=5 vs 8+1=9 for full binary search.

## System Interface

- **Build:** `go build -o /tmp/queue-analysis .` (repo root)
- **Run predictor experiment:**
  ```bash
  python3 .nous/queue-throughput/runs/iter-3/inputs/run_predictor.py
  python3 .nous/queue-throughput/runs/iter-3/inputs/run_predictor.py --no-wait-budget
  ```
- **Run harness:**
  ```bash
  source nous/.venv/bin/activate && python -m nous.harness.run \
      --scenarios nous/scenarios.json \
      --strategy nous/harness/strategies/<name>.py \
      --out <results-path>.json
  ```
- **Output format:** JSON with per-scenario records: M_chosen, calls, throughput_chosen, M_truth, throughput_truth, gap_throughput_rel, gap_M, wall_clock_seconds, internal_solve_calls.
- **Predictor result (baseline):** M_est=38, M_truth=40, error=2, max_error=2, all_within_5=True.

## Code Map

- `pkg/analyzer/queueanalyzer.go:242` — `lambda := min(lambdaStarTTFT, lambdaStarITL, lambdaStarTPS)`. THE mechanism creating the two-phase structure. M* is where these two rates cross.
- `pkg/analyzer/queueanalyzer.go:263-266` — IterationTime(M) = alpha + M*(beta*tc + gamma*tm). Foundation of the linear DecodeTime relationship.
- `pkg/analyzer/queueanalyzer.go:278-280` — DecodeTime(M) = IterationTime(M) + beta + gamma*(avgIn + (avgOut+1)/2). AFFINE in M. This is why n_ITL = (targetITL - d_intercept) / d_slope works.
- `pkg/analyzer/queueanalyzer.go:270-274` — PrefillTime(M) = IterationTime(M) + (beta+gamma)*avgIn. Used in the wait_budget computation.
- `pkg/analyzer/queueanalyzer.go:103-107` — Service rate at state n: n / (PrefillTime(n) + avgOut*DecodeTime(n)). Governs L_ITL limit.
- `pkg/service/analyzer.go:118-160` — /target handler. Response includes RPSTargetTTFT and RPSTargetITL for ratio-based searches.
- `nous/harness/oracle.py:42-54` — Oracle wrapper. HTTP 400 → {"throughput": 0.0}, no call count.
- `nous/harness/run.py:76-80` — Strategy return value check + confirmatory eval.
- `nous/cache/truth-*.json` — Pre-computed truth with f_curve for all scenarios.
- `.nous/queue-throughput/runs/iter-3/inputs/run_predictor.py` — The predictor test script. Takes `--no-wait-budget` for ablation.

## Code Targets

### predictor_hybrid.py (to be created in iter-4)
- Location: `nous/harness/strategies/predictor_hybrid.py`
- Interface: `def search(target_eval, m_min, m_max) -> int`
- Algorithm:
  1. Need scenario params (avgIn, avgOut, targetITL, targetTTFT) to compute M_est.
  2. The harness's target_eval closure binds these params but doesn't expose them to the strategy.
  3. **Solution for iter-4:** Either (a) modify the oracle to include scenario params in the response, (b) extract them from the first probe's behavior, or (c) pass them via a strategy config mechanism.
  4. Once M_est is computed: binary search ratio R(M) in [M_est-5, M_est+5].
  5. Fallback: if narrow window doesn't bracket crossover, widen to [M_est-10, M_est+10] (+1 call) or fall back to full [m_min, m_max].

## What I Tried That Didn't Work

- **Fitting RPSTargetTTFT(M) to a saturating curve (a*M/(b+M)).** Linearization gave negative coefficients; the functional form doesn't match the actual shape which has a convex onset followed by concave approach to limit.
- **M/M/1 approximation for WaitTime.** The standard M/M/1 wait formula gives grossly wrong values (804ms vs actual 6ms) because the state-dependent model has much lower effective utilization than a simple M/M/1.
- **Constant multiplier predictor (M* = c * n_ITL).** Best constant is c≈1.5 (max error=5) but can't achieve ≤2 error because the ratio M*/n_ITL varies from 1.50 to 1.72 depending on the scenario.
- **Linear interpolation of R(M) from 2 reference probes.** R(M) is not linear in M (it has a convex onset), so linear interpolation from widely-spaced probes overshoots badly.
- **Quarter/three-quarter reference probes for narrow search.** For baseline (M*=40 in [2,256]), the 25% point (M=65) is already past M*, so the narrowing doesn't help — still needs full binary search on [2, 65].

## What I Excluded and Why

- **Solving the full state-dependent queue model analytically.** The steady-state distribution of the birth-death process has no useful closed form for predicting M*. The predictor works from first principles (DecodeTime linearity + stochastic buffer) without needing queue-model inversion.
- **Generalizing the predictor to varying alpha/beta/gamma.** The campaign uses fixed hardware params. Generalizing would require probing at multiple (alpha, beta, gamma) settings and fitting the buffer coefficient, which is out of scope.
- **Implementing the full hybrid strategy.** The strategy needs scenario params injected. The harness currently passes only (target_eval, m_min, m_max). Modifying the harness interface is an iter-4 concern.
- **Testing with queueSize sensitivity.** Baseline vs small-queue shows queueSize shifts M* by only 2. The predictor doesn't use queueSize and still achieves error ≤ 2. Queue size effects are negligible for practical purposes.

## Evolution of Thinking

Started by trying to predict M* from the "shape" of RPSTargetTTFT(M) — fitting functional forms, computing service rates analytically, etc. This failed because RPSTargetTTFT involves the full queue model solution.

The breakthrough was switching from "predict where TTFT rate equals ITL rate" to "what determines the avg occupancy at crossover, and how much headroom above it does M* need?" The answer: DecodeTime is linear in batch size (from the code), so n_ITL = (targetITL - intercept) / slope gives the exact operating point. The buffer above n_ITL follows sqrt(n) scaling (stochastic fluctuation), with a small correction for the wait-time budget.

The final insight: queue occupancy at crossover is essentially ZERO (0.016 requests). The system never queues at the crossover rate — it's running in a regime where all arriving requests go straight into service. M* is about having enough SERVICE capacity to handle fluctuations, not about queue management.

## Current Status

- **Validated:** Predictor formula M_est = round(n_ITL + 3.0*sqrt(n_ITL) + 0.05*wait_budget). Max error = 2. Crossover detection via sign(wait_budget) is perfect. Ablation confirms wait_budget term is necessary for long-loose-itl.
- **Uncertain:** (1) Whether the buffer coefficient 3.0 is universal or scenario-specific (only 3 data points). (2) Whether the 0.05 wait_budget coefficient holds for extreme wait budgets (only tested up to 107ms). (3) How to inject scenario params into the strategy interface for the hybrid approach.
- **Suggested next:** (1) Implement the full predictor_hybrid strategy (iter-4). Design choice: either extend the harness to pass scenario params to the strategy, or have the strategy infer params from a reference probe. (2) Compare predictor_hybrid (predicted 5 calls) vs ratio_binary_search (9 calls) vs a simpler "golden-section on throughput" approach. (3) For the no-crossover case: the predictor detects it but doesn't identify M_plateau_onset. A useful extension: predict the plateau onset for no-crossover scenarios using a similar closed-form approach.

## Warnings & Constraints

- **Strategy doesn't have scenario params.** The current harness interface `search(target_eval, m_min, m_max)` doesn't pass (avgIn, avgOut, targetITL, targetTTFT). For iter-4's hybrid strategy, you'll need to either: (a) add a `scenario` param to the search interface, (b) embed the predictor in the harness (before calling the strategy), or (c) infer params from the first oracle response. Option (a) is cleanest but changes the interface.
- **The predictor is calibrated on 3 crossover data points.** The coefficients (3.0, 0.05) are fit to {baseline, long-loose-itl, small-queue}. With only 3 points and 2 free parameters, overfitting is possible. Use the predictor as a warm-start (±5 safety margin), not as a point estimate.
- **The nous/.venv doesn't have numpy/scipy.** Only stdlib and `requests` are available. All analysis scripts use pure Python math.
- **Server port conflicts.** The harness manages the Go server lifecycle. When running scripts that probe the oracle directly, ensure no other instance is on :8080. Use `pkill -f /tmp/queue-analysis` before starting.
- **DecodeTime approximation.** The predictor uses DT(n_ITL) ≈ targetITL, but the actual EvalITL function finds the max lambda where avg decode time = targetITL across the state distribution. The avg occupancy at that rate is slightly below n_ITL (observed: 22.26 vs predicted 23.25 — because the avg is over all states, not just the modal state). This 1-unit discrepancy is absorbed by the ±5 safety margin.
