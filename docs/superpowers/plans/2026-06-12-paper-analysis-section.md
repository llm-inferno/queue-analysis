# Paper Analysis Section Implementation Plan (revised)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a reviewer-ready Analysis section for *Scaling with Optimal Concurrency*, grounded in the NOUS reformulation campaign's principles: section text (§5.1–5.6) in TeX, four PDF figures, one TeX table, a reusable figure-generation script, and a regenerated `/target` sweep coherent with the current analyzer.

**Architecture:** Empirical-first, derivation-grounded. The paper skeleton (`paper/main.tex`, `paper/sections/analysis.tex` stub, `.gitignore`, `README.md`) already exists from the prior skeleton commit. This plan (1) regenerates the stale `/target` sweep against the current Go analyzer and 6-scenario `scenarios.json`, (2) builds a single `make_figures.py` that reads truth caches + the sweep and computes the closed-form `M_ITL`/`M_TPF` from vendored, parity-checked primitives, (3) emits Figs 1–4 and Tab 1, then (4) drafts the section subsection-by-subsection.

**Tech Stack:** LaTeX (article class) + `latexmk`; Python 3 (`matplotlib`, `numpy`, `requests`, `pytest`) in `paper/scripts/.venv`; the Go `queue-analysis` REST server (`go run main.go`, `:8080`) for the sweep.

**Source documents:**
- Spec: `docs/superpowers/specs/2026-06-12-paper-analysis-section-design.md`
- Campaign report/handoff/principles: `.nous/queue-throughput-formulas/{report.md,handoff.md,principles.json}`
- Truth caches: `nous/cache/truth-{baseline,itl-only,ttft-only,unbounded,alpha-low,alpha-high}.json`
- Scenarios: `nous/scenarios.json` (object: `{search_range, scenarios:[…]}`)
- Primitives (source of truth): `nous/harness/formulas.py`, parity of `pkg/analyzer/queueanalyzer.go:275-327`, `pkg/analyzer/utils.go:8-47`
- Analytic paper (local, gitignored): `docs/references/LLM-inference-serving-modeling-and-analysis.pdf` (Ramani & Tantawi)
- `/target` request/response struct: `pkg/service/analyzer.go:1-40` (json tags) and handler `:118-165`

---

## Reference data (verified at planning time)

These values are computed from the ported closed forms and **must** match what the
implemented script produces (parity gate in Task 2). They also seed the table prose.

| Scenario   | regime (runtime) | `M_ITL` | `M_TPF` | `M*`(=`M_truth`) | `f*` [RPS] | gap `M*/M_ITL` |
| ---------- | ---------------- | ------- | ------- | ---------------- | ---------- | -------------- |
| baseline   | crossover        | 40      | 147     | 69               | 1.9232237  | 1.73×          |
| itl-only   | itl-only         | 8       | 256     | 17               | 0.1261…    | 2.13×          |
| ttft-only  | ttft-only        | 95      | 70      | 92               | 4.5230…    | 0.97×          |
| unbounded  | unbounded        | 256     | 256     | 256              | 121.4636…  | 1.00×          |
| alpha-low  | crossover        | 107     | 256     | 170              | 5.1730…    | 1.59×          |
| alpha-high | crossover        | 6       | 45      | 17               | 0.2797…    | 2.83×          |

Regime classifier (RP-6/RP-7): `itl_binds = itl(m_max) > targetITL`;
`ttft_binds = ttft_prefill(m_max) > targetTTFT`. Then:
`unbounded` if not `itl_binds` and not `ttft_binds`; else `ttft-only` if `M_TPF < M_ITL`;
else `itl-or-crossover`.

---

## File structure

```
paper/
├── main.tex                              # EXISTS — driver
├── cite.bib                              # EXISTS (stub) — add Ramani–Tantawi entry
├── .gitignore  README.md                 # EXIST
├── sections/analysis.tex                 # EXISTS (stub) — fill §5.1–5.6
├── figs/  fig1..4_*.pdf                   # NEW (generated)
├── tabs/  lower_bound_regime.tex          # NEW (generated)
├── data/  baseline_lambda_sweep.json      # REGENERATE (overwrite stale)
└── scripts/
    ├── requirements.txt                   # EXISTS — add pytest
    ├── sweep_baseline.py                  # REWRITE (new scenarios.json + camelCase)
    ├── primitives.py                      # NEW — vendored closed forms
    ├── test_primitives.py                 # NEW — parity gate
    └── make_figures.py                    # NEW — figs + table
```

`primitives.py` is split from `make_figures.py` so the closed forms can be unit-tested
in isolation and imported by both the figure script and the table builder.

---

## Phase 1 — Regenerate the `/target` sweep

### Task 1: Rewrite `sweep_baseline.py` and regenerate the baseline λ\* sweep

**Files:**
- Modify: `paper/scripts/requirements.txt`
- Rewrite: `paper/scripts/sweep_baseline.py`
- Regenerate (output): `paper/data/baseline_lambda_sweep.json`

**Why:** The committed sweep is stale (peaks at 2.26 RPS @ M≈42; the current baseline
truth peaks at 1.923 @ M=69) and was written for the old flat-list `scenarios.json` with
PascalCase fields. Rewrite for the current object-shaped `scenarios.json` and camelCase
`/target` fields, then regenerate so Figs 3–4 are coherent with the truth caches.

- [ ] **Step 1: Add `pytest` to `paper/scripts/requirements.txt`**

Final contents:

```
matplotlib>=3.8
numpy>=1.26
requests>=2.31
pytest>=8.0
```

- [ ] **Step 2: Rewrite `paper/scripts/sweep_baseline.py`**

