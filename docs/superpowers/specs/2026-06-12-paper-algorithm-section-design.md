# Paper — Algorithm Section Design

**Working title:** *Scaling with Optimal Concurrency* (auto-scaling jointly with concurrency control)
**Section:** Algorithm — *Formula-Guided Onset Search*
**Venue target:** Conference / workshop (e.g. MLSys, SoCC, HotCloud) — reviewer-grade rigor
**Date:** 2026-06-12
**Status:** Approved (design); ready for implementation planning.

---

## 1. Purpose & scope within the paper

The Algorithm section turns the structural facts of the Analysis section into a concrete
procedure. The Analysis section (`paper/sections/analysis.tex`, §\ref{sec:analysis}) ends
by naming four exploited properties and calls the procedure "a downward monotone-predicate
search." This section **is** that procedure: it consumes P1–P4 and delivers the algorithm,
its oracle-call cost, and its guarantees.

It reuses Analysis's established notation — `f(M)`, the *oracle* (one analytic SLO-feasible
rate evaluation), the onset `M*`, the peak `f*`, the tolerance `ε = 2%`, and the closed-form
primitives `M_ITL`, `M_TPF` — so it introduces **no new preliminaries**.

The faithful reference implementation is `nous/harness/strategies/formula_guided.py`
(`EPS = 0.02`, `MAX_ITERS = 6`). The pseudocode in the section mirrors it exactly.

**Properties carried in from Analysis:**

- **P1** Two-phase shape: `f(M)` rises concavely to `M*`, then plateaus → optimisation reduces to onset detection.
- **P2** Closed-form warm start: `M_ITL` exact under `nc=1`; `M_TPF` vs `M_ITL` ordering classifies the regime at zero oracle cost.
- **P3** Monotone-to-plateau: a downward monotone-predicate search anchored at `M_max` converges in `O(log M_max)` calls.
- **P4** Bounded but non-constant occupancy gap → warm-started bounded search, not pure prediction.

## 2. Out of scope

