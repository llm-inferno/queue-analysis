# Paper — Analysis Section Design

**Working title:** *Scaling with Optimal Concurrency* (auto-scaling jointly with concurrency control)
**Section:** Analysis (shape of f(M))
**Venue target:** Conference / workshop (e.g. MLSys, SoCC, HotCloud) — reviewer-grade rigor
**Date:** 2026-06-10
**Status:** Approved (design); ready for implementation planning.

---

## 1. Purpose & scope within the paper

The analysis section is the technical heart of the paper: it characterizes
`f(M) = max-RPS-meeting-targets` as a function of `MaxBatchSize M`, and derives the
structural facts that downstream sections (Algorithm, Experimentation) build on.

It sits after Background / Motivation / Problem-statement, and feeds the Algorithm
section by establishing four exploitable properties:

- **P1** Two-phase shape: concave rise, then plateau.
- **P2** `M*` is the TTFT/ITL binding-constraint crossover (`R(M)=1`).
- **P3** `R(M)` is monotone in the rising phase.
- **P4** A model-grounded predictor `M_est` locates `M*` within a tight bracket.

**Out of scope** for this section: search algorithms themselves, comparison with
prior work on auto-scaling / admission control, experimental Pareto results.

## 2. Narrative arc

Empirical-first, derivation-grounded:

1. **Show** the headline plot of `f(M)` for the baseline; name the two-phase pattern.
2. **Generalize** with the 4-scenario overlay; note the same shape recurs.
3. **Ask** "why does this shape arise?" — set up the min-of-constraints argument.
4. **Derive** `λ*_TTFT(M)` and `λ*_ITL(M)` from the queueing model;
   show `f(M) = min(·)` produces the two-phase shape.
5. **Introduce** `R(M) = λ*_TTFT/λ*_ITL`; show monotonicity in the rising phase;
   locate `M*` as the `R(M)=1` crossing.
6. **Predict** `M*` in closed form: derive what we can; calibrate the residual
   honestly against the 4 scenarios.
7. **Summarize** the four properties (P1–P4) the algorithm will exploit.

Each step earns the next: the plots motivate the structural question, the structural
argument earns the right to talk about `R(M)`, `R(M)` earns the predictor, and the
predictor earns the algorithm.

## 3. Subsection structure

### 3.1 The shape of f(M): a two-phase curve

Headline `f(M)` plot for baseline + 4-scenario overlay. State the empirical
observation: concave rise to `M*`, then flat plateau (variation `< 0.08%` of `f*`
on our scenarios). Open with the honest scope sentence: "Our claims are empirical
across 4 scenarios and structural via the queueing model; the empirical breadth is
limited and the structural argument is the load-bearing one for generality."

### 3.2 The structural cause: min of binding constraints

Recall the queueing model. Derive `λ*_TTFT(M)` and `λ*_ITL(M)`. Show
`f(M) = min(λ*_TTFT, λ*_ITL)`. The min-of-constraints plot. Conclude: the kink is
where the binding constraint switches.

### 3.3 Locating M*: the crossover ratio R(M)

Define `R(M) = λ*_TTFT(M) / λ*_ITL(M)`. Argue monotonicity of `R` in the rising
phase from the model. `M* = smallest M with R(M) ≥ 1`. Plot `R(M)` with crossing
marker. Note `R(M)` need not be monotone past `M*` (the handoff doc flags this for
`short-tight-ttft`) — out of scope here, since `M*` is what we need.

### 3.4 The plateau and the no-crossover case

Two related but distinct claims:

- **Structural:** for `M ≥ M*`, the binding constraint switches from TTFT to ITL,
  and `λ*_ITL(M)` saturates (additional batch slots cannot be used productively
  given the ITL target). So `f` is bounded above and approaches a limit.
- **Numerical:** what we observe in the truth caches is `f` varying within `~10⁻⁴`
  of `f*` over the plateau. This is **not** evidence of true flatness at machine
  precision — the analyzer's iterative solver introduces noise at that scale, and
  the structural claim only guarantees boundedness, not constancy.

**Implication for algorithms:** any "improvement" past `M*` below the solver's
noise floor is not actionable. We define `f* := f(M*)`, treat any `M ≥ M*` as
achieving `f*` up to numerical precision, and acknowledge a small lower bound on
achievable `gap_throughput_rel` set by the solver.

The **no-crossover case** (`sign(wait_budget) < 0`) is the trivial extreme of the
same phenomenon: TTFT never becomes the binding constraint, so `M*` effectively
sits at or beyond `M_max` and any large-enough `M` achieves `f*` (within solver
noise). The classifier `sign(wait_budget)` distinguishes the two cases at zero
oracle cost (RP-10).