```python
"""One-shot /target sweep over M in [1, 256] for the baseline scenario.

Caches RPSTargetTTFT, RPSTargetITL, throughput per M to
paper/data/baseline_lambda_sweep.json so figure scripts run without
hitting the analyzer. Requires the queue-analysis Go server on :8080
(`go run main.go` from the repo root).

scenarios.json is an object {search_range, scenarios:[...]}; /target uses
camelCase request/response fields (see pkg/service/analyzer.go).
"""
import json
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
SCN = json.loads((REPO / "nous" / "scenarios.json").read_text())
OUT = REPO / "paper" / "data" / "baseline_lambda_sweep.json"
URL = "http://localhost:8080/target"
M_MIN, M_MAX = 1, 256


def main() -> int:
    baseline = next(s for s in SCN["scenarios"] if s["name"] == "baseline")
    base_payload = {
        "avgInputTokens": baseline["AvgInputTokens"],
        "avgOutputTokens": baseline["AvgOutputTokens"],
        "alpha": baseline["alpha"],
        "beta": baseline["beta"],
        "gamma": baseline["gamma"],
        "maxQueueSize": baseline["maxQueueSize"],
        "targetTTFT": baseline["targetTTFT"],
        "targetITL": baseline["targetITL"],
    }

    rows = []
    for m in range(M_MIN, M_MAX + 1):
        payload = dict(base_payload, maxBatchSize=m)
        r = requests.post(URL, json=payload, timeout=30)
        if r.status_code == 400:
            rows.append({"m": m, "infeasible": True})
            continue
        r.raise_for_status()
        body = r.json()
        for key in ("throughput", "RPSTargetTTFT", "RPSTargetITL"):
            if body.get(key) is None:
                raise RuntimeError(f"M={m}: /target response missing '{key}': {body}")
        rows.append({
            "m": m,
            "infeasible": False,
            "throughput": body["throughput"],
            "RPSTargetTTFT": body["RPSTargetTTFT"],
            "RPSTargetITL": body["RPSTargetITL"],
        })
        if m % 32 == 0:
            print(f"  M={m}: lam_TTFT={body['RPSTargetTTFT']:.4f}  "
                  f"lam_ITL={body['RPSTargetITL']:.4f}  f={body['throughput']:.4f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"scenario": "baseline", "rows": rows}, indent=2))
    print(f"\nWrote {len(rows)} rows to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Ensure the venv and deps**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper/scripts
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
Expected: matplotlib, numpy, requests, pytest installed (no errors).

- [ ] **Step 4: Start the Go server**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
go run main.go &
sleep 3
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8080/target \
  -H 'Content-Type: application/json' \
  -d '{"maxBatchSize":40,"avgInputTokens":256,"avgOutputTokens":1024,"alpha":8.0,"beta":0.033,"gamma":0.000333,"maxQueueSize":128,"targetTTFT":60.0,"targetITL":20.0}'
```
Expected: prints `200`. (If `go run` is slow to bind, increase the sleep.)

- [ ] **Step 5: Run the sweep**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper/scripts
source .venv/bin/activate
python sweep_baseline.py
```
Expected: progress every 32 M; ends "Wrote 256 rows …". M=1 may be infeasible.

- [ ] **Step 6: Verify coherence with the truth cache (critical gate)**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
python3 -c "
import json
sw=json.load(open('paper/data/baseline_lambda_sweep.json'))['rows']
t=json.load(open('nous/cache/truth-baseline.json'))
feas={r['m']: min(r['RPSTargetTTFT'], r['RPSTargetITL']) for r in sw if not r['infeasible']}
fc={p['m']: p['throughput'] for p in t['f_curve']}
mstar=t['M_truth']; fstar=t['throughput_truth']
print('truth  M*=%d f*=%.4f' % (mstar, fstar))
print('sweep  min(lam) @M* = %.4f   (should ~= f*)' % feas[mstar])
print('sweep  min(lam) peak = %.4f' % max(feas.values()))
assert abs(feas[mstar] - fstar) / fstar < 0.02, 'sweep min(lambda) at M* disagrees with truth f* by >2%'
print('OK: sweep is coherent with truth cache')
"
```
Expected: prints `OK: sweep is coherent…`. If the assert fails, the server/scenario
params are wrong — do NOT proceed; re-check the payload field mapping in Step 2.

- [ ] **Step 7: Stop the server**

```bash
pkill -f "go run main.go" ; pkill -f "exe/main" 2>/dev/null ; true
```

- [ ] **Step 8: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/scripts/requirements.txt paper/scripts/sweep_baseline.py paper/data/baseline_lambda_sweep.json
git commit -m "paper: regenerate /target sweep for current analyzer + 6-scenario set"
```

---

## Phase 2 — Closed-form primitives (tested) + figure scaffold

### Task 2: Vendor the closed-form primitives with a parity test

**Files:**
- Create: `paper/scripts/primitives.py`
- Create: `paper/scripts/test_primitives.py`

**Why:** Tab 1 and Fig 4 need `M_ITL`, `M_TPF`, and the regime label. These come from
the analytic primitives (`nous/harness/formulas.py`). We vendor a minimal copy so the
paper regenerates from its own venv without importing the nous package, and we gate it
with a parity test against the known values (RP-1).

- [ ] **Step 1: Write the failing test `paper/scripts/test_primitives.py`**

```python
"""Parity gate: vendored primitives must reproduce the campaign's M_ITL/M_TPF
and the regime classification for all six scenarios (RP-1, RP-6, RP-7)."""
import json
from pathlib import Path

import primitives as P

REPO = Path(__file__).resolve().parents[2]
SCN = {s["name"]: s for s in
       json.loads((REPO / "nous" / "scenarios.json").read_text())["scenarios"]}

EXPECTED = {
    # name:        (M_ITL, M_TPF, regime)
    "baseline":   (40, 147, "crossover"),
    "itl-only":   (8, 256, "itl-or-crossover"),
    "ttft-only":  (95, 70, "ttft-only"),
    "unbounded":  (256, 256, "unbounded"),
    "alpha-low":  (107, 256, "crossover"),
    "alpha-high": (6, 45, "crossover"),
}


def test_m_itl_m_tpf_regime():
    for name, (m_itl, m_tpf, regime_family) in EXPECTED.items():
        p = SCN[name]
        assert P.m_itl(p, 256) == m_itl, f"{name}: M_ITL"
        assert P.m_tpf(p, 256) == m_tpf, f"{name}: M_TPF"
        cell = P.regime_cell(p, 256)
        # itl-only and crossover share the same primitive cell (RP-6)
        if regime_family in ("crossover", "itl-or-crossover"):
            assert cell == "itl-or-crossover", f"{name}: cell {cell}"
        else:
            assert cell == regime_family, f"{name}: cell {cell}"


def test_nc_is_one_on_dev_set():
    for name, p in SCN.items():
        assert P.num_iterations_per_prefill(256, p) == 1, f"{name}: nc(256)"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper/scripts
source .venv/bin/activate
pytest test_primitives.py -q
```
Expected: FAIL with `ModuleNotFoundError: No module named 'primitives'`.

- [ ] **Step 3: Write `paper/scripts/primitives.py`**

```python
"""Analytic service-time primitives — vendored, parity-checked port of
nous/harness/formulas.py (itself a port of pkg/analyzer/queueanalyzer.go:275-327
and pkg/analyzer/utils.go:8-47). Self-contained so paper figures regenerate from
the paper venv alone. Verified against RP-1 by test_primitives.py.

`params` is a scenario dict with keys: alpha, beta, gamma, AvgInputTokens,
AvgOutputTokens, targetITL, targetTTFT, maxQueueSize.
"""
from __future__ import annotations

