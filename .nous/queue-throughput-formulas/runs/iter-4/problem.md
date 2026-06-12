# Iter-4 Problem Framing — Concurrency-Optimal Formula-Guided Onset Search

## Research Question

Given the analytic primitives `itl(B)`, `ttft_prefill(B)`, `tau(B)` (`nous/harness/formulas.py:99,93,82`),
design a **formula-guided search that pinpoints the plateau-onset `M*`** — the *smallest*
batch size whose throughput is within `epsilon=0.02` of peak — using few `/target` calls.

This is the brief's **iter-4 stage** (`nous/description.txt:181-189`): the first
code-changes stage. It implements `formula_guided.py`, `naive_ternary.py`, `naive_max.py`
under `nous/harness/strategies/` and validates them **on the 6-scenario dev set**
(`nous/scenarios.json`), gating on `(calls, gap_M)` subject to `gap_f <= epsilon`.

**The headline metric is `gap_M = |M_chosen - M_truth|` (concurrency distance), NOT
`gap_throughput_rel`.** The brief (`nous/description.txt:133-148`) is explicit: f(M) is
monotone-rising then flat, so *any* `M >= M*` — including the trivial constant `M_max=256` —
achieves peak throughput within ~3% in one call. Therefore `gap_f` cannot reward a precise
predictor; the deployed value of `M̂` is **concurrency**: the smallest M that reaches
near-peak throughput. Over-provisioning to `M_max` wastes KV-cache/batch slots for zero
throughput gain. `gap_f <= epsilon` is a *feasibility constraint to stay under*, not the
thing to win.

## System Interface

- **Build:** none. The harness spawns the Go analyzer with `go run main.go` and waits for
  `:8080` (`nous/harness/server.py`); `go1.26.4` is on PATH. Activate the venv first:
  `source nous/.venv/bin/activate`.
- **Strategy contract** (`nous/harness/run.py:36-48`): each strategy file defines
  `search(target_eval, params, m_min, m_max) -> int`. `params` carries
  `{alpha,beta,gamma,AvgInputTokens,AvgOutputTokens,targetITL,targetTTFT,maxQueueSize}` —
  exactly the keys `formulas.py` consumes (`scenarios.py:scenario_to_params`).
- **Oracle** (`nous/harness/oracle.py:24-36`): `target_eval(M)` POSTs to `/target`; HTTP 400
  (infeasible) → `{"throughput":0.0}` and is **NOT counted**; only feasible (`throughput>0`)
  calls increment `stats.calls`.
- **+1 confirmatory call** (`nous/harness/run.py:78`): the harness always evaluates the
  chosen M once after `search` returns, so `calls = strategy_calls + 1` (unless that eval
  is a 400). Code evidence: `run.py:78` `final = eval_(m_chosen)`.
- **Scoring** (`nous/harness/scoring.py:33-46`): `gap_throughput_rel = max(0,(truth-chosen)/truth)`
  (0 when `truth<=0`); `gap_M = abs(m_chosen - m_truth)`.
- **Output flag (native):** `--out <path>.json` writes one JSON record per scenario with
  keys `M_chosen, calls, throughput_chosen, M_truth, throughput_truth, gap_throughput_rel,
  gap_M, wall_clock_seconds, internal_solve_calls` (`run.py:120`, `scoring.py:13-24`). Never
  use shell redirects.
- **Dev truth caches:** `nous/cache/truth-<name>.json` (default `--cache-dir nous/cache`,
  `run.py:42`). Verified the dev set needs **no symlink** (files already carry the `truth-`
  prefix). M_truth in the cache **is the onset M\***, confirmed below.

## Baseline Command

```bash
source nous/.venv/bin/activate
python -m nous.harness.run \
  --scenarios nous/scenarios.json \
  --strategy nous/harness/strategies/naive_max.py \
  --m-min 1 --m-max 256 \
  --out .nous/queue-throughput-formulas/runs/iter-4/results/naive_max.json
```

## Baseline Validation

Ran the above (with the strategy file staged in `iter-4/inputs/naive_max.py`). **Exit 0**,
wrote 6 records to the `--out` path. Example metrics (the concurrency story in one table):

| scenario | M_chosen | calls | gap_f | **gap_M** | M_truth (=M*) |
|---|---|---|---|---|---|
| baseline | 256 | 1 | 0.0001 | **187** | 69 |
| itl-only | 256 | 1 | 0.0027 | **239** | 17 |
| ttft-only | 256 | 1 | 0.0000 | **164** | 92 |
| unbounded | 256 | 1 | 0.0000 | **0** | 256 |
| alpha-low | 256 | 1 | 0.0001 | **86** | 170 |
| alpha-high | 256 | 1 | 0.0001 | **239** | 17 |

This is the crux: `naive_max` is throughput-perfect (`gap_f <= 0.0027`) in 1 call but
concurrency-terrible (worst `gap_M = 239`). gap_f genuinely cannot discriminate.

