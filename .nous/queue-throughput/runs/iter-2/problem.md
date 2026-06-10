# Iteration 2 — Problem Framing

## Research Question

Can the crossover point M* (where RPSTargetTTFT first exceeds RPSTargetITL) be detected in O(log N) oracle calls via binary search on the ratio R(M) = RPSTargetTTFT(M) / RPSTargetITL(M)?

Specifically:
1. Is R(M) strictly monotonically increasing for M in [2, M*] across all scenarios?
2. Does R(M*) ≥ 1.0 exactly at the throughput-optimal M?
3. For scenarios without a crossover (ratio never reaches 1.0), can the binary search detect the "permanently bound" case and fall back to a plateau-onset heuristic?

Source files implementing the mechanism:
- `pkg/analyzer/queueanalyzer.go:242` — `lambda := min(lambdaStarTTFT, lambdaStarITL, lambdaStarTPS)` — the min operation that creates the two-phase structure.
- `pkg/analyzer/queueanalyzer.go:248-252` — `TargetRate` struct returned to the HTTP handler, providing RPSTargetTTFT and RPSTargetITL fields.
- `pkg/service/analyzer.go:118` — `/target` handler assembling the response JSON with both rate components visible to the strategy.

## System Interface

- **Build:** `go build -o /tmp/queue-analysis .` (from repo root)
- **Harness CLI:**
  ```bash
  source nous/.venv/bin/activate && python -m nous.harness.run \
      --scenarios nous/scenarios.json \
      --strategy nous/harness/strategies/<name>.py \
      --out <results-path>.json
  ```
- **CLI flags:**
  - `--scenarios` (required): path to scenarios JSON (`nous/scenarios.json`)
  - `--strategy` (required): path to strategy Python file
  - `--out` (required): output JSON path
  - `--m-min` (optional, default from scenarios.json): minimum M to search
  - `--m-max` (optional, default from scenarios.json): maximum M to search
  - `--cache-dir` (optional, default `nous/cache`): truth cache directory
  - `--port` (optional, default 8080): analyzer port
- **Code evidence:**
  - `--scenarios` parsed at `nous/harness/run.py:102`
  - `--strategy` parsed at `nous/harness/run.py:103`
  - `--out` parsed at `nous/harness/run.py:105`
  - `--m-min`/`--m-max` parsed at `nous/harness/run.py:104`, defaults from `config.m_min`/`config.m_max`
- **Output format:** JSON array of records, each with fields: `scenario`, `strategy`, `M_chosen`, `calls`, `throughput_chosen`, `M_truth`, `throughput_truth`, `gap_throughput_rel`, `gap_M`, `wall_clock_seconds`, `internal_solve_calls`
- **Oracle response fields available to strategies:** `offeredRPS`, `throughput`, `avgRespTime`, `avgWaitTime`, `avgNumInServ`, `avgTTFT`, `avgITL`, `maxRPS`, `RPSTargetTTFT`, `RPSTargetITL`
- **Infeasibility:** HTTP 400 → `{"throughput": 0.0}`, not counted against call budget (`nous/harness/oracle.py:45-50`)

## Baseline Command

```bash
source nous/.venv/bin/activate && python -m nous.harness.run \
    --scenarios nous/scenarios.json \
    --strategy nous/harness/strategies/example_linear_scan.py \
    --m-min 35 --m-max 45 \
    --out .nous/queue-throughput/runs/iter-2/results/baseline_smoke.json
```

## Baseline Validation

Ran successfully. Exit code 0. Output:
```
[baseline] M=40 calls=12 gap_rel=0.0000
[short-tight-ttft] M=40 calls=12 gap_rel=0.0000
[long-loose-itl] M=45 calls=12 gap_rel=0.2607
[small-queue] M=38 calls=12 gap_rel=0.0000
wrote 4 records to .nous/queue-throughput/runs/iter-2/results/baseline_smoke.json
```

## Experimental Conditions

### Arm 1: h-main — Ratio monotonicity and crossover detection

**Prediction:** For all scenarios with a crossover (baseline, long-loose-itl, small-queue), the ratio R(M) = RPSTargetTTFT(M) / RPSTargetITL(M) is strictly monotone increasing in the range [2, M*+5], and R(M*) is the first M where R ≥ 1.0.

**Method:** Write a strategy (`ratio_binary_search.py`) that binary-searches on R(M) crossing 1.0. For each scenario, the strategy:
1. Evaluates R at `m_mid = (lo + hi) // 2`
2. If R < 1.0, set `lo = m_mid + 1`; if R ≥ 1.0, set `hi = m_mid`
3. Terminates when `lo == hi`
4. If the search converges to m_max without finding R ≥ 1.0 (no-crossover case), falls back to returning M where throughput first exceeded 99% of the observed max.

