# Paper — Analysis Section Design (revised)

**Working title:** *Scaling with Optimal Concurrency* (auto-scaling jointly with concurrency control)
**Section:** Analysis (shape of `f(M)`, the closed-form lower bound, and the regime partition)
**Venue target:** Conference / workshop (e.g. MLSys, SoCC, HotCloud) — reviewer-grade rigor
**Date:** 2026-06-12
**Status:** Approved (design); ready for implementation planning.

> **Supersedes** `docs/superpowers/specs/2026-06-10-paper-analysis-section-design.md`.
> That spec was written against the pre-reformulation analyzer and a 4-scenario set
> (`baseline, short-tight-ttft, long-loose-itl, small-queue`). The NOUS reformulation
> campaign (`queue-throughput-formulas`, merged via PR #8) redefined the objective,
> regenerated all truth caches, and replaced the scenario set. The old spec's central
> claims — `M* = R(M)=1` crossover, a tight predictor with `|error| ≤ 2`, and
> `M*=40` for the baseline — are **invalidated**: `40` was actually the closed-form
> *lower bound* `M_ITL`, not the onset (`M*=69`). This revision re-grounds every claim
> in the campaign's discovered principles (RP-1..RP-11, see
> `.nous/queue-throughput-formulas/principles.json`).

---

## 1. Purpose & scope within the paper

The analysis section is the technical heart of the paper. It characterizes
`f(M) = max-RPS-meeting-SLOs` as a function of `MaxBatchSize M`, and derives the
structural facts the Algorithm section builds on. It establishes four exploitable
properties:

- **P1** Two-phase shape: concave rise to a plateau.
- **P2** A model-grounded *lower bound* `M_ITL`, exact in closed form under `nc=1`,
  plus a primitive-only regime partition (`M_TPF` vs `M_ITL`) computable at zero
  oracle cost.
- **P3** `f(M)` is non-decreasing to a plateau, so a downward monotone-predicate
  search anchored at `m_max` locates the onset in `O(log M_max)` oracle calls.
- **P4** The occupancy gap `M*/M_ITL` is bounded but **non-constant** (1.59×–2.83× on
  the ITL-governed scenarios; up to ~6.3× on the benchmark), so `M_ITL` warm-starts a
  bounded search rather than predicting `M*` outright.

**Out of scope:** the search algorithm itself (Algorithm section), comparison with
prior auto-scaling / admission-control work, experimental Pareto results, and the
benchmark grid (the 30-scenario `scenarios_benchmark.json`) — this section uses the
6 "dev" scenarios where `nc=1` holds throughout.

## 2. Core quantities (precise definitions)

The section pins down the following, in this order:

- **`f(M)`** — the maximum request rate that meets *both* SLOs (average TTFT and
  average ITL) at batch size `M`. Operationally `f(M) = min(λ*_TTFT(M), λ*_ITL(M))`,
  where `λ*_TTFT, λ*_ITL` are the per-constraint maximum admissible rates returned by
  the `/target` endpoint (`RPSTargetTTFT`, `RPSTargetITL`).
- **`M*` (the onset, the target quantity)** — the smallest `M` with
  `f(M) ≥ (1−ε)·f_peak`, with `ε` stated explicitly (`ε = 0.02`). This is the
  concurrency-minimizing operating point the paper title promises.
- **`M_argmax` (reference point)** — the smallest `M` reaching the strict maximum of
  `f` (this is what the truth caches store as `M_truth`). On all six scenarios the
  plateau is float-flat, so `M_argmax = M*`; §3.5 explains when and why they diverge
  on wider grids (RP-10).
- **`M_ITL`** — the closed-form ITL-binding batch size,
  `M_ITL = clamp(⌊1 + (targetITL − itl(1))/δ⌋, 1, M_max)`, where
  `δ = (w_prefill(1) + w_decode)/(1 + m_out)` is the (constant, under `nc=1`) slope of
  the affine `itl(B)`. Exact under `nc=1` (RP-1); a **lower bound** on `M*` (RP-2).
- **`M_TPF`** — the largest `B` with `ttft_prefill(B) ≤ targetTTFT`. An **upper bound**
  on the `M` at which the TTFT constraint first binds (RP-5), not an upper bound on
  `M*`.