import math

MAX_NUM_TOKENS = 8192  # analyzer.DefaultMaxNumTokens


def _max_batch_for_iters(num_iters: int, n_in: float, m_out: float) -> int:
    m = float(num_iters)
    batch = (m + m_out) * (MAX_NUM_TOKENS - n_in / m) / (n_in + m_out)
    return int(math.floor(max(0.0, batch)))


def num_iterations_per_prefill(B: int, params: dict) -> int:
    n_in = float(params["AvgInputTokens"])
    m_out = float(params["AvgOutputTokens"])
    sizes, batch, k = [], 0, 1
    while batch < B:
        batch = _max_batch_for_iters(k, n_in, m_out)
        sizes.append(batch)
        k += 1
    for i, bs in enumerate(sizes):
        if bs >= B:
            return i + 1
    return len(sizes)


def _w_prefill(nc: int, params: dict) -> float:
    n = float(params["AvgInputTokens"])
    return (params["beta"] + params["gamma"] * (nc + 1) / 2.0) * n


def _w_decode(params: dict) -> float:
    n = float(params["AvgInputTokens"])
    m = float(params["AvgOutputTokens"])
    return params["beta"] * m + params["gamma"] * m * (n + (m + 1) / 2.0)


def delta(B: int, params: dict) -> float:
    nc = num_iterations_per_prefill(B, params)
    m = float(params["AvgOutputTokens"])
    return (_w_prefill(nc, params) + _w_decode(params)) / (nc + m)


def _bg(B: int, params: dict) -> float:
    return max(0.0, params["alpha"] + (B - 1) * delta(B, params))


def itl(B: int, params: dict) -> float:
    n = float(params["AvgInputTokens"])
    m = float(params["AvgOutputTokens"])
    return _bg(B, params) + params["beta"] + params["gamma"] * (n + (m + 1) / 2.0)


def ttft_prefill(B: int, params: dict) -> float:
    nc = num_iterations_per_prefill(B, params)
    return nc * _bg(B, params) + _w_prefill(nc, params)


def m_itl(params: dict, m_max: int) -> int:
    """Closed-form ITL-binding batch size (exact under nc=1; RP-1)."""
    d = delta(1, params)
    raw = math.floor(1 + (params["targetITL"] - itl(1, params)) / d)
    return max(1, min(m_max, raw))


def m_tpf(params: dict, m_max: int) -> int:
    """Largest B with ttft_prefill(B) <= targetTTFT (0 if none)."""
    feasible = [B for B in range(1, m_max + 1)
                if ttft_prefill(B, params) <= params["targetTTFT"]]
    return max(feasible) if feasible else 0


def regime_cell(params: dict, m_max: int) -> str:
    """Primitive-decidable 3-cell partition (RP-6, RP-7)."""
    itl_binds = itl(m_max, params) > params["targetITL"]
    ttft_binds = ttft_prefill(m_max, params) > params["targetTTFT"]
    if not itl_binds and not ttft_binds:
        return "unbounded"
    if m_tpf(params, m_max) < m_itl(params, m_max):
        return "ttft-only"
    return "itl-or-crossover"
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest test_primitives.py -q
```
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/scripts/primitives.py paper/scripts/test_primitives.py
git commit -m "paper: vendored closed-form primitives (M_ITL/M_TPF/regime) with parity test"
```

---

### Task 3: Scaffold `make_figures.py`

**Files:**
- Create: `paper/scripts/make_figures.py`

- [ ] **Step 1: Write the scaffold**

```python
"""Generates all paper figures and tables from cached data.

Sources:
  - nous/cache/truth-<scenario>.json  (f_curve, M_truth, throughput_truth, regime)
  - paper/data/baseline_lambda_sweep.json
  - paper/scripts/primitives.py        (M_ITL, M_TPF, regime)
Outputs:
  - paper/figs/fig{1..4}_*.pdf
  - paper/tabs/lower_bound_regime.tex
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import primitives as P

REPO = Path(__file__).resolve().parents[2]
TRUTH_DIR = REPO / "nous" / "cache"
DATA_DIR = REPO / "paper" / "data"
FIG_DIR = REPO / "paper" / "figs"
TAB_DIR = REPO / "paper" / "tabs"
M_MAX = 256

# Display order, grouped by regime; baseline first (headline).
SCENARIOS = ["baseline", "alpha-low", "alpha-high", "itl-only", "ttft-only", "unbounded"]
SCN_PARAMS = {s["name"]: s for s in
              json.loads((REPO / "nous" / "scenarios.json").read_text())["scenarios"]}
REGIME_COLOR = {"crossover": "C0", "itl-only": "C2", "ttft-only": "C1", "unbounded": "C3"}


def load_truth(name: str) -> dict:
    return json.loads((TRUTH_DIR / f"truth-{name}.json").read_text())


def load_baseline_sweep() -> dict:
    return json.loads((DATA_DIR / "baseline_lambda_sweep.json").read_text())


def setup_style() -> None:
    plt.rcParams.update({
        "font.size": 10, "axes.labelsize": 11, "axes.titlesize": 11,
        "legend.fontsize": 9, "lines.linewidth": 1.6,
        "figure.dpi": 150, "savefig.bbox": "tight",
    })


def main() -> None:
    setup_style()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    TAB_DIR.mkdir(parents=True, exist_ok=True)
    fig1_baseline_fM()
    fig2_overlay_fM()
    fig3_min_constraints()
    fig4_lower_bound_bracket()
    tab1_lower_bound_regime()
    print("done")


# Stubs — implemented in subsequent tasks.
def fig1_baseline_fM(): pass
def fig2_overlay_fM(): pass
def fig3_min_constraints(): pass
def fig4_lower_bound_bracket(): pass
def tab1_lower_bound_regime(): pass


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it imports and runs cleanly**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper/scripts
source .venv/bin/activate
python make_figures.py
```
Expected: prints `done`; no errors.

- [ ] **Step 3: Commit**

```bash
git add paper/scripts/make_figures.py
git commit -m "paper: scaffold figure-generation script"
```

---

## Phase 3 — Figures and table

### Task 4: Fig 1 — headline f(M), baseline

**Files:**
- Modify: `paper/scripts/make_figures.py`
- Create (output): `paper/figs/fig1_baseline_fM.pdf`

- [ ] **Step 1: Replace the `fig1_baseline_fM` stub**

