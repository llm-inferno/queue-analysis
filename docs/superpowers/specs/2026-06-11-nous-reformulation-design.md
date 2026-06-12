# NOUS Reformulation — Formula-Guided Search Campaign

**Status:** design — pending implementation plan
**Date:** 2026-06-11
**Target system:** `/Users/tantawi/Projects/llm-inferno/queue-analysis`
**NOUS install:** `~/Projects/nous/agentic-strategy-evolution`
**Supersedes (operationally):** `2026-06-09-nous-throughput-campaign-design.md`

## 1. Why a new campaign

Commit `99024df` ("analyzer: new analysis with limited-token (chunked-prefill) case") corrected a double-count of focal request work in the service-time formula:

```
old: τ(B) = (nc+m) · (α + (B+1)·δ)   ← counts focal work twice
new: τ(B) = (nc+m) · (α + B·δ)
```

The prior NOUS campaign (`2026-06-09-...`, run_id `queue-throughput`, merged via PR #5) was conducted against the buggy formula. Its quantitative findings (`baseline: M*=40, f*=2.17`, etc.) are arithmetically wrong against the corrected analyzer; its qualitative findings (unimodality, plateau-at-peak) survive but were tuned to the old f-curve. The paper draft on branch `paper-analysis-section` was paused at Task 2 specifically because of this discrepancy.

This reformulation rebuilds the campaign on the corrected analyzer and, simultaneously, exploits insights we did not have during the original run — most importantly that the analytic primitives (ITL, TTFT, τ) can be handed to NOUS as derivation inputs rather than discovered empirically.

The three insights driving the redesign:

1. **Is K=4 enough to partition the load space?** The original campaign fixed 4 ad-hoc scenarios and never tested whether 4 is the right partition cardinality. The new design exposes regime structure as a first-class iter-2 deliverable.
2. **(α, β, γ) belong in the reasoning, not just as numbers.** The original held them at `(12, 0.05, 0.0005)`. The new sweeps them on the realistic ratio manifold (β ≈ α/240, γ ≈ α/24000, perturbed) so derivations and algorithms must be parameter-generic.
3. **The closed-form ITL/TTFT/τ primitives unlock analytical reasoning.** With the formulas, NOUS can differentiate, take limits, and identify regime boundaries instead of curve-fitting to oracle calls. This shifts iter 1 from "shape characterization" to "derive M̂(params)."

## 2. Goal

Two deliverables, in order:

1. **A predictor M̂(params) derived analytically** from the ITL/TTFT/τ primitives, validated against `/target` on a curated dev scenario set. Closed form where each constraint binds in isolation; piecewise on the regime partition where multiple constraints interact.
2. **A formula-guided search algorithm** that uses M̂ as a tight bracket center and refines via a small number of `/target` calls. Pareto-compared against a parameter-blind baseline (`naive_ternary`) on a benchmark grid.

Both deliverables emerge from NOUS's per-iteration `bundle.yaml` / `findings.json` artifacts and the algorithm strategies committed under `nous/harness/strategies/`.

## 3. Optimization problem

Unchanged from the prior campaign:

```
M* = argmax_{M ∈ [M_min, M_max]} f(M)
where f(M) = throughput returned by /target for the ProblemData at MaxBatchSize=M
```

Fixed bounds: `M_min = 1`, `M_max = 256`.

What changes is the campaign's framing of *how* M̂ is found: derive analytically from primitives, then refine.

### 3.1 Analytic primitives (handed to NOUS)

```
prefill(B) = nc · (α + (B−1)·δ) + w_prefill
itl(B)     = (α + (B−1)·δ) + β + γ·(n + (m+1)/2)
τ(B)       = (nc + m) · (α + B·δ)

where:
  B    = batch size (= maxBatchSize variable, M)
  nc   = number of chunked-prefill iterations = NumIterationsPerPrefill(B, n)
  n    = AvgInputTokens
  m    = AvgOutputTokens
  α, β = model/runtime constants (ms)
  γ    = per-token decode coefficient (ms/token)
  δ    = per-token batch coefficient (ms/token); extracted from analyzer code into formulas.py
  w_prefill = prefill warmup constant (ms)
```

The `/target` endpoint composes these primitives through a state-dependent M/M/1 queue solver to produce f(M) = max RPS satisfying ITL ≤ T_ITL and TTFT ≤ T_TTFT under queue capacity Q.

## 4. Parameter ranges and scenarios

### 4.1 Parameter ranges (sweep manifold)

β and γ are coupled to α via canonical ratios with bounded perturbation:

| Param | Range | Notes |
|---|---|---|
| α | {4, 8, 16} | factor-of-2 around 8 |
| β/α | {1/400, 1/240, 1/120} | canonical ≈ 1/240 |
| γ/α | {1/40000, 1/24000, 1/12000} | canonical ≈ 1/24000 |
| L_in (AvgInputTokens) | {64, 256, 1024, 4096} | |
| L_out (AvgOutputTokens) | {64, 256, 1024, 4096} | |
| T_ITL | {15, 20, 30, 40, 60} ms | |
| T_TTFT | {30, 60, 120, 200, 400} ms | |
| Q (maxQueueSize) | {4, 32, 128} | |
| M range | [1, 256] | unchanged |

### 4.2 Dev scenarios (6, regime-spanning)

Probed against `/target` during design. Each chosen to exercise one regime cleanly. Regime label captures which constraint binds at the peak; α-perturbed scenarios fall in `crossover` regime but exist to probe parameter sensitivity of M*.

| name | regime | (α, β, γ, L_in, L_out, T_ITL, T_TTFT, Q) | M* (probe) | f* (probe) |
|---|---|---|---|---|---|
| baseline | crossover (TTFT→ITL; peak at transition) | (8, .033, .000333, 256, 1024, 20, 60, 128) | 80 | 1.92 |
| itl-only | pure ITL plateau | (8, .033, .000333, 256, 4096, 15, 400, 128) | 40 | 0.13 |
| ttft-only | pure TTFT plateau | (8, .033, .000333, 1024, 256, 60, 80, 128) | ~80 | 4.49 |
| unbounded | no constraint binds in [1,256] → M* = M_max | (4, .017, .000167, 64, 128, 200, 2000, 4) | 256 | 122 |
| alpha-low | crossover; low-α perturbation | (4, .017, .000167, 256, 1024, 20, 60, 128) | 200 | 5.19 |
| alpha-high | crossover; high-α perturbation | (16, .067, .000667, 256, 1024, 20, 60, 128) | 40 | 0.28 |

Two structural notes from the design probes:

- **`baseline` is intrinsically balanced.** At small M, TTFT pegs at 60.0 (binding); at M≥80, the curve flips to ITL=20.0 binding and TTFT drops to ~48.6 (loose). The peak M*=80 is the TTFT→ITL crossover. A separate "balanced" scenario would be redundant.
- **Pure queue-binding regime barely exists in our ranges.** Even at Q=2 with very loose targets, queue costs only ~2% throughput; f(M) rises monotonically through M=256 (no peak within range). The `unbounded` scenario captures this corner: the algorithm should detect "M* = M_max" cheaply rather than search for an interior peak.

### 4.3 Benchmark grid (~30 LHS samples)

Generated by a script — not enumerated in this spec — so reproducibility is a function of (ranges, sampler, seed) rather than a hand-typed list.

- Sampler: Latin hypercube over the parameter ranges in §4.1, with β = α · (β/α-sample) and γ = α · (γ/α-sample) so the realistic-ratio manifold is preserved.
- Seed: `42`.
- N_samples: `30` (default; tunable).
- Output: `nous/scenarios_benchmark.json`. One scenario per record, with index `bench-XXX`.
- Truth caches built once after generation.

## 5. Stage plan

Five iterations. `observe` mode = NOUS reasons + reports, no code changes. `code_changes` = NOUS adds files under `nous/harness/strategies/`.

| # | Mode | Goal | Inputs | Outputs |
|---|---|---|---|---|
| 1 | observe | Derive M̂(params) closed-form from ITL/TTFT/τ primitives. Solve each binding constraint in isolation. | Formulas, scenario schema. No oracle calls. | Symbolic expressions for M_ITL, M_TTFT, M_queue and a rule for combining them. Explicit assumptions (e.g., n ≈ L_in, steady state). |
| 2 | observe | Map regime structure: where in (params) space does each constraint bind? Directly tests "are 4 groups enough?" | Iter 1 output. Pure analysis on symbolic boundaries. | Regime partition (could be 2, 3, 4, or more cells). Per-cell expression for M̂. Boundary equations. |
| 3 | observe | Validate predictor against `/target` on the dev set. Quantify error. | M̂ from iter 2, dev scenarios. Oracle calls allowed (validation, not algorithm budget). | Per-scenario error table. Loose regimes flagged. Decision: predictor sufficient alone, or needs search refinement. |
| 4 | code_changes | Implement formula-guided search: M̂ → bracket → small `/target` refinement. Add baseline `naive_ternary.py`. | M̂ + new harness contract. | `formula_guided.py` and `naive_ternary.py`. Predicted worst-case calls and gap on dev set, justified from iter 3. |
| 5 | code_changes | Run on benchmark grid. Pareto-compare against baseline and prior strategies. Per-regime breakdown. | Strategies + benchmark grid. | Final Pareto plot. Per-regime table. Honest comparison report. |

**Iter 3 oracle calls are not counted against any algorithm budget.** They are part of NOUS's reasoning loop, not the deployed algorithm.

**Each iteration's gate**: NOUS must produce the listed outputs before moving on. If iter 1 cannot derive a closed form for, say, the queue constraint, that becomes an explicit assumption for iter 2 to test rather than a quiet skip.

## 6. Harness contract changes

### 6.1 Strategy interface

Wider signature so strategies can compute M̂:

```python
def search(target_eval, params: dict, m_min: int, m_max: int) -> int
```

Where `params = {alpha, beta, gamma, AvgInputTokens, AvgOutputTokens, targetITL, targetTTFT, maxQueueSize}` — the scenario JSON minus the name.

Backwards compatibility: prior strategies (`predictor_*.py`, `adaptive_*.py`, `ratio_binary_search.py`, `example_linear_scan.py`) are retrofitted to accept-and-ignore `params`. Kept callable as a baseline cohort for iter 5 comparison.

### 6.2 New module: `nous/harness/formulas.py`

Exposes the analytic primitives as functions so strategies can reuse them rather than re-deriving:

```python
def num_iterations_per_prefill(B, L_in): ...     # nc per analyzer logic
def itl(B, params): ...                          # per primitive
def ttft(B, params): ...                         # composite from prefill + queue wait
def tau(B, params): ...                          # per primitive
```

`δ` is extracted from `pkg/analyzer/queueanalyzer.go` and documented; `formulas.py` is the source of truth for what NOUS sees as the formulas.

### 6.3 New module: `nous/harness/scenarios_benchmark.py`

Generates `nous/scenarios_benchmark.json` from the parameter ranges in §4.1 with seed=42, N=30. Generated once and committed.

### 6.4 Truth-cache regeneration

Existing `nous/harness/baseline_truth.py` runs after dev + benchmark scenarios are committed. Cache layout:

- `nous/cache/truth-<name>.json` — dev scenarios, named.
- `nous/cache/bench/<idx>.json` — benchmark grid, indexed.

Old caches deleted as part of the cutover.

### 6.5 Score collection extension

Each scenario JSON gets a `regime` field:

```
"itl-only" | "ttft-only" | "crossover" | "unbounded" | "bench"
```

`bench` is the regime label for benchmark-grid scenarios where the binding constraint is determined post-hoc by NOUS in iter 5. So iter 5 can produce a per-regime breakdown without manual labeling.

### 6.6 Out of scope

- No changes to `pkg/analyzer/`, the Go server, or `/solve` / `/target` endpoints.
- No online or streaming variants of the algorithm.
- Iter 4 strategies stay as single Python files under `nous/harness/strategies/`.

## 7. NOUS-facing brief

### 7.1 `nous/description.txt` (rewrite)

Eight sections, in order:

1. **Background** — queue-analysis Go server with `/solve` and `/target`. One-line acknowledgement that the analyzer was corrected in `99024df` and prior NOUS findings are not load-bearing.
2. **Analytic primitives** — Plain-text statement of the three formulas (per §3.1) with parameter glossary. One line: "These give per-iteration mean times. `/target` composes them through a state-dependent M/M/1 solver."
3. **Problem definition** — f(M), argmax over [1, 256]. One-line addition: "Use the analytic primitives to derive M̂(params) where possible, then refine via `/target` if needed."
4. **Scenarios** — The 6 dev scenarios from §4.2, named, with regime label. Path to benchmark grid noted but **not enumerated**; iter 1-4 work on the dev set.
5. **Harness contract** — Updated signature (per §6.1). Note prior strategies remain as baseline cohort.
6. **Pareto axes and scoring** — Unchanged: `(calls, gap_throughput_rel)`, worst-case primary. Truth cache paths.
7. **Stage plan** — The 5-iter table from §5, with mode and gate criteria explicit.
8. **Out of scope** — Per §6.6.

### 7.2 `nous/campaign.yaml` (rewrite)

```yaml
research_question: >
  Given the analytic primitives ITL(B), TTFT components, and τ(B) for a vLLM-style
  inference server, derive M̂(params) = argmax_M f(M) and design a formula-guided
  search that pinpoints argmax_M f via few /target calls. Score on (calls,
  gap_throughput_rel); see nous/description.txt for the full brief.

run_id: queue-throughput-formulas
max_iterations: 5
target_system: <unchanged from prior campaign.yaml>
prompts:
  methodology_layer: "prompts/methodology"
  domain_adapter_layer: null
```

`run_id` changes so prior campaign cache/state does not collide.

### 7.3 What NOUS does NOT see

- The MASCOTS 2026 paper PDF.
- The prior `description.txt` or its findings.
- The prior strategies' source.
- The dev-set truth caches up front (available via `/target` calls during the campaign, just not pre-loaded).

### 7.4 `formulas.py` visibility

NOUS sees `nous/harness/formulas.py` as a code module it can import. **Recommended over prose-only.** Drift between brief and oracle is the worse failure mode; we still ask NOUS to show its derivation in iter 1's report so the analytic story is preserved.

## 8. Success criteria

### 8.1 Per-iteration gates

| iter | gate (must produce) | failure handling |
|---|---|---|
| 1 | Closed-form M̂(params) for at least one binding case with explicit derivation. Open cases listed as "needs case analysis." | If no closed form on any case, formulas may be wrong or the optimization isn't analytically tractable. Halt; reconsider. |
| 2 | Regime partition (≤ 5 regimes) with boundary equations in (params). At least 3 regimes from the dev set covered. | If partition is just "always ITL" or "depends on everything," the formulas don't separate cleanly — flag as a finding. |
| 3 | Per-dev-scenario error table: gap_M = \|M̂ − M_truth\|, gap_f = (f_truth − f_M̂) / f_truth. Worst-case gap_f ≤ 20% on at least 4/6 scenarios. | If predictor is loose everywhere, iter 4 falls back to formula-as-bracket-only. |
| 4 | `formula_guided.py` strategy file. Predicted worst-case calls ≤ 8, gap_f ≤ 5% on dev set. Baseline `naive_ternary.py` also added. | If predicted bounds aren't met when run, iter 5 still runs but result is reported honestly (no retry-fudging). |
| 5 | Pareto plot on benchmark grid. Per-regime table: regime × (worst calls, worst gap). Honest comparison to prior strategies. | None — iter 5 is the report stage. |

### 8.2 Campaign-level success

The campaign succeeds if all of the following hold:

1. M̂(params) has a stated form (closed or piecewise) backed by derivation from the formulas.
2. The regime partition is empirically validated against dev scenarios.
3. `formula_guided` strictly Pareto-dominates `naive_ternary` on worst-case (calls, gap) on the benchmark grid.
4. The "is K=4 enough?" question gets a number from the campaign data, not a guess.

If 1–3 hold but 4 does not, that is a partial success: paper still gets an analytical predictor and a search algorithm, with a weaker structural story.

### 8.3 Likely failure modes

- **Predictor loose in one regime** (e.g., near boundaries, or unbounded): expected. Iter 4 uses M̂ as bracket center, not direct answer. Loose regime gets characterized in the paper as where search refinement matters.
- **Truth-cache regen reveals analyzer issues at edge cases** (e.g., L=4096 hangs, infeasibility regions explode): blocking. Halt; surface to user.
- **NOUS over-fits to dev set** (good on dev, bad on benchmark): what the dev/benchmark split is for. If iter 4 strategy works on dev but fails on benchmark, iter 5 reports it honestly; may need an iter 6 or accept the gap.

## 9. Post-campaign plan

1. **Paper revival.** Findings replace the stale `paper/sections/analysis.tex` skeleton on `paper-analysis-section`. Most of the paper structure (auto-scaling + concurrency control framing) stays valid; the analysis, predictor, and algorithm sections rebuild on the new derivation. Estimate: paper writing resumes ~1 week post-campaign.
2. **Memory updates.** Update `project_paper_analysis_section.md` (resumed); update `project_nous_campaign_status.md` (new run_id supersedes prior); add a new memory linking new campaign findings.
3. **Truth caches.** New caches (~37 files) committed. Old caches deleted. New cache layout (`nous/cache/bench/`).
4. **Branching.** New branch `nous-formula-campaign` off `main`. The `paper-analysis-section` branch retains paper-only commits and rebases onto whatever lands later. (Open: confirm branching choice with user before campaign starts.)

## 10. Cost estimate

- Truth-cache regen: ~10 minutes wall-clock (~9.5k `/target` calls @ ~50ms each).
- Five NOUS iterations: ~2-4 hours total compute + user review at each iteration's end.
- Paper revival once campaign completes: ~1 week of focused writing.

## 11. Open questions for implementation plan

These do not block the design but should be resolved before implementation begins:

1. Confirm branching: new `nous-formula-campaign` branch off `main`, or stay on `paper-analysis-section`?
2. Confirm `formulas.py` visibility to NOUS (recommended: visible as importable module; alternative: prose-only).
3. Confirm truth-cache scope: regenerate dev + benchmark in one batch, or stage (dev first, validate, then benchmark)?
4. Confirm the prior 4 strategies stay in the baseline cohort, or are pruned to e.g. only `predictor_direct.py` to keep the iter-5 comparison legible.
