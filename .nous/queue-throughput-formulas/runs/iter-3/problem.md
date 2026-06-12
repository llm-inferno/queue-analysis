# Iter-3 Problem Framing — Oracle-Validated Endpoint Predictor

## Research Question

Given the iter-2 regime partition and its per-cell bracket `[M_ITL, min(M_TPF, 256)]`,
**which point in the bracket should a formula-guided strategy seed at to minimize
`gap_throughput_rel` with the fewest `/target` calls?** Iter-2 designated the LOWER
endpoint `M_ITL` as the per-cell point estimate (`m_hat`). Iter-3 is the first iteration
permitted to call the oracle (`/target`) and read truth caches — so we validate that
choice against ground truth on the six dev scenarios, and fit any occupancy-gap correction
the data demands.

The analytic primitives are in `nous/harness/formulas.py` (`itl`, `ttft_prefill`, `tau`,
`delta`, `num_iterations_per_prefill`), a parity-checked port of
`pkg/analyzer/queueanalyzer.go:275-327` and `pkg/analyzer/utils.go:8-47`. The oracle
`f(M)` is the `throughput` field returned by `POST /target` (the max RPS meeting both
`AvgITL <= targetITL` and `AvgTTFT <= targetTTFT` under queue capacity `Q`), composed
through the state-dependent M/M/1 solver in `pkg/queue/mm1modelstatedependent.go`.

## System Interface

- **Build:** none precompiled. The harness spawns `go run main.go` in the repo root and
  waits for `:8080` (`nous/harness/server.py:38-52`). `go version go1.26.4` is on PATH.
- **Run a strategy across all scenarios:** `python -m nous.harness.run` loads a strategy
  file (any path) exposing `search(target_eval, params, m_min, m_max) -> int`, spawns the
  Go server once, runs the strategy per scenario, then makes **one extra confirmatory
  `eval_(m_chosen)` call** that IS counted in `calls` (`nous/harness/run.py:78-86`).
- **Oracle contract:** `target_eval(m)` POSTs `scenario_to_problem(scenario, m)` to
  `/target`; HTTP 400 → `{"throughput": 0.0}` and is **NOT counted** against the budget
  (`nous/harness/oracle.py:30-38`). The strategy receives per-scenario constants via
  `params` (alpha/beta/gamma/AvgInputTokens/AvgOutputTokens/targetITL/targetTTFT/
  maxQueueSize) — `nous/harness/scenarios.py:scenario_to_params`. **This means a strategy
  can compute the predictor live; it does NOT need to read `scenarios.json` out-of-band**
  (the legacy `strategies/_common.py` hardcodes stale pre-fix constants — do not use it).
- **Scoring:** `gap_throughput_rel = max(0, (f_truth - f_chosen)/f_truth)` (negatives
  clamped to 0 — any M on the plateau scores 0) and `gap_M = |M_chosen - M_truth|`
  (`nous/harness/scoring.py:compute_gap`). The Pareto axes are `(calls, gap_throughput_rel)`.
- **Output flag:** `--out <path>` writes a JSON list of per-scenario records. No shell
  redirects.

**Code evidence**
- `nous/harness/run.py:78-86` — the +1 confirmatory call overhead, counted.
- `nous/harness/oracle.py:30-38` — 400→0.0 uncounted; per-scenario alpha/beta/gamma.
- `nous/harness/scenarios.py:scenario_to_params` — params keys passed to `search`.
- `nous/harness/formulas.py:99-102` (`itl`), `:93-96` (`ttft_prefill`), `:72-76` (`delta`).
- `nous/harness/scoring.py:compute_gap` — clamp-to-zero gap definition.

## Baseline Command

```bash
source nous/.venv/bin/activate
python -m nous.harness.run \
    --scenarios nous/scenarios.json \
    --strategy .nous/queue-throughput-formulas/runs/iter-3/inputs/seed_upper.py \
    --m-min 1 --m-max 256 \
    --out .nous/queue-throughput-formulas/runs/iter-3/results/seed_upper.json
```

## Baseline Validation

Ran the exact command above (live Go server, live `/target`). Exit 0; wrote 6 records to
`results/smoke_seed_upper.json`. Observed per-scenario `(M_chosen, calls, gap_rel)`:

| scenario   | M_chosen | calls | gap_throughput_rel |
|------------|----------|-------|--------------------|
| baseline   | 147      | 1     | 0.0001 |
| itl-only   | 256      | 1     | 0.0027 |
| ttft-only  | 70       | 1     | 0.0009 |
| unbounded  | 256      | 1     | 0.0000 |
| alpha-low  | 256      | 1     | 0.0001 |
| alpha-high | 45       | 1     | 0.0001 |

`seed_upper` achieves `gap_rel <= 0.0027` everywhere with exactly **1 oracle call**.

## Experimental Conditions

All conditions are strategy files already written to `runs/iter-3/inputs/`; the executor
runs each via `python -m nous.harness.run --strategy <path> --out results/<name>.json`.
Each starts from a clean worktree (no target-repo edits; no code_changes).

1. **seed_upper** (h-main) — `inputs/seed_upper.py`. Seeds at the bracket UPPER endpoint:
   `unbounded→256`, `ttft-only→M_TPF`, `itl-or-crossover→min(M_TPF, 256)`. 1 call.
2. **seed_lower** (h-ablation) — `inputs/seed_lower.py`. Identical skeleton, seeds at the
   bracket LOWER endpoint `M_ITL` — the iter-2 point estimate `m_hat`. 1 call.
3. **naive_max** (h-control-negative) — `inputs/naive_max.py`. Returns `M_MAX=256`
   unconditionally; no formula, no search. 1 call.
4. **example_linear_scan** (reference) — `nous/harness/strategies/example_linear_scan.py`.
   Brute scan, 256 calls, `gap=0`. The call-pessimal / gap-optimal corner.

## Success Criteria

Directional (multi-seed significance handled by the bundle; we test direction + mechanism):

- **h-main:** `gap_rel(seed_upper) <= gap_rel(seed_lower)` for every scenario, with the
  difference largest where the occupancy ratio `M_truth/M_ITL` is largest, and
  `gap_rel(seed_upper)` near zero (plateau) on all six.
- **h-ablation:** `seed_lower` shows materially larger `gap_rel` than `seed_upper` on the
  ITL-binding scenarios (baseline, itl-only, alpha-low, alpha-high), confirming the upper
  endpoint is the necessary component.
- **h-control-negative:** `|gap_rel(seed_upper) - gap_rel(naive_max)|` is within float
  noise on all six — the throughput axis cannot distinguish the formula seed from constant
  `M_MAX` under nc=1.
- **h-robustness:** For `ttft-only`, `M_truth=92 > U=70` (bracket fails to contain
  `M_truth`) yet `gap_rel(seed_upper) ~ 0` — throughput-optimality is robust to the bracket
  missing the argmax.

## Constraints

- `M ∈ [1, 256]`; SLOs `AvgITL <= targetITL`, `AvgTTFT <= targetTTFT`; queue capacity `Q`
  per scenario.
- No edits to the target Go repo or to `nous/harness/`; strategies are standalone input
  files. Worktree isolation between conditions.
- Respect active principles RP-1..RP-7. In particular `M_ITL` is a LOWER bound (RP-2) and
  `M_TPF` an UPPER bound (RP-5) — the data tests whether those directions hold for the
  THROUGHPUT argmax (not just the constraint crossings).

## Prior Knowledge

- **Iter-1 (RP-1..RP-5):** closed-form `M_ITL` under nc=1; `M_ITL` lower bound, `M_TPF`
  upper bound on the respective binding M; saturation `S(B)` concave-increasing to `S_inf`.
- **Iter-2 (RP-6, RP-7):** three primitive-decidable cells; the `M_TPF < M_ITL` ordering
  decides `ttft-only`; the `itl-only`↔`crossover` split needs the queue wait. Iter-2
  designated `M_ITL` (lower endpoint) as the per-cell point estimate — **this iteration
  tests that designation against the oracle.**
- **Verified for this iteration:** all six dev scenarios have `nc=1` across `[1,256]`
  (probed via `num_iterations_per_prefill`), so `delta` is constant and the f-plateau is
  expected to extend to `M_MAX` — the mechanism behind h-control-negative.