```python
def fig1_baseline_fM():
    truth = load_truth("baseline")
    m_star = truth["M_truth"]            # onset == argmax on this float-flat plateau
    f_star = truth["throughput_truth"]
    ms = [pt["m"] for pt in truth["f_curve"]]
    fs = [pt["throughput"] for pt in truth["f_curve"]]

    fig, ax = plt.subplots(figsize=(5.5, 3.2))
    ax.plot(ms, fs, color="C0")
    ax.axvline(m_star, color="gray", linestyle="--", linewidth=1)
    ax.annotate(f"$M^* = {m_star}$", xy=(m_star, f_star),
                xytext=(m_star + 20, f_star * 0.55), fontsize=10, color="gray",
                arrowprops=dict(arrowstyle="->", color="gray", lw=0.8))
    ax.text(m_star / 2, f_star * 0.40, "rising", ha="center", color="C0", alpha=0.7)
    ax.text((m_star + M_MAX) / 2, f_star * 1.04, "plateau", ha="center", color="C0", alpha=0.7)
    ax.set_xlabel("MaxBatchSize $M$")
    ax.set_ylabel("$f(M)$ — max RPS meeting SLOs")
    ax.set_xlim(0, M_MAX)
    ax.set_ylim(0, f_star * 1.15)
    fig.savefig(FIG_DIR / "fig1_baseline_fM.pdf")
    plt.close(fig)
```

- [ ] **Step 2: Run and inspect**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper/scripts
source .venv/bin/activate && python make_figures.py
```
Then inspect `paper/figs/fig1_baseline_fM.pdf` (Read tool renders PDFs).
Expected: single curve rising concavely to M≈69 then flat; dashed line + "$M^*=69$"
at M=69; annotations not overlapping the curve. If they overlap, adjust the `xytext`
and `text` coordinates and re-run before committing.

- [ ] **Step 3: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/scripts/make_figures.py paper/figs/fig1_baseline_fM.pdf
git commit -m "paper: Fig 1 — headline f(M) for baseline"
```

---

### Task 5: Fig 2 — six-scenario overlay (normalized)

**Files:**
- Modify: `paper/scripts/make_figures.py`
- Create (output): `paper/figs/fig2_overlay_fM.pdf`

- [ ] **Step 1: Replace the `fig2_overlay_fM` stub**

```python
def fig2_overlay_fM():
    fig, ax = plt.subplots(figsize=(5.8, 3.6))
    seen_regimes = set()
    for name in SCENARIOS:
        truth = load_truth(name)
        regime = truth["regime"]
        color = REGIME_COLOR.get(regime, "C4")
        ms = np.array([pt["m"] for pt in truth["f_curve"]])
        fs = np.array([pt["throughput"] for pt in truth["f_curve"]])
        f_star = truth["throughput_truth"]
        norm = fs / f_star if f_star > 0 else fs
        # One legend entry per regime; scenarios in a regime share color.
        label = regime if regime not in seen_regimes else None
        seen_regimes.add(regime)
        ax.plot(ms, norm, color=color, alpha=0.9, label=label)
        ax.axvline(truth["M_truth"], color=color, linestyle=":", linewidth=0.8, alpha=0.5)
    ax.axhline(1.0, color="gray", linewidth=0.6, alpha=0.5)
    ax.set_xlabel("MaxBatchSize $M$")
    ax.set_ylabel(r"$f(M)/f^*$ (normalized)")
    ax.set_xlim(0, M_MAX)
    ax.set_ylim(0, 1.1)
    ax.legend(loc="lower right", framealpha=0.9, title="regime")
    fig.savefig(FIG_DIR / "fig2_overlay_fM.pdf")
    plt.close(fig)
```

- [ ] **Step 2: Run and inspect**

```bash
python make_figures.py
```
Inspect `paper/figs/fig2_overlay_fM.pdf`.
Expected: six normalized curves all rising to a ~1.0 plateau at different `M`; legend
shows the four regimes (crossover, itl-only, ttft-only, unbounded). The shared-color
crossover trio (baseline/alpha-low/alpha-high) reaches the plateau at visibly different
`M`. Legend does not cover data.

- [ ] **Step 3: Commit**

```bash
git add paper/scripts/make_figures.py paper/figs/fig2_overlay_fM.pdf
git commit -m "paper: Fig 2 — normalized six-scenario overlay by regime"
```

---

### Task 6: Fig 3 — min-of-constraints decomposition (baseline)

**Files:**
- Modify: `paper/scripts/make_figures.py`
- Create (output): `paper/figs/fig3_min_constraints.pdf`

- [ ] **Step 1: Replace the `fig3_min_constraints` stub**

```python
def fig3_min_constraints():
    sweep = load_baseline_sweep()
    rows = [r for r in sweep["rows"] if not r["infeasible"]]
    ms = np.array([r["m"] for r in rows])
    lam_ttft = np.array([r["RPSTargetTTFT"] for r in rows])
    lam_itl = np.array([r["RPSTargetITL"] for r in rows])
    f_min = np.minimum(lam_ttft, lam_itl)
    m_star = load_truth("baseline")["M_truth"]

    fig, ax = plt.subplots(figsize=(5.8, 3.6))
    ax.plot(ms, lam_ttft, color="C1", label=r"$\lambda^*_{\mathrm{TTFT}}(M)$")
    ax.plot(ms, lam_itl, color="C2", label=r"$\lambda^*_{\mathrm{ITL}}(M)$")
    ax.plot(ms, f_min, color="C0", linewidth=2.6, label=r"$f(M)=\min(\cdot)$")
    ax.axvspan(ms.min(), m_star, alpha=0.07, color="C1")
    ax.axvspan(m_star, ms.max(), alpha=0.07, color="C2")
    ax.axvline(m_star, color="gray", linestyle="--", linewidth=1)
    ax.text(m_star * 0.5, f_min.max() * 0.15, "TTFT binds", ha="center", color="C1", fontsize=9)
    ax.text((m_star + ms.max()) / 2, f_min.max() * 0.15, "ITL binds", ha="center", color="C2", fontsize=9)
    ax.set_xlabel("MaxBatchSize $M$")
    ax.set_ylabel("RPS")
    ax.set_xlim(ms.min(), ms.max())
    ax.set_ylim(bottom=0)
    ax.legend(loc="lower right", framealpha=0.9)
    fig.savefig(FIG_DIR / "fig3_min_constraints.pdf")
    plt.close(fig)
```

- [ ] **Step 2: Run and inspect**

