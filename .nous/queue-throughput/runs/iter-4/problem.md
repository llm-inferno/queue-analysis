# Problem Framing — Iteration 4

## Research Question

What is the minimum oracle-call budget that achieves gap_throughput_rel = 0 across all scenarios? Quantify the Pareto front of (worst-case calls, worst-case gap) by implementing and comparing four algorithm variants that trade predictor reliance against call count.

The mechanism under test: the closed-form predictor (iter-3, RP-9) narrows the search space from [2, 256] to a ±2 window around M_est, and the ratio test R(M) = RPSTargetTTFT/RPSTargetITL pinpoints the exact crossover within that window. The hypothesis is that these two components together achieve 44% call reduction vs pure binary search, and that removing either component degrades performance measurably.

Key source files:
- `pkg/service/analyzer.go:118-160` — /target handler returning RPSTargetTTFT, RPSTargetITL
- `pkg/analyzer/queueanalyzer.go:242` — min(lambdaStarTTFT, lambdaStarITL) mechanism
- `nous/harness/run.py:76-80` — Strategy return + confirmatory call (+1)
- `nous/harness/oracle.py:42-54` — Oracle wrapper, 400→{throughput:0}, no-count

## System Interface

- **Build:** `go build -o /tmp/queue-analysis .` (from repo root)
- **Run harness:**
  ```bash
  source nous/.venv/bin/activate && python -m nous.harness.run \
      --scenarios nous/scenarios.json \
      --strategy nous/harness/strategies/<name>.py \
      --out <results-path>.json
  ```
- **Strategy interface:** `def search(target_eval, m_min: int, m_max: int) -> int`
- **Oracle response fields:** `throughput`, `RPSTargetTTFT`, `RPSTargetITL` (all floats)
- **Call counting:** oracle increments stat.calls per successful call; HTTP 400 does NOT count.
- **Confirmatory overhead:** harness adds exactly +1 call after strategy returns.

**Code evidence:**
- Strategy loading: `nous/harness/run.py:31-41` — imports `search` from strategy file
- Confirmatory call: `nous/harness/run.py:80` — `final = eval_(m_chosen)`
- Call counting: `nous/harness/oracle.py:52` — `stats.calls += 1`
- Scenario loading: `nous/harness/scenarios.py` via `load_campaign()`

## Baseline Command

```bash
source nous/.venv/bin/activate && python -m nous.harness.run \
    --scenarios nous/scenarios.json \
    --strategy nous/harness/strategies/predictor_direct.py \
    --out .nous/queue-throughput/runs/iter-4/results/predictor_direct.json
```

## Baseline Validation

Exit code 0. Output:
```
[baseline] M=40 calls=4 gap_rel=0.0000
[short-tight-ttft] M=256 calls=5 gap_rel=0.0000
[long-loose-itl] M=93 calls=5 gap_rel=0.0000
[small-queue] M=38 calls=3 gap_rel=0.0000
```
Worst-case: 5 calls, gap=0.

## Experimental Conditions

### Arm 1: h-main — predictor_direct
Strategy file: `nous/harness/strategies/predictor_direct.py`
```bash
source nous/.venv/bin/activate && python -m nous.harness.run \
    --scenarios nous/scenarios.json \
    --strategy nous/harness/strategies/predictor_direct.py \
    --out .nous/queue-throughput/runs/iter-4/results/predictor_direct.json
```

### Arm 2: h-control-negative — ratio_binary_search
Strategy file: `nous/harness/strategies/ratio_binary_search.py`
```bash
source nous/.venv/bin/activate && python -m nous.harness.run \
    --scenarios nous/scenarios.json \
    --strategy nous/harness/strategies/ratio_binary_search.py \
    --out .nous/queue-throughput/runs/iter-4/results/ratio_binary_search.json
```

### Arm 3: h-ablation — predictor_naive
Strategy file: `nous/harness/strategies/predictor_naive.py`
```bash
source nous/.venv/bin/activate && python -m nous.harness.run \
    --scenarios nous/scenarios.json \
    --strategy nous/harness/strategies/predictor_naive.py \
    --out .nous/queue-throughput/runs/iter-4/results/predictor_naive.json
```

### Arm 4: h-robustness — predictor_hybrid
Strategy file: `nous/harness/strategies/predictor_hybrid.py` (existing)
```bash
source nous/.venv/bin/activate && python -m nous.harness.run \
    --scenarios nous/scenarios.json \
    --strategy nous/harness/strategies/predictor_hybrid.py \
    --out .nous/queue-throughput/runs/iter-4/results/predictor_hybrid.json
```

## Success Criteria

1. **h-main (predictor_direct):** worst-case calls ≤ 5, gap_throughput_rel = 0 for all 4 scenarios.
2. **h-control-negative (ratio_binary_search):** worst-case calls = 9, gap_throughput_rel = 0 for all 4 scenarios. Confirms the no-predictor baseline.
3. **h-ablation (predictor_naive):** worst-case gap_throughput_rel > 0 for at least one scenario (demonstrates refinement necessity). Expected: baseline gap ≈ 2.47%.
4. **h-robustness (predictor_hybrid):** worst-case calls ≤ 5, gap = 0, mean calls ≥ mean of predictor_direct (validates conservative radius doesn't improve worst-case).

## Constraints

- All strategies must implement `search(target_eval, m_min, m_max) -> int`.
- No changes to the Go analyzer or harness infrastructure.
- Strategies may read `nous/scenarios.json` to compute M_est values.
- The predictor coefficients (3.0, 0.05) from RP-9 are fixed.
- Pareto comparison uses worst-case across all 4 scenarios (primary), mean (secondary).

## Prior Knowledge

- RP-1: f(M) is two-phase: concave rise to M*, then flat plateau (variation < 0.08%).
- RP-2: M* = smallest M where RPSTargetTTFT first exceeds RPSTargetITL.
- RP-5: The problem is plateau-onset detection.
- RP-6: Full binary search on ratio requires 8+1=9 calls.
- RP-9: Predictor M_est = round(n_ITL + 3.0*sqrt(n_ITL) + 0.05*wait_budget), max error ≤ 2.
- RP-10: sign(wait_budget) classifies crossover vs no-crossover perfectly.
- RP-11: Predictor-guided hybrid achieves 5 calls, gap=0 (44% reduction from 9).
