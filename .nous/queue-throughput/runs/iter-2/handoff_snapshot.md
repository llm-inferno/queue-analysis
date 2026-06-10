# Handoff — Iteration 2

## Goal

Confirm that M* is findable in O(log N) oracle calls via binary search on the ratio R(M) = RPSTargetTTFT/RPSTargetITL crossing 1.0. Implement and test the `ratio_binary_search` strategy. Ablate single constraints to confirm the min(TTFT, ITL) mechanism is solely responsible for the two-phase structure.

## Key Discoveries

1. **R(M) = RPSTargetTTFT/RPSTargetITL is strictly monotone increasing for all M < M* in all scenarios.** Full-range probes (M=2..256) show zero monotonicity violations below M* for baseline, long-loose-itl, and small-queue. Violations only appear in the post-crossover plateau (M≥79 for small-queue) where they're irrelevant to optimization.

2. **R(M*) is the exact crossover point.** For baseline: R(39)=0.992116, R(40)=1.008669. For long-loose-itl: R(92)=0.998106, R(93)=1.001563. For small-queue: R(37)=0.994010, R(38)=1.012406. The ratio flips from <1 to >1 at exactly M_truth in all cases.

3. **Oracle responses include both rates.** The /target response contains `RPSTargetTTFT` and `RPSTargetITL` fields (confirmed at `pkg/service/analyzer.go:118`, response schema in `examples/solution-target.json`). Strategies can read these directly — no auxiliary probing needed.

4. **short-tight-ttft never crosses (max ratio ≈ 0.50).** R stays in [0.036, 0.498] for all M∈[2,256]. The strategy must detect this and fall back to a plateau-onset heuristic.

5. **Single-constraint ablation confirms mechanism:**
   - ITL-only (targetTTFT=9999): peaks at M=24, 3% drop to M=256. No plateau.
   - TTFT-only (targetITL=9999): monotone-then-flat (0.00008% noise). No crossover.
   - Both active: M*=40, flat plateau. The crossover is SOLELY from min(TTFT, ITL).

6. **First-difference ratio signature is unambiguous.** At crossover: df(M*)/df(M*-1) = 0.30-0.54. Normal concavity: 0.97-0.98. Separation > 0.44 in all crossover scenarios. This provides an independent confirmation mechanism.

7. **RPSTargetITL peaks at M≈24-25 then slowly decays to a limit (~2.166).** This is because decode time grows linearly with M (more concurrent requests → longer per-token iteration). RPSTargetTTFT grows monotonically because higher M increases total service capacity, reducing queue wait time which dominates TTFT.

## System Interface

- **Build:** `go build -o /tmp/queue-analysis .` (repo root)
- **Run harness:**
  ```bash
  source nous/.venv/bin/activate && python -m nous.harness.run \
      --scenarios nous/scenarios.json \
      --strategy nous/harness/strategies/ratio_binary_search.py \
      --out .nous/queue-throughput/runs/iter-2/results/arm_h_main.json
  ```
- **Output format:** JSON array of `{scenario, strategy, M_chosen, calls, throughput_chosen, M_truth, throughput_truth, gap_throughput_rel, gap_M, wall_clock_seconds, internal_solve_calls}`
- **Baseline result (linear scan M=[35,45]):** baseline M=40, calls=12, gap=0.0

## Code Map

- `pkg/analyzer/queueanalyzer.go:242` — `lambda := min(lambdaStarTTFT, lambdaStarITL, lambdaStarTPS)`. THE mechanism creating the two-phase structure. Check here to understand why ratio detection works.
- `pkg/analyzer/queueanalyzer.go:248-252` — `TargetRate` struct with RateTargetTTFT and RateTargetITL. These become RPSTargetTTFT and RPSTargetITL in the HTTP response.
- `pkg/analyzer/queueanalyzer.go:263-281` — `IterationTime`, `PrefillTime`, `DecodeTime`. Linear-in-M formulas. IterationTime(M) = Alpha + M*(Beta*tokensCompute + Gamma*tokensMemory). Explains why RPSTargetITL peaks then decays.
- `pkg/analyzer/queueanalyzer.go:103-108` — Service rate computation. `servRate[n-1] = n / (PrefillTime(n) + AvgOut * DecodeTime(n))`. Sublinear growth of service rate with M causes TTFT to grow slower than linear.
- `pkg/service/analyzer.go:118` — `/target` handler. Assembles the full response JSON including both target rates.
- `nous/harness/oracle.py:42-54` — Oracle wrapper. HTTP 400 → `{"throughput": 0.0}`, no call count. Infeasible responses lack RPSTargetTTFT/RPSTargetITL fields.
- `nous/harness/run.py:53-98` — `run_strategy_on_scenario`. The +1 confirmatory call is at line 80.
- `nous/harness/run.py:76` — Strategy return value bounds check: `m_min <= m_chosen <= m_max`.
- `nous/cache/truth-*.json` — Pre-computed truth. Structure: `{scenario, M_truth, throughput_truth, f_curve: [{m, throughput}, ...]}`.

## Code Targets

### ratio_binary_search.py (new file)
- Location: `nous/harness/strategies/ratio_binary_search.py`
- Interface: `def search(target_eval, m_min, m_max) -> int`
- Algorithm:
  1. Binary search on R(M) = RPSTargetTTFT/RPSTargetITL crossing 1.0
  2. lo=m_min, hi=m_max. At each step: m_mid=(lo+hi)//2, eval(m_mid), check R.
  3. If R(m_mid) < 1.0: lo = m_mid + 1. If R >= 1.0: hi = m_mid.
  4. Terminates when lo == hi. Return lo (this is M*).
  5. Fallback: if all probed R values are < 1.0 when lo=hi=m_max, the scenario has no crossover. In this case, return the M from among evaluated points that had the highest throughput (already observed during the binary search).