```bash
python make_figures.py
```
Inspect `paper/figs/fig3_min_constraints.pdf`.
Expected: `λ*_ITL` rises and saturates; `λ*_TTFT` rises and overtakes it; the bold
`f=min` curve is the two-phase lower envelope with the kink near M=69; two shaded
regions, dashed `M*` line. The three curves are visually distinguishable. If `f=min`
hides under a constraint curve, the bold linewidth (2.6) should keep it visible; bump
if needed.

- [ ] **Step 3: Commit**

```bash
git add paper/scripts/make_figures.py paper/figs/fig3_min_constraints.pdf
git commit -m "paper: Fig 3 — min-of-constraints decomposition for baseline"
```

---

### Task 7: Fig 4 — lower bound & bracket (baseline)

**Files:**
- Modify: `paper/scripts/make_figures.py`
- Create (output): `paper/figs/fig4_lower_bound_bracket.pdf`

- [ ] **Step 1: Replace the `fig4_lower_bound_bracket` stub**

```python
def fig4_lower_bound_bracket():
    truth = load_truth("baseline")
    p = SCN_PARAMS["baseline"]
    m_star = truth["M_truth"]
    f_star = truth["throughput_truth"]
    ms = [pt["m"] for pt in truth["f_curve"]]
    fs = [pt["throughput"] for pt in truth["f_curve"]]
    m_itl = P.m_itl(p, M_MAX)
    m_tpf = P.m_tpf(p, M_MAX)

    fig, ax = plt.subplots(figsize=(5.8, 3.4))
    ax.plot(ms, fs, color="C0", zorder=2)
    marks = [
        (m_itl, "C2", f"$M_{{\\mathrm{{ITL}}}}={m_itl}$", "lower bound"),
        (m_star, "gray", f"$M^*={m_star}$", "onset"),
        (m_tpf, "C1", f"$M_{{\\mathrm{{TPF}}}}={m_tpf}$", "TTFT upper bd"),
    ]
    for x, c, lab, _ in marks:
        ax.axvline(x, color=c, linestyle="--", linewidth=1.2, zorder=1)
    # Shade the [M_ITL, M_TPF] bracket the search narrows.
    ax.axvspan(m_itl, m_tpf, alpha=0.08, color="C0", zorder=0)
    handles = [plt.Line2D([0], [0], color=c, linestyle="--", label=lab)
               for x, c, lab, _ in marks]
    ax.legend(handles=handles, loc="lower right", framealpha=0.9)
    ax.set_xlabel("MaxBatchSize $M$")
    ax.set_ylabel("$f(M)$ [RPS]")
    ax.set_xlim(0, M_MAX)
    ax.set_ylim(0, f_star * 1.15)
    fig.savefig(FIG_DIR / "fig4_lower_bound_bracket.pdf")
    plt.close(fig)
```

- [ ] **Step 2: Run and inspect**

```bash
python make_figures.py
```
Inspect `paper/figs/fig4_lower_bound_bracket.pdf`.
Expected: baseline `f(M)` with three dashed verticals — `M_ITL=40` (green, on the
rising phase, below the onset), `M*=69` (gray, at the knee), `M_TPF=147` (orange, out on
the plateau); the `[40,147]` span is lightly shaded. Visually shows `M_ITL` is a lower
bound and the onset sits inside the `[M_ITL, M_TPF]` bracket. Legend readable.

- [ ] **Step 3: Commit**

```bash
git add paper/scripts/make_figures.py paper/figs/fig4_lower_bound_bracket.pdf
git commit -m "paper: Fig 4 — M_ITL lower bound and search bracket"
```

---

### Task 8: Tab 1 — lower bound, regime, and gap

**Files:**
- Modify: `paper/scripts/make_figures.py`
- Create (output): `paper/tabs/lower_bound_regime.tex`

- [ ] **Step 1: Replace the `tab1_lower_bound_regime` stub**

```python
def tab1_lower_bound_regime():
    rows_out = []
    for name in SCENARIOS:
        p = SCN_PARAMS[name]
        truth = load_truth(name)
        m_itl = P.m_itl(p, M_MAX)
        m_tpf = P.m_tpf(p, M_MAX)
        m_star = truth["M_truth"]          # onset == argmax on the dev plateaus
        f_star = truth["throughput_truth"]
        gap = m_star / m_itl if m_itl > 0 else float("nan")
        # gap_f at the lower bound: relative throughput shortfall if you stop at M_ITL.
        f_at_mitl = truth["f_curve"][min(m_itl, len(truth["f_curve"])) - 1]["throughput"]
        gap_f = (f_star - f_at_mitl) / f_star if f_star > 0 else 0.0
        rows_out.append({
            "name": name, "regime": truth["regime"],
            "m_itl": m_itl, "m_tpf": m_tpf, "m_star": m_star,
            "gap": gap, "gap_f": gap_f,
        })

    lines = [
        r"\begin{table}[t]",
        r"  \centering",
        r"  \caption{Closed-form lower bound, regime, and occupancy gap across the "
        r"six scenarios. $M_{\mathrm{ITL}}$ is exact under $nc=1$ (RP-1) and a lower "
        r"bound on the onset $M^*$ (RP-2); the gap $M^*/M_{\mathrm{ITL}}$ is bounded but "
        r"non-constant, motivating a warm-started search rather than direct prediction. "
        r"The $\mathrm{ttft\text{-}only}$ row has $M_{\mathrm{TPF}}<M_{\mathrm{ITL}}$ "
        r"(RP-7), the load-bearing classification signal.}",
        r"  \label{tab:lower-bound-regime}",
        r"  \begin{tabular}{llrrrrr}",
        r"    \toprule",
        r"    Scenario & regime & $M_{\mathrm{ITL}}$ & $M_{\mathrm{TPF}}$ & $M^*$ & "
        r"$M^*/M_{\mathrm{ITL}}$ & gap$_f$ (\%) \\",
        r"    \midrule",
    ]
    for r in rows_out:
        lines.append(
            f"    {r['name'].replace('-', '--')} & {r['regime']} & {r['m_itl']} & "
            f"{r['m_tpf']} & {r['m_star']} & {r['gap']:.2f} & {r['gap_f']*100:.1f} \\\\")
    lines += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}", ""]
    (TAB_DIR / "lower_bound_regime.tex").write_text("\n".join(lines))
```

- [ ] **Step 2: Run and inspect the emitted table**

```bash
python make_figures.py
cat ../tabs/lower_bound_regime.tex
```
Expected: 6 data rows. baseline row reads `baseline & crossover & 40 & 147 & 69 & 1.73 &`
(gap_f ~ a few %); ttft--only row has `95 & 70 & 92` (M_TPF < M_ITL); unbounded row
`256 & 256 & 256 & 1.00`. If `M_ITL`/`M_TPF`/`M*` don't match the Reference-data table
at the top of this plan, stop — the primitives or truth caches are being misread.

