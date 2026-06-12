# Paper — Experiments Section Design

**Working title:** *Scaling with Optimal Concurrency* (auto-scaling jointly with concurrency control)
**Section:** Experiments / Evaluation — *validate & demonstrate the onset search*
**Venue target:** Conference / workshop (e.g. MLSys, SoCC, HotCloud) — reviewer-grade rigor
**Sub-issue:** #14 (under epic #11)
**Date:** 2026-06-12
**Status:** Approved (design); ready for implementation planning.

---

## 1. Purpose & scope within the paper

The Experiments section supplies the **measured evaluation** that both prior sections
forward-reference via `\ref{sec:experiments}` (Analysis `paper/sections/analysis.tex` and
Algorithm `paper/sections/algorithm.tex`). It must (a) define `\label{sec:experiments}` so
those dangling references resolve, and (b) deliver the minimal evidence that the
Formula-Guided Onset Search of §Algorithm does its job.

**Two goals, deliberately minimal (brainstorm decision):**

1. **Validate** — the algorithm finds the ε-onset accurately, at low oracle cost, within the
   SLO-feasibility tolerance, and **Pareto-dominates** the two naive search baselines on the
   concurrency objective `(calls, gap_onset)` at `gap_f ≤ ε`.
2. **Demonstrate** — one *measured* onset-search trace showing the algorithm's actual probes
   landing on the onset.

The section is explicit that these are **numerical experiments over the analytic queueing
model** of Ramani and Tantawi (`\cite{ramani2026queueing}`) — exploration and validation,
not a live-serving study. The substantive comparative experiment (the impact of limiting
**concurrency** versus other admission/limiting schemes) is **future work**, scoped in §3.4.

It reuses all established notation — `f(M)`, the *oracle* (one analytic SLO-feasible-rate
evaluation), the onset `M*`, peak `f*`, tolerance `ε = 2%`, primitives `M_ITL`, `M_TPF`,
`M_max` — and introduces **no new preliminaries**.

## 2. Out of scope

- **No new algorithm or analysis.** Those live in §Analysis / §Algorithm; this section only
  measures the committed `formula_guided` strategy and the two baselines.
- **No live-vLLM evaluation.** Stated as the headline future-work item, not performed.
- **No exhaustive ablation battery.** The single load-bearing design choice (the high anchor
  at `f(M_max)`) is referenced as a one-line fact from the campaign (bench-023, `gap_f = 0.22`
  under a `U`-seed), not re-run as a dedicated ablation subsection. Cell-aware seed and
  `MAX_ITERS` are mentioned only as already-justified in §Algorithm.
- **No variable-`nc` extension / multi-probe `f*`** — already flagged as future work in
  §Analysis and §Algorithm.

## 3. Section structure

Four short subsections. Target ≈ 1–1.5 columns plus one table and one figure.

### 3.1 Setup & protocol (≈ ⅓ column)
- **Oracle.** One call = one analytic `/target` evaluation returning the SLO-feasible rate at
  a given `M` (same definition as §Analysis). State that all numbers come from this analytic
  model, not a live server.
- **Scenarios.** The 6 dev scenarios spanning the four regimes (crossover ×3, ITL-only,
  TTFT-only, unbounded) and the **30-scenario benchmark** drawn by Latin-hypercube sampling
  (seed = 42) over the parameter ranges. Of the 30, **25 are feasible**; 5 are genuinely
  infeasible everywhere (all-zero `f` curves) and are reported separately (the strategies must
  return `m_min` there, `gap_M = 0`).
- **Truth caches.** For every scenario the oracle is evaluated exhaustively at all
  `M ∈ [1, 256]`, giving the ground-truth `f(M)` curve, the strict argmax `M_truth`, and the
  peak `throughput_truth`. The **ε-onset** is computed from the cached curve as the smallest
  `M` with `f(M) ≥ (1−ε)·max_M f(M)`.
- **Replay protocol.** The three committed strategies are replayed **offline** against the
  caches with a counted, cache-backed oracle (no Go server); call counts and chosen `M`
  reproduce the live-campaign values exactly because the strategies are deterministic and the
  cache is the oracle tabulated at every `M`. One confirmatory `oracle(M_chosen)` call is added
  after each strategy returns (matching `nous/harness/run.py`), so reported `calls` include
  that `+1`.

### 3.2 Onset accuracy & cost (the one quantitative artifact)

One table (`paper/tabs/eval_comparison.tex`) comparing the three strategies on the **25
feasible benchmark scenarios** (worst / mean), with the 6 dev scenarios summarised in prose.

**Metric order — lead with the objective (brainstorm decision "report both, lead with onset"):**