### 3.5 A model-grounded predictor for M*

Derive `M_est` term-by-term:

- `n_ITL` is exact from affine `DecodeTime(M)`.
- The `√n_ITL` "safety-stock" term: attempt derivation from the queueing-theoretic
  literature (light-traffic / heavy-traffic asymptotics).
- The `wait_budget` contribution: attempt derivation from `PrefillTime(n_ITL)` and
  the TTFT budget.

Whatever residual remains is fit on the 4 scenarios and **labeled clearly as
empirical**. We do **not** call this a "closed-form derivation" if free parameters
survive. Report `|M_est − M*| ≤ 2` with explicit caveats: N=3 crossover scenarios
calibrate any fit coefficients.

**Closing paragraph** (deferred-work pointer): we explicitly flag that relating
`M_est` to an analytical expression from the queueing model itself — likely an
asymptotic or limiting-case argument (large-`n_ITL`, light/heavy-traffic regimes)
— is ongoing work. The analytic paper (referenced in memory) is the canonical
source for these derivations.

### 3.6 Summary: properties exploited downstream

Restate **P1–P4** in algorithm-ready form, e.g.:

- P1 ⇒ optimization reduces to plateau-onset detection.
- P2 ⇒ `M*` is locatable by solving a 1D crossing problem.
- P3 ⇒ bracketing converges in `O(log M_max)`.
- P4 ⇒ `M_est` warm-starts the bracket, reducing call count to `O(1)` for a fixed
  predictor accuracy.

This subsection is short (~half a page) but earns its keep by giving the algorithm
section a clean handoff.

## 4. Plot specifications

Four figures and one table, all sourced from existing truth caches `nous/cache/truth-*.json`
(256 (m, throughput) points per scenario) plus a few targeted `/target` probes for
derived quantities (`R(M)`, `λ*_TTFT`, `λ*_ITL`).

- **Fig 1 — Headline f(M), baseline.** x: `M ∈ [1, 256]` (linear); y: `f(M)` [RPS].
  Mark `M* = 40` with a vertical dashed line and "M*" label; annotate the rising
  phase and plateau regions. Single curve. Section anchor — keep uncluttered.

- **Fig 2 — Four-scenario overlay.** Same axes; one curve per scenario (baseline,
  short-tight-ttft, long-loose-itl, small-queue) with `M*` markers. Single y-axis.
  Reader should see "same shape, different `M*`" at a glance. Caveat in caption:
  4 scenarios, not a universality proof.

- **Fig 3 — Min-of-constraints decomposition, baseline.** x: `M`; y: RPS. Three
  curves: `λ*_TTFT(M)`, `λ*_ITL(M)`, `f(M) = min(·)` overlaid. Shade `M < M*`
  (TTFT binds) vs. `M ≥ M*` (ITL binds / saturated). The most important figure
  in the section — visualizes the structural argument.

- **Fig 4 — R(M) crossover, baseline.** Two-panel stacked: top `f(M)` with `M*`
  marker; bottom `R(M) = λ*_TTFT/λ*_ITL` with `R=1` line and crossing marked.
  Aligned x-axis. Stops at the crossover (caption notes non-monotonicity past
  `M*`).

- **Tab 1 — Predictor accuracy.** TeX table (`tabs/predictor_accuracy.tex`)
  showing `M_est`, `M_truth`, `|error|`, and `gap_throughput_rel` for each of the
  4 scenarios. Honestly labeled as N=3 crossover calibration; the no-crossover row
  shows the `sign(wait_budget)` classifier worked.

**Source-of-truth notes:**

- Figs 1, 2 read directly from truth caches — no new oracle calls.
- Figs 3, 4 require pulling `RPSTargetTTFT` and `RPSTargetITL` from `/target`
  responses across `M ∈ [1, 256]` for the baseline. `/target` returns these
  fields (`pkg/service/analyzer.go:118-160`). One pass = 256 calls.
- Tab 1 needs nothing beyond what we have.

All plots produced via a small Python script under `paper/scripts/`; outputs into
`paper/figs/` and `paper/tabs/`. Script and source data committed so figures are
reproducible.

## 5. Claims and how each is defended

