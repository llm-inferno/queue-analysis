# Iter-2 Problem Framing — Regime Partition of `argmax_M f(M)`

## Research Question

For fixed inputs `(alpha, beta, gamma, AvgInputTokens=n, AvgOutputTokens=m, maxQueueSize=Q,
targetITL, targetTTFT)`, `f(M)` is the max RPS returned by `/target` at `maxBatchSize=M`,
and `M* = argmax_{M in [1,256]} f(M)`. Iter-1 derived the closed-form latency crossings
`M_ITL` and `M_TTFT_prefill` from the analytic primitives in
`nous/harness/formulas.py` (`itl(B)`:99-102, `ttft_prefill(B)`:93-96, `tau(B)`:83-86,
`delta(B)`:72-76) and established their bound directions (RP-2: `M_ITL` is a LOWER bound
on the ITL-binding `M*`; RP-5: `M_TTFT_prefill` is an UPPER bound on the TTFT-binding
`M*`).

**Iter-2 question (stage plan):** *where in params-space does each constraint bind?
Partition params-space into ≤5 regime cells with boundary equations, give each cell a
per-cell M-hat, and answer directly: "are 4 groups enough?"* This is a pure-analysis
(observe) iteration on the symbolic forms — **NO `/target` (oracle) calls, NO truth-cache
reads, NO code changes.**

## System Interface

- **Build:** none. `nous/harness/formulas.py` is pure-`math` Python; `import
  nous.harness.formulas` resolves from the repo root (`nous/__init__.py` present). No Go
  build, no server.
- **Primitive entry points** (params dict = scenario keys):
  - `num_iterations_per_prefill(B, params)` — `nc(B)` step function vs `MaxNumTokens=8192`
    (`formulas.py:44-56`).
  - `itl(B, params)` — `formulas.py:99-102`; `ttft_prefill(B, params)` — `:93-96`;
    `tau(B, params)` — `:83-86`; `delta(B, params)` — `:72-76`.
- **Output:** the iter-2 validator writes structured JSON via `--out` (native; no shell
  redirect). Keys: `per_scenario` (cell, M_ITL, M_TPF, m_hat, bracket, primitive
  signature, label), `boundary_itl_unbounded`, `boundary_ttftonly`,
  `perturbation_baseline_ttft`, `naive_2x2_mismatches`,
  `indistinguishable_label_sets`, and `gates` (eight arm booleans).

## Baseline Command

```bash
python3 .nous/queue-throughput-formulas/runs/iter-2/inputs/validate_regimes.py \
    --scenarios nous/scenarios.json \
    --out .nous/queue-throughput-formulas/runs/iter-2/results/baseline.json
```

Run from the repo root `/Users/tantawi/Projects/llm-inferno/queue-analysis` (the script
also self-locates the repo root onto `sys.path`, so any cwd works).

## Baseline Validation

Ran the exact command above. **Exit 0.** Wrote
`.nous/queue-throughput-formulas/runs/iter-2/results/baseline.json`. All eight gates
returned `true`. Example per-scenario classification observed:

| scenario | label | M_ITL | M_TPF | cell (primitive) | M-hat | bracket | signature |
|---|---|---|---|---|---|---|---|
| baseline | crossover | 40 | 147 | itl-or-crossover | 40 | [40,147] | (1,1,+) |
| itl-only | itl-only | 8 | 256 | itl-or-crossover | 8 | [8,256] | (1,0,+) |
| ttft-only | ttft-only | 95 | **70** | **ttft-only** | 70 | [1,70] | (1,1,**−**) |
| unbounded | unbounded | 256 | 256 | **unbounded** | 256 | [256,256] | (0,0,0) |
| alpha-low | crossover | 107 | 256 | itl-or-crossover | 107 | [107,256] | (1,0,+) |
| alpha-high | crossover | 6 | 45 | itl-or-crossover | 6 | [6,45] | (1,1,+) |

Key observed facts: `ttft-only` is the **only** scenario with `M_TPF < M_ITL`;
`itl-only` and `alpha-low` (crossover) share the **identical** primitive signature
`(1,0,+)` yet carry **different** labels.

## The Partition (≤5 cells, primitive-decidable)

With `itl_binds = itl(256) > targetITL`, `ttft_pf_binds = ttft_prefill(256) > targetTTFT`,
`M_ITL` = largest `B` with `itl(B) ≤ targetITL`, `M_TPF` = largest `B` with
`ttft_prefill(B) ≤ targetTTFT`:

1. **`unbounded`** — `¬itl_binds ∧ ¬ttft_pf_binds` → no latency constraint reaches its
   target in `[1,256]` → **M-hat = 256**. (Caveat: assumes the queue capacity `Q` does
   not bind; the queue wait is invisible to primitives — verified in iter-3.)
2. **`ttft-only`** — `M_TPF < M_ITL` → TTFT strictly binds before ITL (PROVABLE, see
   mechanism) → **M-hat = M_TPF** (an upper bound; the queue wait pulls true `M*` down,
   corrected in iter-3).
3. **`itl-or-crossover`** (FUSED) — `M_ITL ≤ M_TPF` and at least one binds → the
   primitives **cannot** decide whether the realized regime is `itl-only` or `crossover`
   → **M-hat ∈ bracket [M_ITL, min(M_TPF,256)]**, point estimate `M_ITL` (lower bound).
   Splitting this cell requires the M/M/1 **queue-wait** term (oracle, iter-3).

**Answer to "are 4 groups enough?"** — No. The four *named* regimes exist, but the
analytic primitives separate only **three** cells cleanly; the `itl-only` ↔ `crossover`
split collapses into one indistinguishable cell because the queue wait (not in any
primitive) is what makes TTFT bind in `alpha-low` but not in `itl-only`.

## Boundary Equations (closed-form in params, nc=1)

- **Unbounded ↔ ITL-bound:** `targetITL* = itl(1) + (M_MAX−1)·delta(1) = itl(256)`
  (matches to <1e-6 on all 6 — `nc=1` makes `itl` affine). ITL binds iff
  `targetITL < itl(256)`.
- **ttft-only on/off:** `M_TPF < M_ITL  ⟺  targetTTFT < ttft_prefill(M_ITL)`. Verified
  as an exact iff on all 6 scenarios. The `baseline` scenario flips into `ttft-only`
  exactly when `targetTTFT` is lowered below `ttft_prefill(M_ITL=40) = 28.114`
  (perturbation confirmed).

## Experimental Conditions

Single deterministic command (above) computing all gates. The arms are falsifiable
assertions on its JSON output — no flag/config variation, no oracle, no code changes
(observe iteration). Conditions are encoded as gate booleans:

- **h-main:** unbounded cell is exact; ttft-only cell is exactly `{M_TPF < M_ITL}`; the
  fused cell carries only `itl-only`/`crossover` labels.
- **h-control-negative:** ≥1 pair of differently-labelled scenarios shares a primitive
  signature (fused cell irreducible without the queue wait).
- **h-robustness:** both boundary equations are closed-form/exact, and a perturbation
  flips cell membership at the predicted threshold.
- **h-ablation:** dropping the `M_TPF < M_ITL` ordering (naive 2×2 on binding booleans
  only) misclassifies `ttft-only` as `crossover`.

## Success Criteria

- `h_main_unbounded_exact`, `h_main_ttftonly_iff_order`,
  `h_main_fused_only_itl_crossover` all `true`.
- `h_control_fused_indistinguishable` `true` with a non-empty
  `indistinguishable_label_sets`.
- `h_robustness_itl_boundary_exact` (`abs_err < 1e-6` all 6), `h_robustness_ttftonly_iff`
  (iff holds all 6), `h_robustness_perturbation_flips` all `true`.
- `h_ablation_ttftonly_lost_without_order` `true`.

## Constraints

- Observe stage: NO `/target` calls, NO truth-cache reads, NO code changes to the target
  repo or `nous/harness/strategies/`. (Oracle reserved for iter-3.)
- Must not violate active principles RP-1…RP-5. The partition is built **on** them:
  RP-1/RP-4 (nc=1 affine exactness underpins the closed-form boundaries), RP-2 (`M_ITL`
  lower bound), RP-5 (`M_TPF` upper bound) — the bound directions are what make the
  `ttft-only` rule provable and the fused cell irreducible.
- `M_MIN=1`, `M_MAX=256` fixed.

## Prior Knowledge

Builds directly on iter-1 (CONFIRMED): `nc=1` everywhere on the dev set makes `itl`,
`ttft_prefill` affine (slope `delta`); the `M_ITL` closed form is exact vs brute scan;
saturation `S(B)` is monotone/concave so throughput is non-decreasing in `M` (latency,
not saturation, sets the useful upper bound on `M`). Iter-1 "Suggested next" asked
exactly for this regime partition with boundary equations and per-cell M-hat. RP-2 and
RP-5 (the bound directions) are the load-bearing inputs to the partition logic.