| Strategy | oracle calls | gap_onset (worst / mean) | gap_f (worst) | gap_argmax (worst) |
|---|---|---|---|---|
| `formula_guided` | ≤ 8 | *(computed)* | 0.0138 ✓ (< ε) | 72 |
| `naive_ternary` | ~30 | *(computed)* | 0.0286 ✗ | 145 |
| `naive_max` | 1 | *(computed)* | 0.0286 ✗ | 251 |

- **gap_onset = |M_chosen − M*|** against the ε-onset — the *actual* objective the algorithm
  optimises. This is the **leading** column.
- **gap_f** = relative throughput shortfall (`scoring.compute_gap`'s `gap_throughput_rel`);
  the SLO-feasibility tolerance is `ε = 0.02`. `formula_guided` is the only strategy that never
  violates it; both baselines violate on bench-025 (interior-peak, `nc` 1→67).
- **gap_argmax = |M_chosen − M_truth|** against the strict float-argmax — reported **second**,
  for continuity with the campaign's published `gap_M`. The text explains the
  **argmax-vs-onset structural floor** (RP-10): on float-wiggly plateaus the strict argmax
  sits far above the onset (e.g. bench-019: argmax 118 vs onset ≈ 46), so most of
  `formula_guided`'s worst `gap_argmax = 72` is this floor, **not** strategy error. Targeting
  the onset is the design intent (§Algorithm), so `gap_onset` is the honest accuracy measure.
- **Takeaway sentence:** `formula_guided` is the only strategy simultaneously *cheap*,
  *SLO-feasible*, and *near-onset* — it Pareto-dominates both baselines on `(calls, gap_onset)`
  subject to `gap_f ≤ ε`. The dev set corroborates (worst `gap_f ≤ 0.0101`, `calls ≤ 8`).

All numbers must be (re)generated by the eval script (§4) and **verified against
`report.md` / `scoring.py`** before drafting; the `(computed)` cells are filled from the
script output, not from memory. If a recomputed value disagrees with the campaign's published
number, the discrepancy is investigated and resolved (the script is the source of truth for
the paper), and the cause noted.

### 3.3 A measured search trace (the demonstration figure)

Upgrade `fig5_onset_search` from **illustrative** to **measured**: replay `formula_guided` on
the **baseline** scenario through the cache-backed oracle and plot the *actual* probes it
issued — the seed at the constraint endpoint, the anchored threshold `(1−ε/2)f*`, and the
downward bisection midpoints — over the true `f(M)` curve, landing on the onset `M*`. This
resolves the Algorithm section's fig5 forward-reference ("the measured evaluation is in
§Experiments") with real data.

- Decision: **reuse `fig5`'s filename/layout** so the Algorithm section's `\ref` to it stays
  valid; change its data source from the hand-replayed schematic to the eval-script trace and
  update the caption from "Illustrative" to measured. The generator records the probe sequence
  the same way the replay does, so figure and table come from one code path.
- If keeping the Algorithm-section schematic *and* adding a measured trace reads better, the
  measured trace becomes a **new** figure in §Experiments (e.g. `fig6_measured_trace.pdf`) and
  fig5 stays the schematic. **Default: upgrade fig5 in place**; the plan revisits this once the
  trace data is in hand. Either way the Algorithm `\ref` must resolve.

### 3.4 Scope & threats to validity (≈ ⅓ column)
A short, honest subsection:
- **Analytic oracle, not live vLLM.** All results assume the three-parameter service model and
  Markovian arrivals; real servers add stochastic token lengths, KV-cache eviction, and chunked
  prefill that may break `nc=1` or the M/M/1 wait model. Calibrating the analytic primitives
  against measured vLLM is the headline future-work item.
- **`nc = 1` regime.** The exact closed-form `M_ITL` holds where a single prefill chunk suffices
  (all dev scenarios; most of the benchmark). Under `nc`-jumps `itl` is piecewise-affine and the
  warm start can err by a step (already noted in §Analysis).
- **argmax-vs-onset floor.** Restate that residual `gap_argmax` is structural (RP-10), and that
  the section reports `gap_onset` as the faithful objective.
- **Future work — the real comparative study.** The substantive experiment we have *not* run:
  measuring the end-to-end impact of limiting **concurrency** (operating at the onset `M*`)
  versus other admission/limiting schemes (e.g. rate limiting, queue-length caps, no limit) on
  latency-SLO attainment and goodput, on a live server. The present section validates that the
  algorithm *finds* the right operating point; quantifying the *benefit* of operating there
  against alternatives is the next paper's evaluation.

## 4. Reproducibility & data flow

Mirror the existing pipeline (`paper/scripts/make_figures.py` + `paper/data/` + caches), fully
offline (no Go server), runnable under `paper/scripts/.venv`.

- **New `paper/scripts/eval_strategies.py`:**
  - For each scenario (6 dev via `nous/cache/truth-*.json`; 30 bench via
    `nous/cache/bench/bench-*.json`), load `f_curve`, `M_truth`, `throughput_truth`, `regime`.
  - Build a **counted, cache-backed `target_eval(m)`** → `{"throughput": f_curve[m-1].throughput}`;
    a `0.0` reading (infeasible) returns `{"throughput": 0.0}` **uncounted**, mirroring
    `nous/harness/oracle.py`.
  - Compute the **ε-onset** per scenario: smallest `m` with `f(m) ≥ (1−ε)·max_M f(m)`,
    `ε = 0.02`.
  - Import the three committed `search()` callables from
    `nous/harness/strategies/{formula_guided,naive_max,naive_ternary}.py` (they import only
    `nous.harness.formulas`, pure-stdlib — add repo root to `sys.path`; **no Go/requests/numpy
    dependency** for strategy logic). Reuse `nous.harness.run.load_strategy` if convenient.
  - Run each strategy with the cache-backed oracle; add one confirmatory `oracle(M_chosen)`
    call (matching `run.py`'s `+1` accounting). Record per scenario:
    `strategy, scenario, regime, M_chosen, calls, throughput_chosen, M_onset, M_truth,
    gap_onset = |M_chosen − M_onset|, gap_argmax = |M_chosen − M_truth|, gap_f`.
  - Write `paper/data/eval_results.json` (one record list), plus a small aggregate block
    (worst/mean per strategy over the 25 feasible bench scenarios; dev summarised) so the table
    emitter does no re-derivation.
- **`paper/scripts/make_figures.py` gains:**
  - `tab2_eval_comparison()` → `paper/tabs/eval_comparison.tex` from `eval_results.json`
    (columns in the §3.2 order; ✓/✗ on the `gap_f < ε` check).
  - Update `fig5_onset_search()` to source its probe sequence from the eval replay on the
    baseline scenario (measured), updating the caption. (Or add `fig6_measured_trace.pdf` per
    §3.3's fallback.)
- **README "Regenerate" steps** extended with `python eval_strategies.py` before
  `python make_figures.py`.
- **Determinism.** The replay is deterministic (cache lookups + deterministic strategies); no
  RNG in the eval path. The benchmark LHS seed (42) lives in the existing scenario generator,
  not in the paper eval.

## 5. Notation & consistency requirements

- Reuse §Analysis / §Algorithm symbols verbatim: `f(M)`, `M*`, `f*`, `ε`, `M_ITL`, `M_TPF`,
  `M_max`, oracle. The ε-onset symbol `M*` is the same onset defined in §Analysis (smallest `M`
  within `ε` of peak), **not** the strict argmax `M_truth`.
- `ε = 0.02`, `MAX_ITERS = 6` match `formula_guided.py`.
- Quantitative claims (`gap_f` worst, `calls` budget, the bench-019 argmax/onset numbers, the
  bench-023/025 facts) must match the regenerated `eval_results.json` and the campaign
  `report.md` / `principles.json`. **Verify against source before drafting; do not paraphrase
  numbers from memory.**
- Strategy display names in the table: `formula_guided` → "Formula-guided",
  `naive_ternary` → "Parameter-blind ternary", `naive_max` → "Naive-max", matching the
  §Algorithm "Baselines" prose.

## 6. Build & verification

- Add `\input{sections/experiments}` to `paper/main.tex` (uncomment the existing commented
  line) and ensure `\label{sec:experiments}` is defined so the §Analysis and §Algorithm
  forward-references resolve with **no undefined refs**.
- Full-paper build (`latexmk -pdf main.tex`) must pass cleanly.
- The eval script + figure/table generators must run under `paper/scripts/.venv` and regenerate
  `eval_results.json`, `eval_comparison.tex`, and the trace PDF deterministically.
- Sanity gate before drafting prose: confirm the regenerated `formula_guided` worst `gap_f`,
  `calls`, and `gap_argmax` reproduce `report.md` (0.0138, ≤8, 72) within rounding; record
  the freshly-computed `gap_onset` values (new, not in `report.md`).

## 7. Deliverables

- `paper/sections/experiments.tex` — the section (defines `\label{sec:experiments}`).
- `paper/scripts/eval_strategies.py` — offline replay → `paper/data/eval_results.json`.
- `paper/tabs/eval_comparison.tex` — the comparison table (generated).
- Measured onset-search trace: updated `paper/figs/fig5_onset_search.pdf` (or new
  `fig6_measured_trace.pdf`) + generator hook in `paper/scripts/make_figures.py`.
- `paper/main.tex` — `\input{sections/experiments}` uncommented.
- `paper/README.md` — regenerate steps updated.
- Epic #11 checklist: tick "Experiments / Evaluation" and link sub-issue #14.
- PR against `main`, mirroring the Analysis (#10) and Algorithm (#13) flow.