- [ ] **Step 3: Verify it compiles**

`booktabs` is already in `main.tex`. Temporarily add `\input{tabs/lower_bound_regime}`
inside `sections/analysis.tex` (after the `\section` line), then:

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper
latexmk -pdf main.tex
```
Expected: `main.pdf` builds and includes the table. Then **remove** the temporary
`\input` line (it returns in Task 14, §5.5).

- [ ] **Step 4: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/scripts/make_figures.py paper/tabs/lower_bound_regime.tex
git commit -m "paper: Tab 1 — lower bound, regime, and occupancy gap"
```

---

## Phase 4 — Section text (subsection-by-subsection)

**Convention:** each task replaces/extends `paper/sections/analysis.tex`. After each,
run `latexmk -pdf main.tex` from `paper/` and inspect `main.pdf` before committing. Pull
facts from the spec and `.nous/queue-throughput-formulas/{report,handoff,principles}`;
do not invent numbers. The section number is `\section` (renders as a number); the spec's
"§5.x" map to the in-section subsections below.

### Task 9: Bibliography + section header

**Files:**
- Modify: `paper/cite.bib`
- Modify: `paper/sections/analysis.tex`

- [ ] **Step 1: Add the analytic-paper entry to `paper/cite.bib`**

```bibtex
% Bibliography for "Scaling with Optimal Concurrency".
@techreport{ramani2026queueing,
  author      = {Ramani, Vishakha and Tantawi, Asser N.},
  title       = {Queueing Model-Based {SLO}-Driven and Self-Tuned {LLM}
                 Inference Service Scaling},
  institution = {IBM T. J. Watson Research Center},
  year        = {2026}
}
```

- [ ] **Step 2: Replace the stub body of `paper/sections/analysis.tex` with the header + intro**

```tex
\section{Analysis: The Shape of $f(M)$}
\label{sec:analysis}

We characterise $f(M)$, the maximum request rate that meets both latency SLOs
(average TTFT and average ITL) at maximum batch size $M$, and derive the structural
facts the scheduling algorithm exploits. Our claims are empirical across six scenarios
and structural via the queueing model of Ramani and Tantawi~\cite{ramani2026queueing};
the empirical breadth is limited, and the structural argument is the load-bearing one
for generality.
```

- [ ] **Step 3: Compile**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper
latexmk -pdf main.tex
```
Expected: builds; the `\cite` shows `[?]` until §5.2 actually cites it and bibtex runs —
acceptable here (no figures referenced yet).

- [ ] **Step 4: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/cite.bib paper/sections/analysis.tex
git commit -m "paper: analysis section header + analytic-paper bib entry"
```

---

### Task 10: §5.1 — The shape of f(M)

**Files:**
- Modify: `paper/sections/analysis.tex`

- [ ] **Step 1: Append the subsection** (after the intro paragraph)

```tex
\subsection{A two-phase curve}
\label{sec:shape}

Figure~\ref{fig:baseline-fM} plots $f(M)$ for the baseline scenario. It rises concavely
to a peak of $f^\ast \approx 1.92$~RPS and then plateaus. We call the operating point of
interest the \emph{onset} $M^\ast$: the smallest $M$ reaching within $\varepsilon=2\%$ of
the peak, $f(M) \ge (1-\varepsilon)\,f_{\max}$. For the baseline, $M^\ast = 69$. The
strict throughput argmax (the smallest $M$ attaining the maximum, which our truth caches
record as $M_{\text{truth}}$) coincides with the onset here because the plateau is flat
to floating-point precision; \S\ref{sec:search} returns to when the two diverge.

\begin{figure}[t]
  \centering
  \includegraphics[width=0.8\linewidth]{fig1_baseline_fM}
  \caption{$f(M)$ for the baseline scenario: a concave rise to the onset
           $M^\ast = 69$, then a plateau.}
  \label{fig:baseline-fM}
\end{figure}

The same two-phase shape recurs across all six scenarios
(Figure~\ref{fig:overlay-fM}), which span four runtime regimes (crossover,
ITL-only, TTFT-only, unbounded) and onsets from $M^\ast=17$ to $256$. We normalise each
curve by its own $f^\ast$ because peak throughput ranges from $0.13$ to $121$~RPS across
the set. Six scenarios are not a universality proof; \S\ref{sec:min-constraints}
supplies the structural reason the shape is general.

\begin{figure}[t]
  \centering
  \includegraphics[width=0.85\linewidth]{fig2_overlay_fM}
  \caption{Normalised $f(M)/f^\ast$ across the six scenarios, coloured by regime. The
           two-phase shape recurs; the onset $M^\ast$ (dotted) varies widely.}
  \label{fig:overlay-fM}
\end{figure}
```

- [ ] **Step 2: Compile and inspect**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper
latexmk -pdf main.tex
```
Inspect `main.pdf`. Expected: §5.1 renders; Figs 1 and 2 placed; no undefined-reference
warnings for `fig:baseline-fM`/`fig:overlay-fM`.

- [ ] **Step 3: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/sections/analysis.tex
git commit -m "paper: draft analysis §5.1 — two-phase shape of f(M)"
```

---

### Task 11: §5.2 — The structural cause: min of binding constraints

**Files:**
- Modify: `paper/sections/analysis.tex`

**Approach (per spec + user decision): cite the model and show the saturation argument;
do not re-derive the closed forms of $\lambda^*$.**

- [ ] **Step 1: Append the subsection**

