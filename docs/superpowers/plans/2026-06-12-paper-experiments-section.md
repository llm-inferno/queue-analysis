# Paper — Experiments Section (with v3 algorithm reconciliation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the paper's Experiments section — a minimal, offline-reproducible validation that the formula-guided onset search finds the ε-onset accurately, cheaply, and within the SLO tolerance, Pareto-beating two naive baselines — *after* first reconciling the stale committed algorithm with the validated v3 (universal `m_max` anchor) and correcting the merged Algorithm section.

**Architecture:** Two phases ship as two separate PRs. **Phase 0 (issue #15):** replace the stale iter-4 `formula_guided.py` with the validated v3, add a regression test, and fully reconcile `paper/sections/algorithm.tex` + `fig5` to v3 (high anchor, not cell-dependent seed). **Phase 1–4 (issue #14):** a new offline replay script (`eval_strategies.py`) drives the three committed strategies against the truth caches, emits `eval_results.json`, a comparison table, and a measured search-trace figure; the section prose consumes them.

**Tech Stack:** Python 3.12 (`paper/scripts/.venv`: numpy, matplotlib; `nous/.venv` for harness tests), the pure-stdlib `nous.harness.formulas`/strategies, LaTeX (`latexmk`, `algorithm2e`), pytest.

**Key verified numbers (v3, recomputed this session — re-verify during execution):**
- formula_guided, **25 feasible benchmark**: `calls ≤ 8`, `gap_onset` worst/mean = **38 / 6.80**, `gap_f` worst = **0.0138** (< ε), `gap_argmax` worst = **72**.
- formula_guided, **6 dev**: `calls ≤ 8`, `gap_onset` 18 / 7.33, `gap_f` 0.0101, `gap_argmax` 20.
- naive_ternary, bench: `calls = 30`, `gap_onset` 155 / 69.64, `gap_f` **0.0286 (violates ε)**, `gap_argmax` 145.
- naive_max, bench: `calls = 1`, `gap_onset` 251 / 180.20, `gap_f` **0.0286 (violates ε)**, `gap_argmax` 251.
- 5 infeasible benchmark scenarios (`bench-005,013,022,028,029`): all strategies return `m_min=1`, `gap=0`.
- baseline v3 trace: probes `[256, 148, 94, 67, 53, 60, 64]`, `M_chosen=67`, 2%-onset `=66`, argmax `M_truth=69`, `M_ITL=40`, `M_TPF=147`, peak `1.9232`.
- bench-023 (regression): itl-or-crossover, `M_ITL=7`, `M_TPF=9`, `U=9`, `f(9)=0.0131`, peak `0.0168`, 2%-onset `13`, argmax `57`.

---

## File Structure

**Phase 0 (PR #1, issue #15):**
- Modify: `nous/harness/strategies/formula_guided.py` — replace iter-4 logic with v3.
- Create: `nous/harness/tests/test_formula_guided.py` — regression test pinning the fix.
- Modify: `paper/sections/algorithm.tex` — full reconciliation to v3.
- Modify: `paper/scripts/make_figures.py` — `fig5_onset_search` anchors at `m_max`.
- Regenerate: `paper/figs/fig5_onset_search.pdf`.

**Phase 1–4 (PR #2, issue #14):**
- Create: `paper/scripts/eval_strategies.py` — offline replay → `paper/data/eval_results.json`.
- Create: `paper/scripts/test_eval_strategies.py` — unit + integration tests.
- Modify: `paper/scripts/make_figures.py` — `tab2_eval_comparison()`; re-point `fig5` at the eval trace.
- Create (generated): `paper/tabs/eval_comparison.tex`, `paper/data/eval_results.json`.
- Create: `paper/sections/experiments.tex` — the section (`\label{sec:experiments}`).
- Modify: `paper/main.tex` — uncomment `\input{sections/experiments}`.
- Modify: `paper/README.md` — add `eval_strategies.py` to regenerate steps.

---

# PHASE 0 — Reconcile to v3 (issue #15, separate PR)

### Task 0.0: Branch

- [ ] **Step 1: Create the precursor branch**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git checkout main && git pull --ff-only
git checkout -b fix/v3-onset-search-and-algorithm-section
```

### Task 0.1: Regression test for the v3 fix (TDD — write first, must fail on stale code)

**Files:**
- Test: `nous/harness/tests/test_formula_guided.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# nous/harness/tests/test_formula_guided.py
"""Regression tests pinning the high-anchor (v3) onset search.

The stale iter-4 strategy seeded f* at the constraint endpoint U for the
itl-or-crossover cell and failed bench-023 (U=9 << peak@57), and returned
m_max on fully-infeasible scenarios. These tests fail on that version and
pass on v3 (universal m_max anchor; infeasible -> m_min).
"""
import json
from pathlib import Path

from nous.harness.strategies.formula_guided import search

REPO = Path(__file__).resolve().parents[3]


def _cache_eval(name: str):
    sub = "bench/" if name.startswith("bench-") else ""
    prefix = "" if name.startswith("bench-") else "truth-"
    cache = json.loads((REPO / "nous" / "cache" / f"{sub}{prefix}{name}.json").read_text())
    f = {pt["m"]: pt["throughput"] for pt in cache["f_curve"]}
    return (lambda m: {"throughput": f.get(m, 0.0)}), f


def _params(name: str) -> dict:
    fname = "scenarios_benchmark.json" if name.startswith("bench-") else "scenarios.json"
    scns = json.loads((REPO / "nous" / fname).read_text())["scenarios"]
    s = next(x for x in scns if x["name"] == name)
    keys = ("alpha", "beta", "gamma", "AvgInputTokens", "AvgOutputTokens",
            "targetITL", "targetTTFT", "maxQueueSize")
    return {k: s[k] for k in keys}


def test_bench023_high_anchor_within_epsilon():
    """bench-023 (itl-or-crossover, U=9 undershoots peak@57): the m_max anchor
    must land within EPS=0.02 of the peak. The stale U-seed gives gap_f=0.22."""
    ev, f = _cache_eval("bench-023")
    peak = max(f.values())
    m = search(ev, _params("bench-023"), 1, 256)
    gap_f = (peak - f[m]) / peak
    assert gap_f <= 0.02, f"bench-023 gap_f={gap_f:.4f} exceeds EPS (chose M={m})"


def test_fully_infeasible_returns_m_min():
    """bench-005 is infeasible everywhere (all-zero f); must return m_min=1."""
    ev, _ = _cache_eval("bench-005")
    m = search(ev, _params("bench-005"), 1, 256)
    assert m == 1
```

- [ ] **Step 2: Run the test, verify it FAILS on the stale strategy**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
source nous/.venv/bin/activate
python -m pytest nous/harness/tests/test_formula_guided.py -v
```
Expected: both tests FAIL (`bench-023 gap_f≈0.2238 > 0.02`; infeasible returns `256 != 1`).

### Task 0.2: Replace the strategy with v3

**Files:**
- Modify: `nous/harness/strategies/formula_guided.py` (full replace)

- [ ] **Step 1: Overwrite the strategy file with v3 logic (deliverable docstring)**

```python
"""formula_guided: closed-form-guided downward onset search (high anchor).

Probes f* at m_max -- always on the plateau when f is monotone-to-plateau
(P3) -- then binary-searches downward for the smallest M with
f(M) >= (1-EPS/2)*f*, the plateau onset M*.

Algorithm:
1. Compute M_ITL (largest B with itl(B)<=targetITL) and M_TPF (largest B with
   ttft_prefill(B)<=targetTTFT) from the closed-form formulas (no oracle calls).
2. Anchor f* = target_eval(m_max). The high anchor reads the true plateau
   height; a constraint-endpoint seed U=max(M_ITL,M_TPF) can badly undershoot
   when M/M/1 queue wait lifts realised throughput above the per-iteration
   binding batch size (RP-2; e.g. bench-023 U=9 vs peak@57).
3. If f* <= 0 the scenario is infeasible everywhere; return m_min (the truth
   convention sets M_truth=m_min there).
4. threshold = (1-EPS/2)*f* so the harness confirmatory call stays < EPS=0.02.
5. Bracket: lo = max(m_min, min(M_ITL, M_TPF));
   hi = min(seed, max(3*U, lo+1), m_max) with U=max(M_ITL,M_TPF) (occupancy-gap
   bound RP-2; the lo+1 floor keeps the bracket non-empty when 3U is tiny).
6. Binary search [lo, hi]; cap at MAX_ITERS=6 so worst-case total calls
   (anchor + search + harness-confirmatory) <= 8.
"""

from __future__ import annotations
from typing import Callable

from nous.harness import formulas as F

EPS = 0.02
MAX_ITERS = 6  # anchor(1) + MAX_ITERS(6) + harness-confirmatory(1) = 8


def _largest_feasible(metric, params: dict, target: float) -> int:
    feas = [B for B in range(1, 257) if metric(B, params) <= target]
    return max(feas) if feas else 1


def search(target_eval: Callable[[int], dict], params: dict, m_min: int, m_max: int) -> int:
    M_ITL = _largest_feasible(F.itl, params, params["targetITL"])
    M_TPF = _largest_feasible(F.ttft_prefill, params, params["targetTTFT"])

    seed = m_max
    fstar = target_eval(seed)["throughput"]
    if fstar <= 0.0:
        return m_min  # fully infeasible -> truth convention M_truth = m_min

    threshold = (1.0 - EPS / 2.0) * fstar

    lo = max(m_min, min(M_ITL, M_TPF))
    U = max(M_ITL, M_TPF)
    hi = min(seed, max(3 * U, lo + 1), m_max)
    hi = max(lo, hi)

    iters = 0
    while lo < hi and iters < MAX_ITERS:
        mid = (lo + hi) // 2
        v = target_eval(mid)["throughput"]
        if v >= threshold:
            hi = mid
        else:
            lo = mid + 1
        iters += 1

    return max(m_min, min(m_max, hi))
```

- [ ] **Step 2: Run the regression test, verify it PASSES**

```bash
python -m pytest nous/harness/tests/test_formula_guided.py -v
```
Expected: both tests PASS.

- [ ] **Step 3: Run the full nous suite (no regressions)**

```bash
python -m pytest nous/harness/tests/ -q
```
Expected: all green (the suite had 44 passing; now +2).

- [ ] **Step 4: Commit**

```bash
git add nous/harness/strategies/formula_guided.py nous/harness/tests/test_formula_guided.py
git commit -m "fix: ship validated v3 onset search (high m_max anchor) + regression test

Stale iter-4 strategy seeded f* at constraint endpoint U for the
itl-or-crossover cell and failed bench-023 (gap_f=0.22, violates EPS).
v3 anchors f* at m_max unconditionally and returns m_min on fully
infeasible scenarios. Pins the fix with a bench-023/bench-005 regression.

Refs #15.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 0.3: Reconcile `algorithm.tex` to v3 (full)

**Files:**
- Modify: `paper/sections/algorithm.tex`

- [ ] **Step 1: Replace the algorithm float (the `\begin{algorithm}…\end{algorithm}` block, lines ~22–67) with the v3 procedure**

Replace the body between `\KwOut{...}` and `\Return \FBisect{...}` (i.e. the seed/anchor/bracket lines) with:

```latex
  $M_{\mathrm{ITL}} \leftarrow$ largest $B$ with $\mathrm{itl}(B) \le \mathrm{targetITL}$
    \tcp*{closed form, no oracle calls}
  $M_{\mathrm{TPF}} \leftarrow$ largest $B$ with $\mathrm{ttft\_prefill}(B) \le \mathrm{targetTTFT}$\;
  $\mathit{seed} \leftarrow m_{\max}$ \tcp*{high anchor: $m_{\max}$ lies on the plateau (P3)}
  $f^\ast \leftarrow f(\mathit{seed})$ \tcp*{1 oracle call}
  \lIf{$f^\ast \le 0$}{\Return $m_{\min}$
    \tcp*[f]{infeasible everywhere: truth sets $M^\ast = m_{\min}$}}
  $\theta \leftarrow (1 - \varepsilon/2)\, f^\ast$ \tcp*{margin keeps a confirmatory call $<\varepsilon$}
  $U \leftarrow \max(M_{\mathrm{ITL}}, M_{\mathrm{TPF}})$\;
  $\mathit{lo} \leftarrow \max(m_{\min},\, \min(M_{\mathrm{ITL}}, M_{\mathrm{TPF}}))$\;
  $\mathit{hi} \leftarrow \min(\mathit{seed},\, \max(3U,\, \mathit{lo}+1),\, m_{\max})$
    \tcp*{occupancy-gap bound}
  $\mathit{hi} \leftarrow \max(\mathit{lo}, \mathit{hi})$\;
  \Return \FBisect{$f$, $\theta$, $\mathit{lo}$, $\mathit{hi}$}
    \tcp*{$\mathit{lo},\mathit{hi}\in[m_{\min},m_{\max}]$ by construction}
```

Leave the `\Fn{\FBisect…}` helper and the `\caption{…}` unchanged.

- [ ] **Step 2: Rewrite the "Closed-form classification (P2)" paragraph (≈ lines 72–81) — demote to "bracket", not "seed gate"**

```latex
\paragraph{Closed-form bracket (P2).}
The primitives $M_{\mathrm{ITL}}$ and $M_{\mathrm{TPF}}$ are computed from the service
model alone, at zero oracle cost (\S\ref{sec:mitl}, \S\ref{sec:regimes}). The search does
not use them to choose its seed; it uses them to \emph{bracket} the descent, with
$\mathit{lo} = \min(M_{\mathrm{ITL}}, M_{\mathrm{TPF}})$ and an occupancy-gap-bounded
$\mathit{hi}$. The three-cell regime partition of \S\ref{sec:regimes} remains a structural
property of the deployment, but the procedure reads only these two endpoints and the high
anchor, so its behaviour does not depend on resolving the itl-only/crossover ambiguity that
the primitives alone cannot decide.
```

- [ ] **Step 3: Replace the "Cell-dependent seed (P4)" paragraph (≈ lines 83–96) with the high-anchor rationale**

```latex
\paragraph{High anchor at $f(m_{\max})$ (P4; RP-2).}
The seed must read a \emph{near-peak} $f^\ast$: if it underestimates the peak, the threshold
$\theta$ is set too low and the downward search halts prematurely. We anchor unconditionally
at $m_{\max}$, which lies on the plateau whenever $f$ is monotone-to-plateau (P3), rather than
at a constraint endpoint that can undershoot. The undershoot is neither hypothetical nor
confined to one regime: on benchmark scenario \texttt{bench-023} --- an ITL-or-crossover cell
with $M_{\mathrm{ITL}} = 7$, $M_{\mathrm{TPF}} = 9$ --- the constraint endpoint $U = 9$ reads
$f(9) \approx 0.013$ while the peak $\approx 0.017$ is attained near $M = 57$. A $U$-anchored
threshold would stop the descent around $M = 9$, a $22\%$ throughput shortfall
($\mathrm{gap}_f = 0.22$) that violates $\varepsilon = 2\%$. Anchoring at $m_{\max}$ reads the
true plateau height and removes the failure, at no extra worst-case oracle cost.
```

- [ ] **Step 4: Replace the "Bracket." paragraph (≈ lines 98–103)**

```latex
\paragraph{Bracket.}
The lower end $\mathit{lo} = \min(M_{\mathrm{ITL}}, M_{\mathrm{TPF}})$ floors the search below
the onset on every cell. The upper end is tightened to $\max(3U,\, \mathit{lo}+1)$ --- the
occupancy gap stays within a small factor of the constraint endpoint $U = \max(M_{\mathrm{ITL}},
M_{\mathrm{TPF}})$ on the scenarios studied --- then capped at the seed and $m_{\max}$; the
$\mathit{lo}+1$ floor keeps the bracket non-empty when $3U$ is small.
```

- [ ] **Step 5: Fix the figure-reference sentence + caption (≈ lines 110–125)**

Change the in-text sentence that currently reads "an ITL-or-crossover cell, so $f^\ast$ is read at $U = M_{\mathrm{TPF}} = 147$" and the caption "$f^\ast$ is read at the constraint endpoint $U = M_{\mathrm{TPF}} = 147$" to the high-anchor version:

```latex
Figure~\ref{fig:onset-search} illustrates the procedure on the baseline scenario: the
closed-form markers $M_{\mathrm{ITL}} = 40$ and $M_{\mathrm{TPF}} = 147$ bracket the search,
$f^\ast$ is anchored at $m_{\max} = 256$ (on the plateau), the threshold is set at
$(1-\varepsilon/2)f^\ast$, and the downward probes descend from the bracket $[40, 256]$ toward
the onset.
```

and the caption:

```latex
  \caption{Formula-guided onset search on the baseline scenario. Closed-form
           $M_{\mathrm{ITL}} = 40$ and $M_{\mathrm{TPF}} = 147$ bracket the search; $f^\ast$ is
           anchored at $m_{\max} = 256$, which lies on the plateau, and the threshold is set at
           $(1-\varepsilon/2)f^\ast$; the downward monotone-predicate probes descend toward the
           onset. The measured trace is in \S\ref{sec:experiments}.}
```

- [ ] **Step 6: Update the "Cost" guarantee wording (≈ lines 130–135) — "seed" → "anchor"**

```latex
\paragraph{Cost.}
The procedure issues one anchor probe at $m_{\max}$, then at most $\textsc{MaxIters}=6$ search
probes and one downstream confirmatory call: eight oracle calls in the worst case (RP-8). The
search is $O(\log m_{\max})$ (\textbf{P3}).
```

- [ ] **Step 7: Check the Baselines / Provenance / Correctness prose for stale "seed at $U$ / cell-dependent" phrasing and align to v3**

Read the remaining paragraphs (Correctness ~137–143, Baselines ~152–161, Provenance ~163–173). The Correctness "single high anchor is safe" wording already matches v3 — keep it. Remove any lingering "cell-chosen seed" phrasing. The Provenance RP list is unchanged (RP-1…RP-11 still apply; RP-2 is now the central anchor principle).

- [ ] **Step 8: Commit**

```bash
git add paper/sections/algorithm.tex
git commit -m "docs(paper): reconcile Algorithm section to v3 high-anchor search

Pseudocode now anchors f* at m_max unconditionally (not a cell-dependent
seed), returns m_min on full infeasibility, and brackets hi by max(3U, lo+1).
Demotes P2 from 'classification gates the seed' to 'primitives bracket the
search'; reframes bench-023 as an itl-or-crossover undershoot fixed by the
m_max anchor.

Refs #15, corrects #12.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 0.4: Update `fig5` generator to the v3 bracket + anchor

**Files:**
- Modify: `paper/scripts/make_figures.py` (`fig5_onset_search`, lines ~178–229)

- [ ] **Step 1: Replace the bracket/anchor computation in `fig5_onset_search` to mirror v3**

In `fig5_onset_search()`, replace the block that computes `seed`, `lo`, `hi`, `f_anchor`, `threshold` (the lines after `fig, ax, c = _baseline_fM_axes()` down to the probe-replay loop) with:

```python
    # Bracket exactly as formula_guided.py (v3) computes it.
    seed = M_MAX
    f_anchor = c.f_of[seed]
    threshold = (1.0 - EPS / 2.0) * f_anchor
    lo = max(1, min(c.m_itl, c.m_tpf))
    U = max(c.m_itl, c.m_tpf)
    hi = min(seed, max(3 * U, lo + 1), M_MAX)
    hi = max(lo, hi)

    # Replay the downward binary search to mark the probed midpoints.
    lo_i, hi_i, probes = lo, hi, []
    for _ in range(MAX_ITERS):
        if lo_i >= hi_i:
            break
        mid = (lo_i + hi_i) // 2
        probes.append(mid)
        if c.f_of[mid] >= threshold:
            hi_i = mid
        else:
            lo_i = mid + 1
```

- [ ] **Step 2: Update the anchor annotation text (the `r"anchor $f^*=f(U)$"` line) to `m_max`**

```python
    ax.text(M_MAX * 0.62, f_anchor * 1.01, r"anchor $f^*=f(m_{\max})$",
            color="C3", fontsize=8, va="bottom")
```

- [ ] **Step 3: Regenerate figures and verify fig5 changed**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper/scripts
source .venv/bin/activate
python make_figures.py
```
Expected: prints `done`; `git status` shows `paper/figs/fig5_onset_search.pdf` modified.

- [ ] **Step 4: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/scripts/make_figures.py paper/figs/fig5_onset_search.pdf
git commit -m "fig(paper): fig5 onset search uses v3 m_max anchor + 3U bracket

Refs #15.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 0.5: Build, PR, merge

- [ ] **Step 1: Full-paper build passes**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper
latexmk -pdf main.tex
```
Expected: `main.pdf` builds; no new errors. (`\ref{sec:experiments}` is still undefined here — that is expected until Phase 3; note it but it does not block this PR since the Algorithm section already had that forward-ref before.)

- [ ] **Step 2: Push and open PR**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git push -u origin fix/v3-onset-search-and-algorithm-section
gh pr create --title "Fix: ship v3 onset search + reconcile Algorithm section" \
  --body "Closes #15. Replaces the stale iter-4 \`formula_guided.py\` with the validated v3 (universal m_max anchor; infeasible→m_min), adds a bench-023/bench-005 regression test, and fully reconciles \`algorithm.tex\` + fig5 to v3 (high anchor, not cell-dependent seed; bench-023 reframed as an itl-or-crossover undershoot).

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 3: After review, merge to `main`** (squash, matching prior section PRs). Phase 1 branches off the updated `main`.

---

# PHASE 1 — Offline evaluation script (issue #14)

### Task 1.0: Branch

- [ ] **Step 1: Branch off updated main**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git checkout main && git pull --ff-only
git checkout -b feat/paper-experiments-section
```

### Task 1.1: Cache-backed counted oracle + ε-onset (TDD)

**Files:**
- Create: `paper/scripts/eval_strategies.py`
- Test: `paper/scripts/test_eval_strategies.py`

- [ ] **Step 1: Write failing tests for the two primitives**

```python
# paper/scripts/test_eval_strategies.py
import eval_strategies as E


def test_cache_oracle_counts_only_feasible():
    f_curve = [{"m": 1, "throughput": 0.0}, {"m": 2, "throughput": 5.0},
               {"m": 3, "throughput": 7.0}]
    ev, stats = E.cache_oracle(f_curve)
    assert ev(1) == {"throughput": 0.0}      # infeasible
    assert ev(2) == {"throughput": 5.0}      # feasible
    assert ev(99) == {"throughput": 0.0}     # out of range -> infeasible
    assert stats["calls"] == 1               # only m=2 counted
    assert stats["probes"] == [1, 2, 99]     # every probe recorded


def test_epsilon_onset_smallest_within_two_percent():
    # rises 0,1,2,...,10 then flat 10 -> peak 10, 0.98*10=9.8 first met at m=10
    f_curve = [{"m": m, "throughput": float(min(m, 10))} for m in range(1, 21)]
    assert E.epsilon_onset(f_curve, eps=0.02) == 10


def test_epsilon_onset_infeasible_returns_none():
    f_curve = [{"m": m, "throughput": 0.0} for m in range(1, 6)]
    assert E.epsilon_onset(f_curve, eps=0.02) is None
```

- [ ] **Step 2: Run, verify FAIL**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper/scripts
source .venv/bin/activate
python -m pytest test_eval_strategies.py -v
```
Expected: FAIL (`module eval_strategies not found` / attrs missing).

- [ ] **Step 3: Create `eval_strategies.py` with the two primitives + repo-path bootstrap**

```python
"""Offline replay of the committed onset-search strategies against the truth
caches, for the paper's Experiments section. No Go server: the truth cache is
the analytic oracle tabulated at every M in [1, 256], so a cache lookup IS the
oracle value. Deterministic strategies => exact reproduction of M_chosen/calls.

Outputs paper/data/eval_results.json (per-scenario records + aggregates).
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))  # so `nous` (pure-stdlib formulas/strategies) imports

DATA_DIR = REPO / "paper" / "data"
EPS = 0.02
M_MIN, M_MAX = 1, 256
PARAM_KEYS = ("alpha", "beta", "gamma", "AvgInputTokens", "AvgOutputTokens",
              "targetITL", "targetTTFT", "maxQueueSize")


def cache_oracle(f_curve: list[dict]):
    """Return (target_eval, stats). Mirrors nous/harness/oracle.py: an
    infeasible reading (throughput <= 0) is uncounted; every probe is recorded."""
    f = {pt["m"]: pt["throughput"] for pt in f_curve}
    stats = {"calls": 0, "probes": []}

    def target_eval(m: int) -> dict:
        stats["probes"].append(m)
        thr = f.get(m, 0.0)
        if thr > 0.0:
            stats["calls"] += 1
        return {"throughput": thr}

    return target_eval, stats


def epsilon_onset(f_curve: list[dict], eps: float = EPS):
    """Smallest m with f(m) >= (1-eps)*peak; None if the scenario is infeasible."""
    f = {pt["m"]: pt["throughput"] for pt in f_curve}
    peak = max(f.values())
    if peak <= 0.0:
        return None
    thresh = (1.0 - eps) * peak
    for m in sorted(f):
        if f[m] >= thresh:
            return m
    return max(f)
```

- [ ] **Step 4: Run, verify PASS**

```bash
python -m pytest test_eval_strategies.py -v
```
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/scripts/eval_strategies.py paper/scripts/test_eval_strategies.py
git commit -m "feat(paper): cache-backed oracle + epsilon-onset for offline eval

Refs #14.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 1.2: Replay one strategy on one scenario (TDD)

**Files:**
- Modify: `paper/scripts/eval_strategies.py`
- Modify: `paper/scripts/test_eval_strategies.py`

- [ ] **Step 1: Add failing tests for `replay`**

Append to `test_eval_strategies.py`:

```python
import json
from pathlib import Path
from nous.harness.strategies import formula_guided, naive_max

REPO = Path(__file__).resolve().parents[2]


def _baseline_cache():
    return json.loads((REPO / "nous" / "cache" / "truth-baseline.json").read_text())


def _baseline_params():
    scns = json.loads((REPO / "nous" / "scenarios.json").read_text())["scenarios"]
    s = next(x for x in scns if x["name"] == "baseline")
    return {k: s[k] for k in E.PARAM_KEYS}


def test_replay_naive_max_one_call():
    rec = E.replay(naive_max.search, _baseline_params(), _baseline_cache())
    assert rec["M_chosen"] == E.M_MAX
    assert rec["calls"] == 1                       # confirmatory only
    assert rec["gap_argmax"] == E.M_MAX - rec["M_truth"]


def test_replay_formula_guided_baseline_trace():
    rec = E.replay(formula_guided.search, _baseline_params(), _baseline_cache())
    assert rec["probes"][0] == E.M_MAX             # high anchor
    assert rec["calls"] <= 8
    assert rec["M_chosen"] == 67
    assert rec["M_onset"] == 66
    assert rec["gap_f"] <= 0.02
```

- [ ] **Step 2: Run, verify FAIL** (`E.replay` missing)

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper/scripts && source .venv/bin/activate
python -m pytest test_eval_strategies.py -v
```

- [ ] **Step 3: Implement `replay` in `eval_strategies.py`**

```python
def replay(search, params: dict, cache: dict, m_min: int = M_MIN, m_max: int = M_MAX) -> dict:
    """Run one strategy against one cached scenario; return a scored record.

    Adds one confirmatory oracle(M_chosen) call after the strategy returns,
    matching nous/harness/run.py (so `calls` includes that +1)."""
    f_curve = cache["f_curve"]
    f = {pt["m"]: pt["throughput"] for pt in f_curve}
    M_truth = int(cache["M_truth"])
    f_truth = float(cache["throughput_truth"])
    onset = epsilon_onset(f_curve)
    onset_eff = onset if onset is not None else M_truth

    ev, stats = cache_oracle(f_curve)
    m_chosen = int(search(ev, params, m_min, m_max))
    if not (m_min <= m_chosen <= m_max):
        raise ValueError(f"strategy returned M={m_chosen} outside [{m_min}, {m_max}]")
    thr_chosen = ev(m_chosen)["throughput"]  # confirmatory (counted if feasible)

    gap_f = max((f_truth - thr_chosen) / f_truth, 0.0) if f_truth > 0 else 0.0
    return {
        "M_chosen": m_chosen,
        "calls": stats["calls"],
        "probes": list(stats["probes"]),
        "throughput_chosen": thr_chosen,
        "M_onset": onset_eff,
        "M_truth": M_truth,
        "throughput_truth": f_truth,
        "feasible": f_truth > 0,
        "gap_onset": abs(m_chosen - onset_eff),
        "gap_argmax": abs(m_chosen - M_truth),
        "gap_f": gap_f,
    }
```

- [ ] **Step 4: Run, verify PASS**

```bash
python -m pytest test_eval_strategies.py -v
```
Expected: all PASS (5 + 2 from earlier task).

- [ ] **Step 5: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/scripts/eval_strategies.py paper/scripts/test_eval_strategies.py
git commit -m "feat(paper): per-scenario strategy replay with onset/argmax/f gaps

Refs #14.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 1.3: Evaluate all scenarios, aggregate, write JSON (TDD integration)

**Files:**
- Modify: `paper/scripts/eval_strategies.py`
- Modify: `paper/scripts/test_eval_strategies.py`

- [ ] **Step 1: Add failing integration test reproducing the headline numbers**

Append to `test_eval_strategies.py`:

```python
def test_evaluate_all_reproduces_headline():
    results = E.evaluate_all()
    bench_fg = results["aggregates"]["benchmark"]["formula_guided"]
    assert bench_fg["calls_worst"] <= 8
    assert bench_fg["gap_f_worst"] <= 0.02
    assert bench_fg["gap_argmax_worst"] == 72
    assert bench_fg["gap_onset_worst"] == 38
    # baselines violate epsilon on the benchmark
    assert results["aggregates"]["benchmark"]["naive_max"]["gap_f_worst"] > 0.02
    assert results["aggregates"]["benchmark"]["naive_ternary"]["gap_f_worst"] > 0.02
    # feasible-count invariant
    assert results["aggregates"]["benchmark"]["n_scenarios"] == 25
```

- [ ] **Step 2: Run, verify FAIL** (`E.evaluate_all` missing)

- [ ] **Step 3: Implement `evaluate_all` + `main` in `eval_strategies.py`**

```python
from nous.harness.strategies import formula_guided, naive_max, naive_ternary

STRATEGIES = {
    "formula_guided": formula_guided.search,
    "naive_ternary": naive_ternary.search,
    "naive_max": naive_max.search,
}


def _load_set(scenarios_path: Path, cache_for):
    scns = json.loads(scenarios_path.read_text())["scenarios"]
    out = []
    for s in scns:
        params = {k: s[k] for k in PARAM_KEYS}
        cache = json.loads(cache_for(s["name"]).read_text())
        out.append((s["name"], params, cache))
    return out


def _aggregate(records: list[dict]) -> dict:
    """Worst/mean gaps over the FEASIBLE records only, per strategy."""
    by_strat: dict[str, list[dict]] = {}
    for r in records:
        by_strat.setdefault(r["strategy"], []).append(r)
    agg = {}
    n_feasible = None
    for strat, recs in by_strat.items():
        feas = [r for r in recs if r["feasible"]]
        n_feasible = len(feas)
        agg[strat] = {
            "calls_worst": max(r["calls"] for r in feas),
            "gap_onset_worst": max(r["gap_onset"] for r in feas),
            "gap_onset_mean": round(statistics.mean(r["gap_onset"] for r in feas), 2),
            "gap_f_worst": round(max(r["gap_f"] for r in feas), 4),
            "gap_argmax_worst": max(r["gap_argmax"] for r in feas),
        }
    agg["n_scenarios"] = n_feasible
    return agg


def evaluate_all() -> dict:
    dev = _load_set(REPO / "nous" / "scenarios.json",
                    lambda n: REPO / "nous" / "cache" / f"truth-{n}.json")
    bench = _load_set(REPO / "nous" / "scenarios_benchmark.json",
                      lambda n: REPO / "nous" / "cache" / "bench" / f"{n}.json")

    records = []
    for setname, dataset in (("dev", dev), ("benchmark", bench)):
        for name, params, cache in dataset:
            for strat, search in STRATEGIES.items():
                rec = replay(search, params, cache)
                rec.update(strategy=strat, scenario=name, set=setname,
                           regime=cache.get("regime", ""))
                rec.pop("probes", None)  # keep JSON compact; trace recomputed for the figure
                records.append(rec)

    aggregates = {
        "dev": _aggregate([r for r in records if r["set"] == "dev"]),
        "benchmark": _aggregate([r for r in records if r["set"] == "benchmark"]),
    }
    return {"eps": EPS, "records": records, "aggregates": aggregates}


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = evaluate_all()
    (DATA_DIR / "eval_results.json").write_text(json.dumps(out, indent=2))
    b = out["aggregates"]["benchmark"]["formula_guided"]
    print(f"wrote eval_results.json; formula_guided bench: calls<={b['calls_worst']} "
          f"gap_onset {b['gap_onset_worst']}/{b['gap_onset_mean']} "
          f"gap_f {b['gap_f_worst']} gap_argmax {b['gap_argmax_worst']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run, verify PASS, and generate the data file**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper/scripts && source .venv/bin/activate
python -m pytest test_eval_strategies.py -v
python eval_strategies.py
```
Expected: tests PASS; print line shows `calls<=8 gap_onset 38/6.8 gap_f 0.0138 gap_argmax 72`.

- [ ] **Step 5: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/scripts/eval_strategies.py paper/scripts/test_eval_strategies.py paper/data/eval_results.json
git commit -m "feat(paper): evaluate_all + aggregates -> eval_results.json

Refs #14.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 1.4: Trace helper for the measured figure (TDD)

**Files:**
- Modify: `paper/scripts/eval_strategies.py`
- Modify: `paper/scripts/test_eval_strategies.py`

- [ ] **Step 1: Add failing test for `trace`**

```python
def test_trace_baseline_probes():
    tr = E.trace("formula_guided", "baseline")
    assert tr["probes"] == [256, 148, 94, 67, 53, 60, 64]
    assert tr["seed"] == 256
    assert tr["M_onset"] == 66
    assert tr["M_truth"] == 69
    assert tr["m_itl"] == 40 and tr["m_tpf"] == 147
    assert abs(tr["threshold"] - (1 - E.EPS / 2) * tr["f_anchor"]) < 1e-9
```

- [ ] **Step 2: Run, verify FAIL**

- [ ] **Step 3: Implement `trace`**

```python
from nous.harness import formulas as F


def trace(strategy_name: str, scenario_name: str) -> dict:
    """Replay one strategy on a dev scenario, exposing the measured probe
    sequence + the closed-form markers, for the search-trace figure."""
    scns = json.loads((REPO / "nous" / "scenarios.json").read_text())["scenarios"]
    s = next(x for x in scns if x["name"] == scenario_name)
    params = {k: s[k] for k in PARAM_KEYS}
    cache = json.loads((REPO / "nous" / "cache" / f"truth-{scenario_name}.json").read_text())
    f = {pt["m"]: pt["throughput"] for pt in cache["f_curve"]}

    ev, stats = cache_oracle(cache["f_curve"])
    m_chosen = int(STRATEGIES[strategy_name](ev, params, M_MIN, M_MAX))
    seed = stats["probes"][0]
    f_anchor = f[seed]
    m_itl = max((B for B in range(1, 257) if F.itl(B, params) <= params["targetITL"]), default=1)
    m_tpf = max((B for B in range(1, 257) if F.ttft_prefill(B, params) <= params["targetTTFT"]), default=0)
    return {
        "probes": list(stats["probes"]),
        "M_chosen": m_chosen,
        "seed": seed,
        "f_anchor": f_anchor,
        "threshold": (1.0 - EPS / 2.0) * f_anchor,
        "M_onset": epsilon_onset(cache["f_curve"]),
        "M_truth": int(cache["M_truth"]),
        "m_itl": m_itl,
        "m_tpf": m_tpf,
        "f_of": f,
    }
```

- [ ] **Step 4: Run, verify PASS**

- [ ] **Step 5: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/scripts/eval_strategies.py paper/scripts/test_eval_strategies.py
git commit -m "feat(paper): trace() exposes measured probe sequence for fig5

Refs #14.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

# PHASE 2 — Table + measured figure

### Task 2.1: Comparison-table emitter

**Files:**
- Modify: `paper/scripts/make_figures.py`

- [ ] **Step 1: Add `tab2_eval_comparison()` and call it from `main()`**

Add near `tab1_lower_bound_regime` and register in `main()` (after `tab1_lower_bound_regime()`):

```python
def tab2_eval_comparison():
    """Strategy comparison over the 25 feasible benchmark scenarios.
    Reads paper/data/eval_results.json (run eval_strategies.py first)."""
    res = json.loads((DATA_DIR / "eval_results.json").read_text())
    agg = res["aggregates"]["benchmark"]
    eps = res["eps"]
    display = [("formula_guided", "Formula-guided"),
               ("naive_ternary", "Parameter-blind ternary"),
               ("naive_max", "Naive-max")]
    n = agg["n_scenarios"]
    lines = [
        r"\begin{table}[t]",
        r"  \centering",
        r"  \caption{Onset-search accuracy and cost over the " + str(n) +
        r" feasible benchmark scenarios (worst / mean). $\mathrm{gap}_{\mathrm{onset}}"
        r"=|\hat M - M^\ast|$ is measured against the $\varepsilon$-onset (the objective);"
        r" $\mathrm{gap}_{\mathrm{argmax}}$ against the strict throughput argmax (campaign"
        r" convention; its floor is structural, RP-10). $\mathrm{gap}_f$ is the relative"
        r" throughput shortfall; the SLO tolerance is $\varepsilon=" + f"{eps:.2f}" + r"$."
        r" Only Formula-guided is simultaneously cheap, SLO-feasible, and near-onset.}",
        r"  \label{tab:eval-comparison}",
        r"  \begin{tabular}{lrrrr}",
        r"    \toprule",
        r"    Strategy & calls & $\mathrm{gap}_{\mathrm{onset}}$ (worst/mean) & "
        r"$\mathrm{gap}_f$ (worst) & $\mathrm{gap}_{\mathrm{argmax}}$ (worst) \\",
        r"    \midrule",
    ]
    for key, label in display:
        a = agg[key]
        ok = r"\checkmark" if a["gap_f_worst"] <= eps else r"$\times$"
        lines.append(
            f"    {label} & {a['calls_worst']} & "
            f"{a['gap_onset_worst']}/{a['gap_onset_mean']:.1f} & "
            f"{a['gap_f_worst']:.4f}~{ok} & {a['gap_argmax_worst']} \\\\")
    lines += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}", ""]
    (TAB_DIR / "eval_comparison.tex").write_text("\n".join(lines))
```

- [ ] **Step 2: Regenerate and inspect the table**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper/scripts && source .venv/bin/activate
python eval_strategies.py && python make_figures.py
cat ../tabs/eval_comparison.tex
```
Expected: a 3-row table; Formula-guided row `8 & 38/6.8 & 0.0138 \checkmark & 72`; both baselines show `0.0286 $\times$`.

- [ ] **Step 3: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/scripts/make_figures.py paper/tabs/eval_comparison.tex
git commit -m "feat(paper): eval comparison table emitter (tab:eval-comparison)

Refs #14.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 2.2: Re-point `fig5` at the measured trace (DRY)

**Files:**
- Modify: `paper/scripts/make_figures.py` (`fig5_onset_search`)

- [ ] **Step 1: Replace the hand-rolled replay in `fig5_onset_search` with a call to `eval_strategies.trace`**

At the top of `make_figures.py` add `import eval_strategies as EV`. Then in `fig5_onset_search`, replace the bracket/probe computation (the block from `seed = M_MAX` through the probe-replay loop added in Phase 0) with:

```python
    tr = EV.trace("formula_guided", "baseline")
    seed, probes = tr["seed"], tr["probes"]
    f_anchor, threshold = tr["f_anchor"], tr["threshold"]
    lo = max(1, min(c.m_itl, c.m_tpf))
    U = max(c.m_itl, c.m_tpf)
    hi = min(seed, max(3 * U, lo + 1), M_MAX)
```

Keep the rest of the drawing (axvspan, anchor/threshold lines, markers at `c.f_of[mid]` for `mid in probes`, legend) unchanged. Probes are now the measured sequence from the strategy itself.

- [ ] **Step 2: Update the fig5 docstring/caption note from "Illustrative" to measured**

Change the `fig5_onset_search` docstring first line to:
```python
    """Measured search trace: the actual probes formula_guided issues on the
    baseline scenario (replayed via eval_strategies.trace), over the true f(M)."""
```

- [ ] **Step 3: Regenerate and verify**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper/scripts && source .venv/bin/activate
python make_figures.py
```
Expected: `done`; `fig5_onset_search.pdf` modified; probe markers at M = 148, 94, 67, 53, 60, 64.

- [ ] **Step 4: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/scripts/make_figures.py paper/figs/fig5_onset_search.pdf
git commit -m "fig(paper): fig5 sourced from measured strategy trace (single code path)

Refs #14.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 2.3: Sanity gate vs report.md

- [ ] **Step 1: Confirm regenerated numbers match the campaign report within rounding**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
python3 -c "import json; a=json.load(open('paper/data/eval_results.json'))['aggregates']['benchmark']['formula_guided']; print(a)"
```
Expected: `gap_f_worst≈0.0138`, `calls_worst=8`, `gap_argmax_worst=72`, `gap_onset_worst=38`. If any disagrees with `report.md` (0.0138 / 8 / 72) beyond rounding, STOP and investigate before writing prose — the script is the paper's source of truth, so a mismatch means either the cache or the strategy changed.

---

# PHASE 3 — Section prose, wiring, build

### Task 3.1: Write `experiments.tex`

**Files:**
- Create: `paper/sections/experiments.tex`

- [ ] **Step 1: Write the section** (numbers below are the expected regenerated values; reconcile against `eval_results.json` before finalizing)

```latex
\section{Experiments}
\label{sec:experiments}

We validate the formula-guided onset search of \S\ref{sec:algorithm} and demonstrate it on a
worked scenario. These are \emph{numerical} experiments: they evaluate the algorithm against
the analytic queueing model of Ramani and Tantawi~\cite{ramani2026queueing} --- the same oracle
used throughout the paper --- not a live server. Their role is exploration and validation. The
substantive comparative study --- the end-to-end benefit of capping \emph{concurrency} (serving
at the onset $M^\ast$) against other admission or rate-limiting schemes on a real deployment ---
is future work (\S\ref{sec:exp-threats}).

\subsection{Setup}
\label{sec:exp-setup}
One \emph{oracle} call is one analytic SLO-feasible-rate evaluation $f(M)$ (\S\ref{sec:analysis}).
We evaluate on the six development scenarios spanning the four regimes and on a $30$-scenario
benchmark drawn by Latin-hypercube sampling (seed $42$) over the service- and workload-parameter
ranges; $25$ are feasible and $5$ are infeasible at every $M$ (all-zero $f$ curves), on which a
correct strategy returns $m_{\min}$. For every scenario we precompute a \emph{truth cache}: the
oracle evaluated at all $M\in[1,256]$, giving the ground-truth curve, the strict argmax
$M_{\mathrm{truth}}$, and the peak. The $\varepsilon$-onset $M^\ast$ is the smallest $M$ with
$f(M)\ge(1-\varepsilon)\max_M f(M)$, $\varepsilon=0.02$.\footnote{The Analysis and Algorithm
sections tabulate $M^\ast$ as $M_{\mathrm{truth}}$ (the strict argmax) where the two coincide to
floating point; the genuine $\varepsilon$-onset can sit a few steps below (baseline: $66$ vs
$69$) and far below on float-wiggly benchmark plateaus --- precisely why we report both gaps.}
Because the cache is the oracle tabulated at every $M$ and the strategies are deterministic, we
\emph{replay} the three committed strategies offline against the caches with a counted,
cache-backed oracle (no server); call counts and chosen $M$ reproduce a live run exactly. As in
the harness, one confirmatory $f(\hat M)$ call follows each strategy, so reported call counts
include that $+1$.

\subsection{Onset accuracy and cost}
\label{sec:exp-accuracy}
Table~\ref{tab:eval-comparison} compares the formula-guided search against the two baselines of
\S\ref{sec:algo-baselines} on the feasible benchmark. We report $\mathrm{gap}_{\mathrm{onset}}
=|\hat M - M^\ast|$ against the $\varepsilon$-onset --- the quantity the algorithm optimises ---
and, for continuity with the discovery campaign, $\mathrm{gap}_{\mathrm{argmax}}=|\hat M -
M_{\mathrm{truth}}|$ against the strict argmax. Formula-guided is the only strategy that is at
once \emph{cheap} ($\le 8$ oracle calls), \emph{SLO-feasible} (worst $\mathrm{gap}_f=0.0138<
\varepsilon$), and \emph{near-onset} (worst $\mathrm{gap}_{\mathrm{onset}}=38$, mean $6.8$). The
naive-max heuristic spends a single call but over-provisions massively (mean
$\mathrm{gap}_{\mathrm{onset}}=180$) and even violates the latency tolerance on an interior-peak
scenario ($\mathrm{gap}_f=0.0286$); parameter-blind ternary spends $30$ calls to converge to the
plateau interior, also violating the tolerance and landing far from the onset. Formula-guided
thus Pareto-dominates both on $(\text{calls},\,\mathrm{gap}_{\mathrm{onset}})$ subject to
$\mathrm{gap}_f\le\varepsilon$. The six development scenarios corroborate (worst
$\mathrm{gap}_f=0.0101$, $\le 8$ calls).

\input{tabs/eval_comparison}

The residual $\mathrm{gap}_{\mathrm{argmax}}$ (worst $72$) is dominated by the structural
argmax-vs-onset divergence (\S\ref{sec:search}, RP-10): on float-wiggly plateaus the strict
argmax sits far above the onset (one scenario: argmax $118$ vs onset $\approx 46$), so most of
that gap is not search error but the deliberate choice to stop at the onset rather than
over-provision to the argmax.

\subsection{A measured search trace}
\label{sec:exp-trace}
Figure~\ref{fig:onset-search} shows the procedure as actually executed on the baseline scenario:
$f^\ast$ anchored at $m_{\max}=256$, the threshold at $(1-\varepsilon/2)f^\ast$, and the
downward monotone-predicate probes $\{148,94,67,53,60,64\}$ descending from the bracket
$[40,256]$ to $\hat M=67$, one step above the onset $M^\ast=66$ --- eight oracle calls including
the anchor and the confirmatory evaluation.

\subsection{Scope and threats to validity}
\label{sec:exp-threats}
The oracle is the analytic model, not a live server: results inherit its Markovian-arrival and
three-parameter service assumptions, and a real vLLM deployment adds stochastic token lengths,
KV-cache eviction, and chunked prefill that can break the $nc=1$ regime or the M/M/1 wait model.
Calibrating the primitives $\mathrm{itl}(B)$, $\mathrm{ttft\_prefill}(B)$ against measured vLLM
is the headline next step. The exact closed-form $M_{\mathrm{ITL}}$ holds under $nc=1$ (all dev
scenarios; most of the benchmark); under chunk-count jumps the warm start can err by a step
(\S\ref{sec:mitl}). Finally, the evaluation establishes that the algorithm \emph{finds} the
near-minimal SLO-feasible concurrency; quantifying the operational \emph{benefit} of serving
there, versus alternative limiting schemes, is the comparative study left to future work.
```

- [ ] **Step 2: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/sections/experiments.tex
git commit -m "docs(paper): write Experiments section (validate + demonstrate)

Refs #14.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 3.2: Wire into the paper + README

**Files:**
- Modify: `paper/main.tex`
- Modify: `paper/README.md`

- [ ] **Step 1: Uncomment the Experiments input in `main.tex`**

Change `% \input{sections/experiments}` to `\input{sections/experiments}` (it sits after `\input{sections/algorithm}`).

- [ ] **Step 2: Add the eval step to README regenerate instructions**

In `paper/README.md`, in the "Regenerate figures and tables" block, add before `python make_figures.py`:
```bash
python eval_strategies.py         # replays strategies vs caches -> paper/data/eval_results.json
```

- [ ] **Step 3: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/main.tex paper/README.md
git commit -m "docs(paper): include Experiments section + README regen step

Refs #14.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 3.3: Full build, verify no undefined refs

- [ ] **Step 1: Clean build**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper
latexmk -C && latexmk -pdf main.tex
```
Expected: `main.pdf` builds. Grep the log for unresolved references:
```bash
grep -iE "undefined (reference|citation)|Rerun|multiply defined" main.log || echo "no ref warnings"
```
Expected: `no ref warnings` (the `\ref{sec:experiments}` from Analysis/Algorithm now resolves; `\ref{tab:eval-comparison}` and `\ref{fig:onset-search}` resolve).

- [ ] **Step 2: Eyeball the PDF** — confirm the Experiments section renders with the table and the measured fig5, and that the Algorithm-section fig5 caption matches (single shared figure).

- [ ] **Step 3: Commit any build artifacts the repo tracks** (match existing convention — the repo currently tracks `main.pdf`/`main.bbl`):

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/main.pdf paper/main.bbl 2>/dev/null; git commit -m "build(paper): rebuild with Experiments section

Refs #14.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>" || echo "nothing to commit"
```

---

# PHASE 4 — Finalize

### Task 4.1: Epic checklist + PR

- [ ] **Step 1: Tick the epic #11 checklist** — edit issue #11 body, change `- [ ] Experiments / Evaluation` to `- [x] Experiments / Evaluation (#14)`:

```bash
gh issue view 11 --json body -q .body > /tmp/epic11.md
# edit /tmp/epic11.md: tick the Experiments line, then:
gh issue edit 11 --body-file /tmp/epic11.md
```

- [ ] **Step 2: Run the full paper-scripts test suite once more**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper/scripts && source .venv/bin/activate
python -m pytest -q
```
Expected: all green.

- [ ] **Step 3: Push and open PR**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git push -u origin feat/paper-experiments-section
gh pr create --title "Paper: Experiments section — validate & demonstrate the onset search" \
  --body "Closes #14. Adds the Experiments section: an offline-reproducible replay (\`eval_strategies.py\`) of the three committed strategies against the truth caches, a comparison table (lead with gap_onset; report gap_argmax for continuity), and a measured onset-search trace (fig5). Formula-guided Pareto-dominates both baselines on (calls, gap_onset) at gap_f ≤ ε. Depends on #15 (v3 reconciliation), merged first.

🤖 Generated with [Claude Code](https://claude.com/claude-code)" \
  --base main
```

- [ ] **Step 4: After merge**, update the campaign-status memory note (v3 now committed on main; #14/#15 closed).

---

## Self-Review (completed during planning)

- **Spec coverage:** §1 purpose → Tasks 3.1/3.2; §3.1 setup → 3.1; §3.2 table → 2.1/3.1; §3.3 trace → 1.4/2.2/3.1; §3.4 threats → 3.1; §4 reproducibility → 1.1–1.4; §6 build → 3.3. The spec assumed the committed strategy was correct; Phase 0 (issue #15) was added after discovering the stale-v3/algorithm-section inconsistency — a superset of the spec, agreed with the user.
- **Placeholder scan:** none — all code blocks are complete; the section prose carries the actual regenerated numbers with a verification gate (Task 2.3) before finalizing.
- **Type/name consistency:** `cache_oracle`→`(target_eval, stats)` with `stats["calls"]`/`stats["probes"]`; `epsilon_onset`→int|None; `replay`→record dict; `trace`→dict with `probes/seed/f_anchor/threshold/M_onset/M_truth/m_itl/m_tpf/f_of`; `evaluate_all`→`{eps,records,aggregates}`; aggregate keys `calls_worst/gap_onset_worst/gap_onset_mean/gap_f_worst/gap_argmax_worst/n_scenarios` used identically in `tab2_eval_comparison`. Strategy display names match `\S\ref{sec:algo-baselines}`.