**Onset verification** (computed `M* = smallest M with f(M) >= 0.98*peak` from the dev
f_curves vs cached `M_truth`): alpha-high 16 vs 17, alpha-low 154 vs 170, baseline 66 vs 69,
itl-only 17 vs 17, ttft-only 56-vs-92, unbounded 238 vs 256. `M_truth` tracks the onset
(small offsets from the truth's epsilon convention), confirming `gap_M` rewards locating
the onset, not the argmax.

## Experimental Conditions

All conditions run on the dev set with the command template above (only `--strategy`/`--out`
change). The three strategy files go in `nous/harness/strategies/` (per brief
`description.txt:158`); the executor implements them and verifies they import `formulas.py`.

1. **formula_guided** (h-main, NEW code). Mechanism: probe a **high seed** for `f*`
   (cell-aware — see below), then **binary-search DOWNWARD** for the smallest M with
   `f(M) >= (1 - epsilon/2)*f*` (a monotone predicate, true for `M >= M*`), bracketed below
   by the closed-form `M_ITL` (RP-1/RP-2) and above by the constraint upper endpoint U /
   an occupancy-gap bound (`~3*M_ITL`, RP-2). Returns the onset estimate. The `epsilon/2`
   safety margin keeps the confirmatory `gap_f` strictly under `epsilon`.
   *Implementation risk (flag for executor):* a naive full-range binary search
   (`[M_ITL, M_max]`) costs `log2(256)+seed+confirm ≈ 10-13` calls on wide-bracket
   scenarios (large `M_ITL`, `U=M_max`: itl-only, alpha-low) — **over the ≤8 gate**. The
   executor must tighten the upper bracket analytically (occupancy-gap bound) or
   interpolate so worst-case calls `<= 8`. The gap_M dominance holds regardless of this
   tuning; the call budget is the engineering target.

2. **naive_max** (h-control-negative, NEW code = existing constant). Returns `m_max`. The
   regime where the concurrency objective is abandoned.

3. **naive_ternary** (h-ablation, NEW code). Parameter-blind ternary search over
   `[m_min, m_max]` maximizing throughput. Ablates the formula guidance (keeps generic
   search). Accepts-and-ignores `params`.

4. **formula_guided on ttft-only** (h-robustness). Same `formula_guided.py`; the analysis
   focuses on the TTFT-binding `ttft-only` record where the constraint upper endpoint
   `U = M_TPF = 70 < M* = 92` (RP-5). Tests that **cell-aware high seeding** (the
   `M_TPF < M_ITL` ttft-only signature, RP-7, triggers an `M_max` `f*` probe) prevents the
   onset search from inheriting U's undershoot.

## Success Criteria (brief iter-4 gate, `description.txt:185-189`)

- **Feasibility:** `formula_guided` worst-case `gap_f <= epsilon = 0.02` on the dev set.
- **Concurrency (headline):** `formula_guided` worst-case `gap_M` **strictly beats BOTH**
  `naive_max` (worst gap_M = 239) **and** `naive_ternary` (worst gap_M ≈ 127, from sim).
  Offline sim of the mechanism gives `formula_guided` worst `gap_M ≈ 22` (ttft-only),
  `<= 9` on the other five — a strict, large win on both axes.
- **Calls:** worst-case `calls <= 8` (engineering target; see implementation risk above).
  `naive_ternary` is expected ~25-30 calls, so the calls-axis win is structural.
- Directional, multi-seed-tested claims; no invented thresholds beyond the brief's
  `epsilon=0.02` and `calls<=8`.

## Constraints

- Out of scope: any change to the Go analyzer or `/solve`,`/target` (`description.txt:198`).
  Only `nous/harness/*` and `nous/harness/strategies/*`.
- A confirmatory `+1` call is unavoidable (`run.py:78`); budget for it.
- Do not import `strategies/_common.py` / `predictor_*.py` — they hardcode stale
  `ALPHA,BETA,GAMMA` (`_common.py:30`) that do not match the per-scenario constants.
- `f(M=1)=0` everywhere (infeasible); never seed or terminate the search at the bottom.

## Prior Knowledge (active principles applied)

- **RP-1 / RP-2:** `M_ITL` is the closed-form lower bound on the onset `M*` (occupancy gap
  `M_truth/M_ITL` ∈ [1.59, 2.83] on ITL-binding dev scenarios). Used as the downward-search
  lower bracket and the basis for the `~3*M_ITL` upper bound.
- **RP-3:** under nc=1, f(M) rises to a flat plateau and never declines in [1,256] — the
  monotone predicate `f(M) >= (1-eps)f*` is well-defined for the downward search.
- **RP-5:** `M_TPF` upper-bounds the TTFT-*constraint* crossing, not the throughput argmax;
  for ttft-only `U = M_TPF = 70 < M* = 92`, so `f*` must be probed HIGH (at `M_max`), not at
  U — the h-robustness concern.
- **RP-6 / RP-7:** the primitive cells; `M_TPF < M_ITL` is the load-bearing ttft-only
  signature that triggers cell-aware high seeding.
