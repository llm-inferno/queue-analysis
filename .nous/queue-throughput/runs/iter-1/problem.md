# Problem Framing — Iteration 1

## Research Question

Characterize the structural properties of f(M) = max-RPS-meeting-targets as a function of MaxBatchSize M, focusing on the **baseline** scenario.

Specifically:
1. **Is f(M) unimodal?** Does it have a single peak with monotone rise and monotone descent?
2. **What causes the peak?** Which constraint (TTFT vs ITL) binds at different M values?
3. **How flat is the plateau?** After the peak, does f decay meaningfully or stay essentially constant?
4. **Is the rising portion concave?** Does the first difference df/dM decrease monotonically?

The /target endpoint (`pkg/service/analyzer.go:118`) computes throughput as `min(RPSTargetTTFT, RPSTargetITL)` via binary search in `pkg/analyzer/queueanalyzer.go:183`. The peak corresponds to the crossover point where RPSTargetTTFT = RPSTargetITL — below this M, TTFT binds; above, ITL binds.

## System Interface

- **Build command:** `go build -o /tmp/queue-analysis .` (from repo root)
- **Run server:** Handled automatically by `nous/harness/server.py` which calls `go run main.go`
- **Harness CLI:**
  ```
  python -m nous.harness.run \
      --scenarios nous/scenarios.json \
      --strategy nous/harness/strategies/<name>.py \
      --m-min 1 --m-max 256 \
      --out <results-path>.json
  ```
- **Output format:** JSON array of records, one per scenario, with fields: `scenario`, `strategy`, `M_chosen`, `calls`, `throughput_chosen`, `M_truth`, `throughput_truth`, `gap_throughput_rel`, `gap_M`, `wall_clock_seconds`.

### Code evidence
- `/target` endpoint definition: `pkg/service/analyzer.go:49`
- `Size()` function (binary search for max-RPS): `pkg/analyzer/queueanalyzer.go:183`
- Throughput = `min(lambdaStarTTFT, lambdaStarITL)`: `pkg/analyzer/queueanalyzer.go:242`
- Service rate computation (state-dependent): `pkg/analyzer/queueanalyzer.go:103-108`
- Oracle wrapper (returns `{"throughput": 0.0}` on 400): `nous/harness/oracle.py:42-54`
- Strategy contract: `nous/harness/strategies/example_linear_scan.py:11`
- Truth cache structure: `nous/cache/truth-<scenario>.json` — dict with keys `scenario`, `M_truth`, `throughput_truth`, `f_curve` (list of `{m, throughput}`)

## Baseline Command

```bash
source nous/.venv/bin/activate && python -m nous.harness.run \
    --scenarios nous/scenarios.json \
    --strategy nous/harness/strategies/example_linear_scan.py \
    --m-min 35 --m-max 45 \
    --out .nous/queue-throughput/runs/iter-1/results/baseline_smoke.json
```

## Baseline Validation

Command exits 0. Output for baseline scenario: `M_chosen=40, calls=12, gap_throughput_rel=0.0`. Full output written to `/tmp/nous_smoke_test.json`. The harness correctly counts 11 strategy calls + 1 confirmatory = 12 total.

## Experimental Conditions

This is an **observe-mode** iteration. No code changes are needed. The experiment analyzes the pre-computed truth cache (`nous/cache/truth-baseline.json`) and live oracle queries to characterize f(M) properties.

### Condition 1: Shape characterization from truth cache
- Analyze `nous/cache/truth-baseline.json` f_curve for: monotonicity, plateau flatness, transition width, concavity.
- No oracle calls needed — data already exists.

### Condition 2: Binding constraint identification via live oracle
- Query the Go server at selected M values (5, 10, 20, 30, 35, 38, 39, 40, 41, 45, 50, 80, 256).
- Record `RPSTargetTTFT` and `RPSTargetITL` from each response to identify the crossover M.
- Command: direct HTTP POST to `localhost:8080/target` (server started by harness).

### Condition 3: Cross-scenario robustness check
- Repeat conditions 1-2 for all 4 scenarios to test if the two-phase structure (rise → plateau) is universal.

## Success Criteria

The hypotheses will be confirmed if:
1. **Unimodality**: The rising portion (M=2..M*) is strictly monotone increasing with at most numerical-noise violations (< 0.01% of peak).
2. **Plateau flatness**: For M > M*, f(M) varies by < 0.15% of f* across all scenarios.
3. **Concavity**: The first difference df/dM is decreasing for M ≥ 8 (after a brief convex onset).
4. **Binding crossover**: The peak coincides with the M where RPSTargetTTFT first exceeds RPSTargetITL.

## Constraints

- Iter 1 is observe-mode: no code_changes to strategy files.
- Only the baseline scenario is the primary target; other scenarios provide robustness evidence.
- The truth cache must not be regenerated (already populated).

## Prior Knowledge

This is the first iteration. No active principles exist yet. The campaign brief establishes:
- M_min=1, M_max=256 (fixed search range).
- 4 named scenarios with known M* values from brute-force scan.
- Infeasibility at M=1 for all scenarios (oracle returns 400).
