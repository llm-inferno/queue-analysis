# Problem Framing — Iteration 5

## Research Question

Can a scenario-agnostic algorithm (no pre-computed M* estimates) achieve fewer oracle calls than full-range binary search (9 calls) while maintaining gap_throughput_rel ≈ 0? Specifically: what is the minimum worst-case call count achievable without scenario knowledge, and how does it compare to the predictor-based predictor_direct (5 calls)?

The mechanism under test: **interpolation search on the ratio R(M) = RPSTargetTTFT/RPSTargetITL.** Since R(M) is approximately linear within tight brackets (verified empirically), linear interpolation of the crossing point R=1.0 converges faster than pure binary search. Combined with early no-crossover detection (probe midpoint → probe m_max → exit if R<1.0), this should reduce worst-case calls from 9 to ≤7.

Key source files:
- `pkg/service/analyzer.go:118-160` — /target handler returning RPSTargetTTFT and RPSTargetITL.
- `pkg/analyzer/queueanalyzer.go:242` — `lambda := min(lambdaStarTTFT, lambdaStarITL, lambdaStarTPS)`.
- `nous/harness/run.py:76-80` — strategy return + confirmatory eval (+1 call).
- `nous/harness/strategies/ratio_binary_search.py` — the 9-call baseline to beat.

## System Interface

- **Build:** `go build -o /tmp/queue-analysis .`
- **Run harness:**
  ```bash
  source nous/.venv/bin/activate && python -m nous.harness.run \
      --scenarios nous/scenarios.json \
      --strategy nous/harness/strategies/<name>.py \
      --out <results-path>.json
  ```
- **Output format:** JSON array with per-scenario records: M_chosen, calls, throughput_chosen, M_truth, throughput_truth, gap_throughput_rel, gap_M, wall_clock_seconds, internal_solve_calls.
- **Code evidence:**
  - `nous/harness/run.py:106` — `--m-min` flag parsed.
  - `nous/harness/run.py:107` — `--m-max` flag parsed.
  - `nous/harness/run.py:108` — `--out` flag (native output).
  - `nous/harness/run.py:80` — confirmatory `eval_(m_chosen)` call counted.

## Baseline Command

```bash
source nous/.venv/bin/activate && python -m nous.harness.run \
    --scenarios nous/scenarios.json \
    --strategy nous/harness/strategies/ratio_binary_search.py \
    --out .nous/queue-throughput/runs/iter-5/results/baseline.json
```

## Baseline Validation

Validated on 2026-06-09. Exit code 0. Output:
```
[baseline] M=40 calls=9 gap_rel=0.0000
[short-tight-ttft] M=256 calls=9 gap_rel=0.0000
[long-loose-itl] M=93 calls=9 gap_rel=0.0000
[small-queue] M=38 calls=9 gap_rel=0.0000
```
All scenarios: 9 calls, gap=0. Confirms the 8-binary-step + 1-confirm = 9 prediction.

## Experimental Conditions

### Arm 1 (h-main): adaptive_interpolation
Strategy: `nous/harness/strategies/adaptive_interpolation.py`

Algorithm:
1. Probe at midpoint M=(m_min+1+m_max)//2=129.
2. If R>=1.0: search lower half [2, 128] with interpolation.
   If R<1.0: probe m_max. If R<1.0 there too, return m_max (no-crossover). Otherwise bracket [130, 255] with interpolation.
3. Once measured bracket established (both R<1.0 and R>=1.0 endpoints known), switch from binary midpoint to linear interpolation of crossing.

Command:
```bash
source nous/.venv/bin/activate && python -m nous.harness.run \
    --scenarios nous/scenarios.json \
    --strategy nous/harness/strategies/adaptive_interpolation.py \
    --out .nous/queue-throughput/runs/iter-5/results/h_main.json
```

### Arm 2 (h-control-negative): ratio_binary_search
Unchanged existing strategy. No interpolation, no early exit. Confirms that without both features, 9 calls is the cost.

Command: (same as baseline command above)

### Arm 3 (h-ablation): adaptive_binary
Same structure as adaptive_interpolation (smart midpoint start, early no-crossover exit) but ALWAYS uses midpoint bisection instead of interpolation. Tests whether interpolation specifically contributes.

Strategy: `nous/harness/strategies/adaptive_binary.py`

Command:
```bash
source nous/.venv/bin/activate && python -m nous.harness.run \
    --scenarios nous/scenarios.json \
    --strategy nous/harness/strategies/adaptive_binary.py \
    --out .nous/queue-throughput/runs/iter-5/results/h_ablation.json
```

### Arm 4 (h-robustness): adaptive_interpolation at m_max=512
Tests scaling behavior when the search range doubles. If interpolation provides O(log log N) benefit, the call increase should be exactly +1 per doubling.

Command:
```bash
source nous/.venv/bin/activate && python -m nous.harness.run \
    --scenarios nous/scenarios.json \
    --strategy nous/harness/strategies/adaptive_interpolation.py \
    --m-max 512 \
    --out .nous/queue-throughput/runs/iter-5/results/h_robustness.json
```

## Success Criteria

1. **h-main**: adaptive_interpolation achieves worst-case calls ≤ 7 with gap_throughput_rel = 0 for all 4 scenarios at m_max=256.
2. **h-control-negative**: ratio_binary_search achieves worst-case calls = 9 (unchanged baseline).
3. **h-ablation**: adaptive_binary achieves worst-case calls = 9 for crossover scenarios (same as ratio_binary_search), proving interpolation is load-bearing for the 7→9 reduction.
4. **h-robustness**: at m_max=512, adaptive_interpolation worst-case = 8 (exactly +1 per range doubling), confirming logarithmic scaling.

## Constraints

- Strategies must use only stdlib + requests (no numpy/scipy). (Per campaign constraint.)
- adaptive_interpolation must NOT read scenarios.json — it must be purely scenario-agnostic.
- gap_throughput_rel must be 0 for all arms (plateau landing is acceptable).
- Strategy return value must be in [m_min, m_max].
- Confirmatory +1 call overhead is unavoidable and counted.

## Prior Knowledge

Active principles applied:
- **RP-1**: f(M) is concave-rise then flat plateau. Validates that ANY M on the plateau gives gap≈0.
- **RP-2**: M* coincides with R(M) crossing 1.0. Foundation for ratio-based search.
- **RP-5**: The problem is plateau-onset detection. Validates returning m_max for no-crossover.
- **RP-6**: Binary search on R finds M* in O(log N). This is the baseline to beat.
- **RP-10**: No-crossover means R never reaches 1.0 at any M. Detected by probing R(m_max).
- **RP-11**: predictor_direct achieves 5 calls. The ceiling for comparison.
- **RP-12**: Current Pareto front has 2 points: (3, 2.47%) and (5, ~0%).