| #  | Claim                                                                                          | Defense                                                                                                                                                                                                                              |
| -- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| C1 | `f(M)` is two-phase (concave rise then plateau) on our scenarios                               | Empirical: Figs 1, 2 from truth caches                                                                                                                                                                                               |
| C2 | The shape arises structurally from `f(M) = min(λ*_TTFT, λ*_ITL)`                               | Model-grounded: derive `λ*_TTFT(M)`, `λ*_ITL(M)` from the state-dependent M/M/1; Fig 3 visualizes                                                                                                                                    |
| C3 | `M*` is the smallest `M` where `λ*_TTFT(M) ≥ λ*_ITL(M)`, equivalently `R(M) ≥ 1`               | Definition + monotonicity argument                                                                                                                                                                                                   |
| C4 | `R(M)` is monotone increasing in the rising phase                                              | Derive from monotonicity of `λ*_TTFT/λ*_ITL` in `M`; restrict claim to rising phase (handoff explicitly notes non-monotone past `M*` for `short-tight-ttft`)                                                                         |
| C5 | The plateau is structural; observed wobble is solver noise                                     | Structural argument from §3.4; numerical caveat with explicit noise-floor estimate from the truth caches                                                                                                                             |
| C6 | `sign(wait_budget)` classifies crossover vs no-crossover                                       | Model-grounded: `wait_budget < 0` ⟺ TTFT target unreachable even at the smallest viable `M`; verify on 4 scenarios (RP-10)                                                                                                           |
| C7 | `M_est = round(n_ITL + c₁·√n_ITL + c₂·wait_budget)` is accurate to `\|error\| ≤ 2` on the 4 scenarios | `n_ITL`: derived exactly from affine `DecodeTime(M)`. `√n_ITL` term: attempted derivation; if fully derivable, `c₁` is no longer free. `wait_budget` term: attempted derivation; otherwise calibrated. **Honest framing: empirical fit covers N=3 crossover scenarios; we do not claim universality.** |

**Two design decisions encoded above:**

- **C5 explicitly downgrades** the plateau-flatness claim from the report's
  "< 0.08% variation" framing (which conflates structure with noise) to
  "structurally bounded; numerically near-flat at the solver's precision."
- **C7 is the section's weakest claim and we treat it as such.** We push the
  derivation as far as we can and label the residual empirical with N=3
  calibration data. We do **not** call it a "closed-form derivation" if free
  parameters survive.

**Deferred work** (called out in §3.5 closing and the paper's Future Work): relate
`M_est` to an analytical expression from the queueing model itself — likely
asymptotic or limiting-case (large-`n_ITL`, light/heavy traffic). Source: the
analytic paper (Overleaf, recorded in `reference_analytic_paper` memory).

## 6. Honest framing of limitations (within the section)

Caveats are **inline** rather than dumped in a Limitations section at the end:

- **At the start of §3.1**, one sentence: "Our claims are empirical across 4
  scenarios and structural via the queueing model; the empirical breadth is
  limited and the structural argument is the load-bearing one for generality."
- **At the end of §3.5**, the closing paragraph: derivation-vs-fit boundary stated
  explicitly; deferred-work pointer to the asymptotic analysis.

This pre-empts reviewer pattern-match without burying the lede.

## 7. Deliverable artifacts

Paper layout (TeX, agreed structure):

```
paper/
├── main.tex                  # small driver; \input section files
├── cite.bib                  # bibliography
├── sections/
│   └── analysis.tex          # this section
├── figs/
│   ├── fig1_baseline_fM.pdf
│   ├── fig2_overlay_fM.pdf
│   ├── fig3_min_constraints.pdf
│   └── fig4_R_crossover.pdf
├── tabs/
│   └── predictor_accuracy.tex
├── data/                     # cached /target sweep for Figs 3, 4 (so figures
│   └── baseline_lambda_sweep.json   #   regenerate without re-running analyzer)
└── scripts/
    └── make_figures.py       # produces figs/ and tabs/ from truth caches + data/
```

**Section deliverables for this design:**

- `paper/sections/analysis.tex` — section text, ~3-4 pages with 4 figures + 1 table (in a 10-page paper budget).
- `paper/figs/fig{1..4}_*.pdf` — produced by `paper/scripts/make_figures.py`.
- `paper/tabs/predictor_accuracy.tex` — produced by the same script.
- `paper/data/baseline_lambda_sweep.json` — cached `/target` outputs for Figs 3, 4.
- `paper/scripts/make_figures.py` — Python; reads `nous/cache/truth-*.json` and
  `paper/data/*.json`; emits everything reproducibly.
- `paper/main.tex` and `paper/cite.bib` skeletons (placeholder for now; populated
  as other sections are drafted).

**Out of scope for this section:**

- Section text for Background, Motivation, Problem-statement, Algorithm,
  Experimentation.
- Bibliography content (file scaffold only).
- Full paper polish.