**Command:**
```bash
source nous/.venv/bin/activate && python -m nous.harness.run \
    --scenarios nous/scenarios.json \
    --strategy nous/harness/strategies/ratio_binary_search.py \
    --out .nous/queue-throughput/runs/iter-2/results/arm_h_main.json
```

**Code changes:**
- `nous/harness/strategies/ratio_binary_search.py` — new file implementing the ratio binary search strategy.

### Arm 2: h-ablation — Single-constraint f(M) shape

**Prediction:** When only one constraint is active:
- ITL-only (targetTTFT=9999): f(M) peaks early (M≈25 for baseline) and decays — no flat plateau.
- TTFT-only (targetITL=9999): f(M) is purely monotone increasing with no crossover — plateau only at physical capacity limits (M≈200+).

The two-phase structure and sharp crossover at M=40 are entirely caused by the `min(TTFT, ITL)` interaction. Neither constraint alone produces the optimizable two-phase shape.

**Method:** Create modified scenario files with one constraint relaxed (set to 9999). Run the linear scan strategy on the full [2, 256] range to characterize the shape.

**Command (ITL-only ablation):**
```bash
source nous/.venv/bin/activate && python -m nous.harness.run \
    --scenarios .nous/queue-throughput/runs/iter-2/inputs/scenarios_itl_only.json \
    --strategy nous/harness/strategies/example_linear_scan.py \
    --out .nous/queue-throughput/runs/iter-2/results/arm_ablation_itl_only.json
```

**Command (TTFT-only ablation):**
```bash
source nous/.venv/bin/activate && python -m nous.harness.run \
    --scenarios .nous/queue-throughput/runs/iter-2/inputs/scenarios_ttft_only.json \
    --strategy nous/harness/strategies/example_linear_scan.py \
    --out .nous/queue-throughput/runs/iter-2/results/arm_ablation_ttft_only.json
```

### Arm 3: h-control-negative — No-crossover scenario

**Prediction:** For short-tight-ttft, the ratio R(M) never reaches 1.0 (max ≈ 0.50). The ratio binary search strategy should detect this (search converges to m_max) and invoke its fallback path, returning an M on the plateau with gap_throughput_rel < 0.001.

**Method:** The h-main strategy already covers this scenario. This arm specifically validates the fallback behavior.

**Command:** Same as h-main (short-tight-ttft is included in the scenarios).

### Arm 4: h-robustness — First-difference ratio signature

**Prediction:** For all scenarios with a crossover, the first-difference ratio df(M*)/df(M*-1) drops to < 0.55 at the crossover point, while the "normal concavity" ratio df(M)/df(M-1) for M in the rising region stays in [0.96, 0.99]. The ratio drop at M* is at least 2x larger than any normal concavity variation.

**Method:** Analyze the f-curves from the truth cache. Compute first-difference ratios for all M and verify the signature.

**Command:** Python analysis script operating on the truth cache:
```bash
source nous/.venv/bin/activate && python .nous/queue-throughput/runs/iter-2/inputs/analyze_diff_ratios.py \
    > .nous/queue-throughput/runs/iter-2/results/arm_robustness_diff_ratios.json
```

## Success Criteria

1. **h-main:** For all scenarios with a crossover (baseline, long-loose-itl, small-queue), the ratio binary search returns M_chosen where gap_throughput_rel = 0.0, using ≤ ceil(log2(255)) + 1 = 9 calls (8 search + 1 confirmatory).
2. **h-ablation:** ITL-only shape peaks at M < 30 for baseline; TTFT-only is monotone with no peak in [2, 256].
3. **h-control-negative:** For short-tight-ttft, the strategy detects no-crossover and returns M with gap_throughput_rel < 0.001 using ≤ 15 calls.
4. **h-robustness:** The first-difference ratio at M* is < 0.55 for all crossover scenarios, while the normal concavity ratio stays in [0.96, 0.99].

## Constraints

- Strategies must use the harness contract: `search(target_eval, m_min, m_max) -> int`
- M range is [1, 256]; M=1 is always infeasible (free to probe)
- Infeasible calls (400) do not count toward call budget
- The harness adds +1 confirmatory call after strategy returns
- No changes to Go analyzer code — only `nous/harness/*` and `nous/strategies/*`

## Prior Knowledge

- **RP-1:** f(M) is two-phase: concave rise then flat plateau (confirmed iter-1)
- **RP-2:** M* = crossover point where RPSTargetTTFT first exceeds RPSTargetITL (confirmed iter-1)
- **RP-3:** Rising portion has brief convex onset then sustained concavity (confirmed iter-1)
- **RP-4:** M=1 always infeasible (confirmed iter-1)
- **RP-5:** Problem is plateau-onset detection, not peak-finding (confirmed iter-1)