All primitives (`itl`, `ttft_prefill`, `tau`, `δ`, `w_prefill`, `w_decode`,
`num_iterations_per_prefill`) are the analytic service-time forms in
`pkg/analyzer/queueanalyzer.go:275-327` / `utils.go:8-47`, mirrored in
`nous/harness/formulas.py` (parity-checked against the Go source).

## 3. The six scenarios

From `nous/scenarios.json`. Three regimes are distinguishable from primitives alone
(RP-6); the labels below are the runtime (oracle-confirmed) regimes.

| Scenario     | Regime (runtime) | Primitive cell      | `M_ITL` | `M*` (onset) | `f*` [RPS] | gap `M*/M_ITL` |
| ------------ | ---------------- | ------------------- | ------- | ------------ | ---------- | -------------- |
| baseline     | crossover        | itl-or-crossover    | 40      | 69           | 1.9232     | 1.73×          |
| alpha-low    | crossover        | itl-or-crossover    | 107     | 170          | 5.1730     | 1.59×          |
| alpha-high   | crossover        | itl-or-crossover    | 6       | 17           | 0.2797     | 2.83×          |
| itl-only     | itl-only         | itl-or-crossover    | 8       | 17           | 0.1261     | 2.13×          |
| ttft-only    | ttft-only        | ttft-only (TPF<ITL) | 95      | 92           | 4.5230     | 0.97×          |
| unbounded    | unbounded        | unbounded           | 256     | 256          | 121.4636   | 1.00×          |

Notes:
- `baseline`, `alpha-low`, `alpha-high` share workload/targets and differ only in the
  service coefficients (`alpha, beta, gamma`) — a clean sensitivity sweep that gives
  the **N=3 crossover calibration set**.
- `itl-only` and `crossover` share the same primitive cell (RP-6) — the primitives
  cannot separate them; only the oracle can.
- `ttft-only` is the cell where `M_TPF (=70) < M_ITL (=95)` (RP-7); note `M* < M_ITL`
  here, consistent with the TTFT constraint, not ITL, governing the onset.

## 4. Narrative arc

Empirical-first, derivation-grounded:

1. **Show** the headline `f(M)` plot; name the two-phase pattern; define the onset
   `M*` and contrast it with `M_argmax`.
2. **Generalize** with the 6-scenario overlay (normalized); the same shape recurs.
3. **Ask** "why this shape?" → derive `f(M) = min(λ*_TTFT, λ*_ITL)`; the plateau is
   ITL saturation.
4. **Derive** the closed-form `M_ITL` from the affine `itl(B)` (under `nc=1`); prove it
   is an exact lower bound on `M*`.
5. **Classify** the regime from primitives alone via the `M_TPF` vs `M_ITL` ordering.
6. **Explain why search, not prediction**: the occupancy gap is bounded but
   non-constant, so `M_ITL` warm-starts a downward monotone-predicate search
   (`f*` anchored at `m_max`) that reaches the onset in a few oracle calls.
7. **Summarize** P1–P4 in algorithm-ready form.

## 5. Subsection structure

### 5.1 The shape of `f(M)`: a two-phase curve  `\label{sec:shape}`

Headline `f(M)` plot for the baseline + 6-scenario overlay. Open with the honest-scope
sentence: "Our claims are empirical across six scenarios and structural via the
queueing model; the empirical breadth is limited and the structural argument is the
load-bearing one for generality." Define `f(M)`, the onset `M*` (smallest `M` within
`ε=2%` of peak), and note that `M_argmax` (the cached `M_truth`) coincides with `M*`
here because the plateaus are float-flat (forward-ref to §5.5 for divergence). Concave
rise to `M*`, then plateau. **Fig 1, Fig 2.**

### 5.2 The structural cause: min of binding constraints  `\label{sec:min-constraints}`

The queueing model (cite Ramani & Tantawi, *Queueing model-based SLO-driven and
self-tuned LLM inference service scaling*) treats the server as a state-dependent
M/M/1 queue with a three-parameter service model (`α` per-iteration overhead, `β`
per-token compute, `γ` per-token KV-cache access). Two SLOs each cap the admissible
rate at a given `M`:
`λ*_TTFT(M)` and `λ*_ITL(M)`. The feasible frontier is the lower envelope
`f(M) = min(λ*_TTFT(M), λ*_ITL(M))`. Argue (RP-3) that `λ*_ITL` rises and **saturates**
(saturation throughput `S(B) = 1000·B/τ(B)` is concave, approaching `S_∞` from below),
while `λ*_TTFT` keeps rising; the two-phase shape of `f` is the consequence. **Fig 3.**