```tex
\subsection{The structural cause: a minimum of binding constraints}
\label{sec:min-constraints}

The queueing model of Ramani and Tantawi~\cite{ramani2026queueing} represents the server
as a state-dependent M/M/1 queue with a three-parameter service model: a per-iteration
overhead $\alpha$, a per-token compute slope $\beta$, and a per-token KV-cache-access
slope $\gamma$. Each SLO caps the admissible arrival rate at a given $M$, yielding two
constraint curves $\lambda^\ast_{\mathrm{TTFT}}(M)$ and $\lambda^\ast_{\mathrm{ITL}}(M)$
(the \texttt{RPSTargetTTFT} and \texttt{RPSTargetITL} outputs of the analyzer). The
feasible request rate is their lower envelope:
\begin{equation}
  f(M) \;=\; \min\bigl(\lambda^\ast_{\mathrm{TTFT}}(M),\,
                       \lambda^\ast_{\mathrm{ITL}}(M)\bigr).
  \label{eq:min-constraints}
\end{equation}

The two-phase shape follows from the asymmetry of the two curves. The per-iteration
saturation throughput $S(B) = 1000\,B/\tau(B)$ is concave and increasing in the batch
occupancy $B$, approaching an analytic ceiling $S_\infty$ from below; consequently
$\lambda^\ast_{\mathrm{ITL}}(M)$ rises and \emph{saturates}, while
$\lambda^\ast_{\mathrm{TTFT}}(M)$ keeps rising over the range of interest. Below the
crossing the TTFT constraint binds and $f$ rises; above it the (saturated) ITL
constraint binds and $f$ flattens. Figure~\ref{fig:min-constraints} shows the
decomposition for the baseline.

\begin{figure}[t]
  \centering
  \includegraphics[width=0.85\linewidth]{fig3_min_constraints}
  \caption{Min-of-constraints decomposition for the baseline. Below $M^\ast$ the TTFT
           constraint binds; above it the saturated ITL constraint binds. $f(M)$ is the
           lower envelope of Eq.~\eqref{eq:min-constraints}.}
  \label{fig:min-constraints}
\end{figure}
```

- [ ] **Step 2: Compile and cross-check**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper
latexmk -pdf main.tex
```
Inspect `main.pdf`. Expected: §5.2 renders with Eq. (1), Fig 3 placed, the `\cite`
now resolves to `[1]` (bibtex ran). Cross-check the prose against Fig 3: the bold
`f=min` curve should match the rise-then-plateau and cross near M=69.

- [ ] **Step 3: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/sections/analysis.tex
git commit -m "paper: draft analysis §5.2 — min-of-constraints structural argument"
```

---

### Task 12: §5.3 — A closed-form lower bound, M_ITL

**Files:**
- Modify: `paper/sections/analysis.tex`

- [ ] **Step 1: Append the subsection**

```tex
\subsection{A closed-form lower bound: $M_{\mathrm{ITL}}$}
\label{sec:mitl}

When the number of prefill chunks $nc(B)=1$ for all $B\in[1,M_{\max}]$ --- which holds
on all six scenarios --- the per-token latency $\mathrm{itl}(B)$ is exactly affine in
$B$ with slope $\delta = (w_{\mathrm{prefill}}(1)+w_{\mathrm{decode}})/(1+m_{\mathrm{out}})$.
Inverting the ITL target then gives a closed-form ITL-binding batch size
\begin{equation}
  M_{\mathrm{ITL}} \;=\; \mathrm{clamp}\!\left(
    \left\lfloor 1 + \frac{\mathrm{targetITL} - \mathrm{itl}(1)}{\delta}\right\rfloor,
    \,1,\,M_{\max}\right),
  \label{eq:mitl}
\end{equation}
which matches a brute-force scan with zero discrepancy. For the baseline
($\mathrm{itl}(1)\approx 8.29$, $\delta\approx 0.297$), Eq.~\eqref{eq:mitl} gives
$M_{\mathrm{ITL}} = 40$.

$M_{\mathrm{ITL}}$ is a \emph{lower bound} on the onset, not the onset itself. Realised
average ITL averages over occupancies at or below $B$, so
$\mathrm{AvgITL} \le \mathrm{itl}(B)$; the ITL SLO is therefore met at batch sizes above
$M_{\mathrm{ITL}}$, and the true onset lies higher
(Table~\ref{tab:lower-bound-regime}: $M^\ast=69 > 40$ for the baseline). The closed form
requires $nc=1$; under chunk-count jumps $\mathrm{itl}$ becomes piecewise-affine and a
single-slope inversion errs by up to one step --- outside the scope of these scenarios.
```

- [ ] **Step 2: Compile and inspect**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper && latexmk -pdf main.tex
```
Expected: §5.3 renders with Eq. (2); the forward `\ref{tab:lower-bound-regime}` will be
undefined until §5.5 inputs the table — acceptable for now (resolves in Task 14).

- [ ] **Step 3: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/sections/analysis.tex
git commit -m "paper: draft analysis §5.3 — closed-form lower bound M_ITL"
```

---

### Task 13: §5.4 — Regime classification from primitives

**Files:**
- Modify: `paper/sections/analysis.tex`

- [ ] **Step 1: Append the subsection**

```tex
\subsection{Regime classification from primitives}
\label{sec:regimes}

A second primitive, $M_{\mathrm{TPF}}$ --- the largest $B$ whose prefill-only TTFT
$\mathrm{ttft\_prefill}(B)$ meets the TTFT target --- combines with $M_{\mathrm{ITL}}$ to
classify a scenario at zero oracle cost. The primitives partition parameter space into
exactly three cells:
\begin{description}
  \item[Unbounded] neither SLO binds at $M_{\max}$;
  \item[TTFT-only] $M_{\mathrm{TPF}} < M_{\mathrm{ITL}}$;
  \item[ITL-or-crossover] $M_{\mathrm{ITL}} \le M_{\mathrm{TPF}}$.
\end{description}
The load-bearing signal is the \emph{ordering} of $M_{\mathrm{TPF}}$ and
$M_{\mathrm{ITL}}$, not the two binding indicators alone: the TTFT-only scenario violates
both SLOs at $M_{\max}$, so a test on the indicators misclassifies it as crossover.
Note $M_{\mathrm{TPF}}$ bounds the $M$ at which the TTFT constraint first binds, not the
onset: $\mathrm{ttft\_prefill}$ excludes the M/M/1 queue wait, so the realised TTFT
frontier sits above $M_{\mathrm{TPF}}$ (the TTFT-only scenario has $M^\ast = 92 >
M_{\mathrm{TPF}} = 70$). The ITL-only and crossover regimes share the third cell and are
separated only by the oracle.
```

- [ ] **Step 2: Compile and inspect**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper && latexmk -pdf main.tex
```
Expected: §5.4 renders with the three-cell description list.

- [ ] **Step 3: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/sections/analysis.tex
git commit -m "paper: draft analysis §5.4 — regime classification from primitives"
```

---

### Task 14: §5.5 — Why search, not prediction (+ inputs the table)

**Files:**
- Modify: `paper/sections/analysis.tex`

- [ ] **Step 1: Append the subsection** (this is where the table is `\input`)