Deferred to the **Experiments / Evaluation** section (separate sub-issue under epic #11),
referenced here via forward `\ref`:

- The full 30-scenario benchmark sweep, the Pareto table, and ablations.
- Quantitative head-to-head numbers for the baselines (naive-max, parameter-blind ternary).
- Real-vLLM-server validation.
- Variable-`nc` closed-form extension and multi-probe `f*` (future work, already flagged in Analysis §\ref{sec:search}).

The section states baselines **qualitatively** (why they fail the concurrency objective) and
defers their measured numbers.

## 3. Section structure

Component-first ordering: present the whole algorithm once, then justify each component
against the P-properties / principles, then state guarantees.

### 3.1 Intro (≈ ½ column)
- Goal: locate the onset `M*` in a handful of oracle calls.
- State the objective inline, anchored on Analysis:
  `M̂ = min{ M : f(M) ≥ (1−ε)·f* }`, with `f*` **probed, not known a priori**.
- One sentence each: pure prediction fails (P4, the non-constant gap); exhaustive search is
  wasteful → motivates *formula-guided* search (closed-form warm start + a short bounded search).

### 3.2 The algorithm (numbered pseudocode float)
A single `algorithm`/`algorithm2e` float, `FormulaGuidedOnsetSearch(params, oracle, m_min, m_max, ε)`,
mirroring `formula_guided.py`:

1. `M_ITL ← largest B with itl(B) ≤ targetITL`; `M_TPF ← largest B with ttft_prefill(B) ≤ targetTTFT` (closed-form, no oracle calls).
2. Cell-aware seed: if `M_TPF < M_ITL` (ttft-only cell) `seed ← m_max`; else `seed ← min(max(M_ITL, M_TPF), m_max)`.
3. Probe `f* ← oracle(seed).throughput`; if infeasible and `seed < m_max`, re-probe at `m_max`; if still infeasible, return `m_max`.
4. `threshold ← (1 − ε/2)·f*`.
5. `lo ← max(m_min, min(M_ITL, M_TPF))`.
6. `hi ← min(seed, m_max)` on ttft-only; else `hi ← min(seed, 3·M_ITL, m_max)`; then `hi ← max(lo, hi)`.
7. Downward binary search on `[lo, hi]` for the smallest `M` with `oracle(M).throughput ≥ threshold`, capped at `MAX_ITERS = 6`. Return `clamp(hi, m_min, m_max)`.

### 3.3 Why each step (design rationale)
Four short paragraphs, each tied to a property/principle:

- **Closed-form seed (P2; RP-1, RP-5, RP-7).** `M_ITL`/`M_TPF` cost zero oracle calls. The
  seed is cell-aware because `M_TPF` *undershoots* the onset on the ttft-only cell (queue
  wait lifts the real TTFT frontier above `M_TPF`), so there we seed at `m_max` instead.
- **High anchor at `f(M_max)` (P4; RP-2).** The load-bearing fix. A seed-at-`U` anchor can
  badly **underestimate** the peak when M/M/1 queue wait lets realised throughput climb far
  above the per-iteration binding batch size. *Concrete motivation:* on bench-023 the
  occupancy gap is **6.3×** (`U = max(M_ITL, M_TPF) = 9` while the plateau peak sits at
  `M ≈ 57`); a `U`-anchored threshold halts the descent at `M = 9` with `gap_f = 0.22`,
  violating `ε`. Anchoring `f*` at `m_max` reads the true plateau height and fixes it.
- **Bracket (P2; RP-2).** `lo = min(M_ITL, M_TPF)` (floors at `M_TPF` on ttft-only where
  `M_ITL` overshoots the onset). `hi` is tightened by the occupancy-gap bound `3·M_ITL`,
  relaxed to `seed` on ttft-only where `M_ITL` is an unreliable tightener.
- **Threshold `(1 − ε/2)` (margin).** Searching to `(1 − ε/2)·f*` leaves headroom so a
  downstream confirmatory evaluation stays within the `ε = 2%` SLO-feasibility tolerance.

### 3.4 Guarantees (prose claims, no proof environment)
Three claims, justified in prose (consistent with Analysis's empirical-plus-structural tone):

1. **Cost.** `≤ 1` (seed) `+ 6` (`MAX_ITERS`) `+ 1` (confirmatory) `= 8` oracle calls; `O(log M_max)` (P3).
2. **Correctness.** Returns `M` with `f(M) ≥ (1 − ε)·f*` given monotone-to-plateau `f` (P3).
   Safe while the post-peak decline `< ε/2` (RP-3); otherwise fall back to a multi-probe `f*`
   (future work).
3. **Onset, not argmax (RP-10).** The search deliberately targets `M*`, not the strict
   throughput argmax, which can sit far higher on a float-wiggly plateau. Over-provisioning
   to the argmax wastes concurrency; targeting the onset is the design intent, and the
   residual `gap_M` against the strict argmax is a structural floor, not a strategy error.

### 3.5 Baselines (qualitative; numbers deferred)
- **Naive-max:** return `M_max`. One oracle call, but over-provisions concurrency (the whole
  point of optimising the onset is to avoid this).
- **Parameter-blind ternary:** maximises `f` over `[m_min, m_max]`, but on a monotone-to-plateau
  curve it converges to the plateau **interior**, not the onset — solving the wrong objective —
  at ~30 oracle calls.

State *why* each fails the concurrency objective; forward-`\ref` the Experiments section for the
measured Pareto comparison.

### 3.6 Provenance (brief methods note, ≈ 3 sentences)
The closed-form primitives, the three-cell regime partition, and the high-anchor fix were
derived through an automated formula-discovery campaign (NOUS, run `queue-throughput-formulas`).
Principles RP-1…RP-11 (`.nous/queue-throughput-formulas/principles.json`) are its recorded,
oracle-validated evidence; the section cites them as the basis for the design choices above.
Honest about provenance, kept short.

## 4. Figure

One **method schematic** (an illustration, not an empirical claim):
a single `f(M)` curve annotated with `M_ITL`, the bracket `[lo, hi]`, the anchor at `f(M_max)`,
and downward-search arrows landing on `M*`.

- Generated reproducibly via `paper/scripts/` like the existing figures.
- **First check `paper/figs/fig4_lower_bound_bracket.pdf`** (and its generator in
  `paper/scripts/make_figures.py`): it may already render the bracket and can be adapted
  rather than duplicated. New filename if a fresh figure is needed (e.g. `fig5_onset_search.pdf`).
- Decision (confirmed): keep the figure in this section.

## 5. Notation & consistency requirements

- Reuse Analysis symbols verbatim: `f(M)`, `M*`, `f*`, `ε`, `M_ITL`, `M_TPF`, `M_max`, oracle.
- `ε = 2%` and `MAX_ITERS = 6` must match `formula_guided.py`.
- The bench-023 figures (`6.3×`, `U = 9`, peak `M ≈ 57`, `gap_f = 0.22`) must match RP-2 /
  `report.md`. Verify against the source before drafting; do not paraphrase numbers from memory.
- Cross-references: `\cite{ramani2026queueing}` for the queueing model; `\ref` to Analysis (P1–P4)
  and forward `\ref` to Experiments.

## 6. Build & verification

- Uncomment `\input{sections/algorithm}` (line 25) in `paper/main.tex`.
- Section must compile cleanly in the full-paper build (`latexmk`), no undefined refs once the
  Experiments label exists (use a placeholder `\ref` guarded so the build still passes, or a
  `\TODO`-style note until Experiments lands).
- If a new figure script is added, it must run under `paper/scripts/.venv` and regenerate the PDF
  deterministically.

## 7. Deliverables

- `paper/sections/algorithm.tex` — the section.
- Figure PDF in `paper/figs/` + generator hook in `paper/scripts/make_figures.py` (new or adapted).
- `paper/main.tex` line 25 uncommented.
- Epic #11 checklist: tick "Algorithm — formula-guided onset search" and link the sub-issue.
- PR against `main`, mirroring the Analysis section's PR #10 flow.