### 5.3 A closed-form lower bound: `M_ITL`  `\label{sec:mitl}`

Under `nc(B) = 1` for all `B ∈ [1, M_max]` (which holds on all six scenarios; RP-4
flags the `nc`-jump exception as out of scope), `itl(B)` is exactly affine in `B` with
slope `δ`. Inverting the ITL target gives the closed form
`M_ITL = clamp(⌊1 + (targetITL − itl(1))/δ⌋, 1, M_max)`, which matches a brute scan
with zero discrepancy (RP-1). Then prove `M_ITL` is a **lower bound** on `M*` (RP-2):
realized `AvgITL` averages over occupancy `≤ B`, so `AvgITL ≤ itl(B)`, and the ITL SLO
is met at batch sizes above `M_ITL`. State the worked baseline numbers
(`itl(1) ≈ 8.29`, `δ ≈ 0.297`, `M_ITL = 40`).

### 5.4 Regime classification from primitives  `\label{sec:regimes}`

The primitives partition parameter space into **exactly three** primitive-decidable
cells (RP-6): (1) unbounded (neither SLO binds at `M_max`), (2) ttft-only
(`M_TPF < M_ITL`), (3) itl-or-crossover (`M_ITL ≤ M_TPF`). The load-bearing signal is
the **ordering** `M_TPF` vs `M_ITL`, not the two binding booleans (RP-7: ttft-only
binds on both, so a 2×2 on booleans misclassifies it). `M_TPF` is an upper bound on the
TTFT-binding `M`, not on `M*`, because `ttft_prefill` excludes the M/M/1 queue wait
(RP-5: ttft-only has `M* = 92 > M_TPF = 70`). The itl-only and crossover runtime
regimes share cell (3) and are separated only by the oracle.

### 5.5 Why search, not prediction  `\label{sec:search}`

Three sub-points:

- **Plateau: structural vs numerical.** For `M ≥ M*`, ITL saturation bounds `f` above
  (structural). The `~10⁻⁴` wobble observed over the plateau is **solver noise**, not
  true flatness at machine precision — the structural claim guarantees boundedness, not
  constancy. We treat any `M ≥ M*` as achieving `f*` up to numerical precision.
- **Onset vs argmax (the "both, explicitly" paragraph).** `M_argmax` (cached
  `M_truth`) is the strict float-max point; on a float-flat plateau it equals the
  onset, but on wiggly plateaus it sits well above (RP-10: e.g. an onset near 46 vs an
  argmax of 118 on a benchmark scenario). The paper optimizes the **onset**;
  over-provisioning to `M_argmax` wastes concurrency. On our six scenarios they
  coincide, which is why the cached `M_truth` is a valid onset stand-in here.
- **The occupancy gap ⇒ search.** On the ITL-governed scenarios `M*/M_ITL` is bounded
  but **non-constant** (1.59×–2.83× here; up to ~6.3× on the benchmark per RP-2), so
  `M_ITL` cannot predict `M*` outright (the `unbounded` and `ttft-only` scenarios are
  not ITL-governed, so `M_ITL` is not the operative lower bound there). Instead it
  warm-starts a **downward monotone-predicate search** with
  `f*` anchored at `m_max` (RP-2/RP-3: the high anchor avoids underestimating the peak
  on occupancy-gap scenarios), reaching the onset in a bounded number of oracle calls
  (RP-8: `≤ 8` on the full benchmark). **Fig 4, Tab 1.**

### 5.6 Summary: properties exploited downstream  `\label{sec:summary}`

Restate P1–P4 in algorithm-ready form:
- **P1** Two-phase shape ⇒ optimization reduces to onset detection.
- **P2** `M_ITL` (exact lower bound, `nc=1`) + the `M_TPF`/`M_ITL` regime partition ⇒
  a zero-oracle-cost warm start and regime-aware seeding.
- **P3** `f` non-decreasing to a plateau ⇒ downward monotone-predicate search converges
  in `O(log M_max)`; anchor `f*` at `m_max`.