```tex
\subsection{Why search, not prediction}
\label{sec:search}

\paragraph{Structural plateau vs.\ numerical noise.}
For $M \ge M^\ast$ the saturated ITL constraint bounds $f$ from above (\S\ref{sec:min-constraints}).
The $\sim\!10^{-4}$ wobble we observe over the plateau is solver noise, not true flatness
at machine precision: the structural claim guarantees boundedness, not constancy. We
therefore treat any $M \ge M^\ast$ as achieving $f^\ast$ up to numerical precision.

\paragraph{Onset vs.\ argmax.}
The strict throughput argmax can sit well above the onset on a wide plateau that wiggles
at floating-point precision (we have observed an onset near $46$ against an argmax of
$118$ on wider grids). Over-provisioning to the argmax wastes concurrency, so we optimise
the onset. On the six scenarios here the plateaus are flat to floating point, so the
argmax coincides with the onset and our cached $M_{\text{truth}}$ is a faithful onset.

\paragraph{The occupancy gap forces a search.}
Table~\ref{tab:lower-bound-regime} reports the occupancy gap $M^\ast/M_{\mathrm{ITL}}$.
On the ITL-governed scenarios it ranges from $1.59\times$ to $2.83\times$ and is not a
constant (it widens further on broader grids), so $M_{\mathrm{ITL}}$ cannot predict
$M^\ast$ directly. Instead it \emph{warm-starts} a downward monotone-predicate search:
anchor the near-peak threshold at $f(M_{\max})$ --- a high anchor avoids underestimating
the peak when queue wait lifts realised throughput far above the per-iteration bound ---
and descend to the smallest $M$ still meeting the threshold. Because $f$ is non-decreasing
to a plateau, this converges to the onset in $O(\log M_{\max})$ oracle calls.

\input{tabs/lower_bound_regime}
```

- [ ] **Step 2: Compile and inspect**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper && latexmk -pdf main.tex
```
Inspect `main.pdf`. Expected: §5.5 renders; Table~1 appears; the
`\ref{tab:lower-bound-regime}` in §5.3 and §5.5 now resolves (no undefined-reference
warning after the second latexmk pass — latexmk re-runs automatically).

- [ ] **Step 3: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/sections/analysis.tex
git commit -m "paper: draft analysis §5.5 — why search, not prediction (+ Tab 1)"
```

---

### Task 15: §5.6 — Summary: properties exploited downstream

**Files:**
- Modify: `paper/sections/analysis.tex`

- [ ] **Step 1: Append the subsection**

```tex
\subsection{Summary: properties exploited downstream}
\label{sec:summary}

The scheduling algorithm builds on four properties established here:
\begin{description}
  \item[\textbf{P1} Two-phase shape.] $f(M)$ rises concavely to $M^\ast$, then plateaus
    (\S\ref{sec:shape}, \S\ref{sec:min-constraints}). Optimisation reduces to onset
    detection.
  \item[\textbf{P2} Closed-form warm start.] $M_{\mathrm{ITL}}$ is an exact lower bound
    under $nc=1$, and the $M_{\mathrm{TPF}}$ vs.\ $M_{\mathrm{ITL}}$ ordering classifies
    the regime at zero oracle cost (\S\ref{sec:mitl}, \S\ref{sec:regimes}).
  \item[\textbf{P3} Monotone-to-plateau.] $f$ is non-decreasing, so a downward
    monotone-predicate search with the threshold anchored at $M_{\max}$ converges in
    $O(\log M_{\max})$ calls (\S\ref{sec:search}).
  \item[\textbf{P4} Bounded but non-constant gap.] The occupancy gap rules out pure
    prediction; a warm-started bounded search reaches the onset in a few oracle calls
    (\S\ref{sec:search}).
\end{description}
```

- [ ] **Step 2: Compile and inspect**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper && latexmk -pdf main.tex
```
Expected: §5.6 renders; all four `\ref`s resolve.

- [ ] **Step 3: Commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git add paper/sections/analysis.tex
git commit -m "paper: draft analysis §5.6 — summary of properties"
```

---

## Phase 5 — Final pass

### Task 16: End-to-end build and spec self-review

**Files:**
- Possibly modify: `paper/sections/analysis.tex`, `paper/main.tex`

- [ ] **Step 1: Clean build, capture warnings**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis/paper
latexmk -C
latexmk -pdf main.tex 2>&1 | tee build.log | grep -iE "warning|error|undefined" || true
```
Expected: no `Undefined reference` / `Citation undefined` warnings. Overfull-hbox
warnings are acceptable; note them but don't necessarily fix.

- [ ] **Step 2: Read the rendered PDF end-to-end and check against the spec**

Inspect `paper/main.pdf`. Verify against
`docs/superpowers/specs/2026-06-12-paper-analysis-section-design.md` §7 (claims):
- C1 two-phase shape (Figs 1–2); C2 min-of-constraints (Eq. 1, Fig 3);
- C3 `M_ITL` exact closed form (Eq. 2); C4 `M_ITL` lower bound (Table 1 gaps);
- C5 3-cell regime partition + `M_TPF` ordering (§5.4);
- C6 plateau structural-vs-noise + onset/argmax (§5.5);
- C7 non-constant occupancy gap ⇒ search, with **no "tight predictor / $|error|\le2$"
  language** anywhere (§5.5, Table 1).
- Honest-scope sentence present at the top of the section; `nc=1` and analytic-simulator
  caveats present.

- [ ] **Step 3: Fix anything failing the spec check; re-build and re-inspect after each edit.**

- [ ] **Step 4: Remove the build log and final-commit**

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
rm -f paper/build.log
git add paper/
git commit -m "paper: analysis section — final pass and self-review"
```

---

## Self-Review Checklist (run before declaring done)

- [ ] Every spec subsection (§5.1–5.6) corresponds to a Phase 4 task (Tasks 10–15).
- [ ] Every figure (Figs 1–4) has a Phase 3 task (Tasks 4–7); Tab 1 has Task 8.
- [ ] The regenerated sweep passed the coherence gate (Task 1 Step 6) — Figs 3–4 agree
      with the truth caches.
- [ ] The vendored primitives passed the parity test (Task 2) — `M_ITL`/`M_TPF`/regime
      match the Reference-data table.
- [ ] No "TBD"/"TODO" in committed `.tex`/`.py` (except `cite.bib` header comment).
- [ ] Subsection labels (`sec:shape`, `sec:min-constraints`, `sec:mitl`, `sec:regimes`,
      `sec:search`, `sec:summary`) and figure/table labels are referenced consistently.
- [ ] No surviving "tight predictor"/"$|error|\le 2$"/"$R(M)=1$ crossover" framing from
      the superseded 2026-06-10 spec.
- [ ] The Ramani–Tantawi analytic paper is cited (`\cite{ramani2026queueing}`) and the
      occupancy-gap derivation is flagged as deferred work.