- Key detail: infeasible M (throughput=0.0, no RPSTargetTTFT field) should be treated as "too low" (lo = m_mid + 1) since infeasibility only occurs at M=1.

### probe_ablation.py (analysis script, already created)
- Location: `.nous/queue-throughput/runs/iter-2/inputs/probe_ablation.py`
- Run directly: `python .nous/queue-throughput/runs/iter-2/inputs/probe_ablation.py 2>/dev/null > results.json`
- Queries oracle directly (not through harness) for ITL-only and TTFT-only shapes.

### analyze_diff_ratios.py (analysis script, already created)
- Location: `.nous/queue-throughput/runs/iter-2/inputs/analyze_diff_ratios.py`
- Run directly: `python .nous/queue-throughput/runs/iter-2/inputs/analyze_diff_ratios.py > results.json`
- Operates on truth cache files to compute first-difference ratio signatures.

## What I Tried That Didn't Work

- **Checking if the ratio is globally monotone**: small-queue has 93 violations for M > 78 (in the deep plateau where binary-search noise dominates). This means the ratio is NOT globally monotone — it's only monotone up to and through the crossover. The binary search must not overshoot into the post-crossover noise zone.
- **Assuming TTFT-only is strictly monotone**: it's flagged as `is_monotone: false` because binary-search noise in the Go analyzer creates micro-violations past M=88. Effectively monotone (0.00008% noise) but technically not.
- **Ablation through the harness**: the harness requires truth cache files. Ablation scenarios (modified targetITL/targetTTFT) don't have caches. Must probe the oracle directly for ablation.

## What I Excluded and Why

- **Closed-form predictor for M***: That's iter-3's goal. We have the data (RPSTargetITL peaks at M≈24-25, RPSTargetTTFT crosses it at M=40) but developing a predictor from {AvgOut, targetITL, targetTTFT, beta, gamma} requires more analysis of how these parameters shift the crossover.
- **Algorithm comparison**: That's iter-4-5. This iteration only confirms the ratio-based detection works.
- **Testing robustness under parameter perturbation**: The campaign specifies 4 fixed scenarios. Adding scenarios is out of scope.
- **Multi-point strategies (e.g., bracketing + interpolation)**: Premature optimization. First confirm the O(log N) binary search baseline works.

## Evolution of Thinking

Started with the iter-1 suggestion to "quantify concavity and test single-constraint ablation." The concavity analysis revealed that while df(M*)/df(M*-1) is a detectable signature (ratio < 0.55 vs normal 0.97), it requires evaluating consecutive M values — not directly useful for a binary search.

The breakthrough came from examining the oracle's auxiliary fields (RPSTargetTTFT, RPSTargetITL). Since M* is defined as the crossover point (RP-2), and the ratio R = TTFT/ITL is monotonically increasing, binary search on R crossing 1.0 is the natural O(log N) algorithm. This is simpler and more robust than any throughput-based detection because it uses a monotone signal (ratio) rather than a nearly-flat signal (throughput differences).

The ablation confirmed that the two-phase structure is purely a `min(TTFT, ITL)` artifact — neither constraint alone produces the exploitable shape. This validates that the ratio-based approach is attacking the fundamental mechanism, not a coincidental property.

The short-tight-ttft scenario (no crossover) requires special handling. The fallback strategy (return max-throughput point from binary search observations) is adequate because in the no-crossover case, the binary search still evaluates O(log N) points across [2, 256], providing good coverage of the flat plateau.

## Current Status

- **Validated:** Ratio R(M) monotonicity up to M* (zero violations for all crossover scenarios). Exact crossover detection at M_truth. Single-constraint ablation confirms mechanism. First-difference signature analysis complete.
- **Uncertain:** (1) Whether the fallback for no-crossover cases (return highest-throughput observed) gives gap < 0.001 with the limited points from binary search. (2) Whether the ratio binary search's log2(255)=8 calls is competitive against simpler strategies that exploit the plateau property (e.g., "evaluate M=30, if throughput > 0 and in plateau, done").
- **Suggested next:** (1) After confirming ratio_binary_search works (this iter), develop a closed-form predictor for M* from input parameters (iter 3). The crossover condition is RPSTargetTTFT(M) = RPSTargetITL(M); analyze how this depends on {AvgOut, targetITL, targetTTFT, alpha, beta, gamma}. (2) Consider a hybrid: predictor gives M_est, then 1-2 oracle calls confirm (iter 4 algorithm).

## Warnings & Constraints

- **Infeasible responses lack ratio fields.** When M=1 returns 400 → `{"throughput": 0.0}`, there's no RPSTargetTTFT/RPSTargetITL. The strategy must handle this case (treat as lo = m_mid + 1 since infeasibility is always at the low end).
- **Ratio is only monotone BELOW the crossover.** Post-crossover (M > M*), the ratio may fluctuate due to binary-search noise in the Go analyzer. The binary search naturally avoids this region (once R ≥ 1.0 is found, hi shrinks), but edge cases around M* should be tested.
- **The harness adds +1 confirmatory call.** Strategy budgets: log2(255)=8 search calls + 1 confirmatory = 9 total. This is well under the brute-force 256 calls.
- **short-tight-ttft's "M_truth=69" is irrelevant.** The strategy should not try to find M=69. Any M ≥ 26 is within 0.003% of peak. The fallback just needs to land on the plateau.
- **Don't probe M=1 inside binary search.** It's infeasible (free but wastes a binary search step). The initial lo should be m_min=1 or 2 — but since the harness may set m_min=1, handle the infeasible response gracefully.