- **P4** Occupancy gap bounded but non-constant ⇒ pure prediction is insufficient;
  warm-started bounded search achieves the onset in a few calls.

## 6. Plot & table specifications

Four figures and one table. Sources: truth caches `nous/cache/truth-*.json`
(`f_curve`: 256 `{m, throughput}` points, plus `M_truth`, `throughput_truth`, `regime`)
and a regenerated `/target` sweep cached under `paper/data/`.

- **Fig 1 — Headline `f(M)`, baseline.** x: `M ∈ [1,256]` linear; y: `f(M)` [RPS].
  Mark the onset `M* = 69` (vertical dashed) with annotation; shade/annotate rising vs
  plateau. Single curve. Note in caption that `M_argmax` coincides here.

- **Fig 2 — Six-scenario overlay, normalized.** x: `M`; y: **`f(M)/f*`** (normalized,
  because `f*` ranges from 0.13 to 121 RPS — a raw overlay is unreadable). One curve per
  scenario, grouped/colored by regime (crossover ×3, itl-only, ttft-only, unbounded),
  onset markers. Caveat in caption: six scenarios are not a universality proof; the
  structural argument carries generality.

- **Fig 3 — Min-of-constraints decomposition, baseline.** x: `M`; y: RPS. Three curves
  `λ*_TTFT(M)`, `λ*_ITL(M)`, `f(M)=min(·)`; shade `M < M*` (TTFT binds) vs `M ≥ M*`
  (ITL binds / saturated). From the regenerated sweep.

- **Fig 4 — Lower bound & bracket, baseline (replaces the old R(M) figure).** `f(M)`
  with three vertical markers: `M_ITL = 40` (closed-form lower bound), `M* = 69` (onset),
  `M_TPF` (TTFT-binding upper bound). Visualizes the bracket `[M_ITL, …]` the search
  exploits and the non-trivial occupancy gap.

- **Tab 1 — Lower bound, regime, and gap** (`tabs/lower_bound_regime.tex`). Columns:
  Scenario, regime, `M_ITL`, `M_TPF`, `M*` (onset), `M_argmax`, occupancy gap
  `M*/M_ITL`, `gap_f` at `M_ITL` (relative throughput shortfall if you stopped at the
  lower bound). Six rows. Replaces the old "predictor accuracy `|error|≤2`" table with
  the honest "exact lower bound, variable gap" story. The three crossover rows are the
  `N=3` calibration set; the no-crossover rows show the primitive classifier working.

**Source-of-truth notes:**
- Figs 1, 2 and the `M*`/`M_argmax`/`f*` columns read directly from truth caches — no
  new oracle calls.
- Fig 3 and Fig 4's `M*` marker need the regenerated `/target` sweep over `M ∈ [1,256]`
  for the baseline. `M_ITL`, `M_TPF` are computed from the closed forms (no oracle).
- The sweep script must be rewritten for the **current** `nous/scenarios.json`
  (a `{search_range, scenarios:[…]}` object) and the **camelCase** `/target` request
  and response fields (`maxBatchSize`, `targetTTFT`, `targetITL`, `maxQueueSize`,
  `throughput`, `RPSTargetTTFT`, `RPSTargetITL`). The old PascalCase script is stale.

All plots via a single Python script under `paper/scripts/`; outputs to `paper/figs/`
and `paper/tabs/`. Script + source data committed for reproducibility.

## 7. Claims and how each is defended

| #  | Claim | Defense |
| -- | ----- | ------- |
| C1 | `f(M)` is two-phase (concave rise then plateau) on our six scenarios | Empirical: Figs 1, 2 from truth caches |
| C2 | The shape arises structurally from `f(M) = min(λ*_TTFT, λ*_ITL)`, with `λ*_ITL` saturating | Model-grounded (Ramani–Tantawi state-dependent M/M/1); RP-3; Fig 3 |
| C3 | `M_ITL` is exact in closed form under `nc=1` | RP-1: `itl(B)` affine ⇒ closed-form inversion; zero-discrepancy vs brute scan; worked baseline (`M_ITL=40`) |
| C4 | `M_ITL` is a **lower bound** on the onset `M*` | RP-2: `AvgITL ≤ itl(B)` (occupancy averaging) ⇒ ITL SLO met above `M_ITL`; Tab 1 gaps all `≥ 1` except ttft-only where TTFT governs |
| C5 | The primitives partition parameter space into exactly 3 cells; `M_TPF` vs `M_ITL` ordering is the load-bearing signal | RP-6, RP-7; `M_TPF` is an upper bound on the TTFT-binding `M`, not `M*` (RP-5) |
| C6 | The plateau is structural; observed wobble is solver noise; `M_argmax` ≠ onset on wiggly plateaus | RP-3 (saturation) + RP-10 (argmax/onset divergence); numerical caveat with noise-floor framing |
| C7 | The occupancy gap `M*/M_ITL` is bounded but **non-constant** (1.59×–2.83× on ITL-governed scenarios), so `M_ITL` warm-starts a bounded search rather than predicting `M*` | RP-2 (gap range, oracle-confirmed) + RP-8 (high-anchor downward search, `≤8` calls). **Honest framing: this is the corrected replacement for the old spec's over-claimed "tight predictor, `\|error\|≤2`".** |

**Design decisions encoded above:**
- **C6 downgrades** the plateau-flatness claim from "<0.08% variation" to "structurally
  bounded; numerically near-flat at the solver's precision," and adds the onset/argmax
  distinction.
- **C7 is the corrected core finding.** The old spec claimed `M_est` predicts `M*` to
  `|error| ≤ 2`; the campaign showed the gap to `M*` is non-constant and `M_ITL` is only
  a lower bound. We present `M_ITL` as an exact, derivable *lower bound + warm start*,
  not a predictor. We do **not** call anything a "closed-form prediction of `M*`".

**Deferred work** (called out in §5.5 and Future Work): an analytical expression for the
occupancy gap (relating `M*` to `M_ITL` via the queue's light/heavy-traffic asymptotics)
would turn the warm-started search into a tighter predictor; the Ramani–Tantawi analytic
paper is the canonical source for that derivation.

## 8. Honest framing of limitations (inline)

- **Start of §5.1:** the empirical-vs-structural scope sentence.
- **§5.3:** `nc=1` is required for the exact closed form; `nc`-jump grids incur a ±1
  error (RP-4) and are out of scope here.
- **§5.5:** the onset/argmax divergence and the non-constant occupancy gap, stated
  plainly; no "tight predictor" language.
- **Limitations note:** six scenarios are not universality; all results are from the
  analytic simulator (`formulas.py` / the Go analyzer), not a real vLLM server
  (real servers add stochastic token lengths, KV eviction, chunked prefill that may
  violate `nc=1` or the M/M/1 model).

## 9. Deliverable artifacts

```
paper/
├── main.tex                     # driver (exists)
├── cite.bib                     # bibliography; add Ramani–Tantawi entry
├── .gitignore                   # exists
├── README.md                    # exists; update regen instructions
├── sections/
│   └── analysis.tex             # this section (§5.1–5.6)
├── figs/
│   ├── fig1_baseline_fM.pdf
│   ├── fig2_overlay_fM.pdf            # normalized f/f*
│   ├── fig3_min_constraints.pdf
│   └── fig4_lower_bound_bracket.pdf   # replaces R(M) crossover
├── tabs/
│   └── lower_bound_regime.tex         # replaces predictor_accuracy
├── data/
│   └── baseline_lambda_sweep.json     # REGENERATED for current analyzer/scenarios
└── scripts/
    ├── requirements.txt          # exists
    ├── sweep_baseline.py         # REWRITTEN for new scenarios.json + camelCase
    └── make_figures.py           # figs + table from caches + sweep
```

**Section deliverables:**
- `paper/sections/analysis.tex` — §5.1–5.6, ~3–4 pages with 4 figures + 1 table.
- `paper/figs/fig{1..4}_*.pdf` — from `make_figures.py`.
- `paper/tabs/lower_bound_regime.tex` — from the same script.
- `paper/data/baseline_lambda_sweep.json` — regenerated `/target` sweep.
- `paper/scripts/sweep_baseline.py` (rewritten) and `make_figures.py` (new).
- `paper/cite.bib` — Ramani–Tantawi analytic-paper entry.

**Out of scope:** all other sections (Background, Motivation, Problem, Algorithm,
Experiments), full bibliography, final polish, and the 30-scenario benchmark.
