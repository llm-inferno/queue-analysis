# NOUS Reformulation — Campaign Run Runbook

Operational steps to run the 5-iteration NOUS campaign whose harness was built in
`docs/superpowers/plans/2026-06-11-nous-reformulation-campaign.md` (plan Tasks 11–15).
Gate criteria are in the spec, `docs/superpowers/specs/2026-06-11-nous-reformulation-design.md` §8.1.

**Branch:** `nous-formula-campaign`  ·  **run_id:** `queue-throughput-formulas` (set in `nous/campaign.yaml`)
**Artifacts land in:** `.nous/queue-throughput-formulas/` (bundle.yaml / findings.json / report)

Run **one iteration at a time** so every gate is reviewed before the next. `target` for the
`status` / `resume` / `report` subcommands is the run_id.

---

## 1. Position + activate

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis
git branch --show-current          # must say: nous-formula-campaign
source nous/.venv/bin/activate
```

## 2. Pre-flight (must be clean before launching)

```bash
python -m pytest nous/harness/tests/ -q     # expect 44 passed
go build -o /tmp/queue-analysis . && echo "build ok"
```

## 3. (Optional safety net) analyzer up on :8080

The harness spawns its own server per run, but iter-3 ad-hoc `/target` probing may want one live:

```bash
/tmp/queue-analysis &          # leave running; kill later with: pkill -f /tmp/queue-analysis
```

## 4. Run iteration 1 — observe mode, NO auto-approve

```bash
nous run nous/campaign.yaml --max-iterations 1
```

- Do **not** pass `--auto-approve` — each iteration is gated.
- Output appears under `.nous/queue-throughput-formulas/`.

## 5. Review the iteration gate, then resume

After each iteration, check its gate (spec §8.1) before continuing:

| iter | mode | gate (must produce) |
|---|---|---|
| 1 | observe | Closed-form M̂(params) for ≥1 binding case **with derivation** (ITL: `n_ITL = (TargetITL − a)/b` from the affine `itl(B)`); open cases listed as "needs case analysis." |
| 2 | observe | Regime partition (≤5 cells) with boundary equations in params; ≥3 dev-set regimes covered. Answers "is K=4 enough?" with a number. |
| 3 | observe | Per-dev-scenario error table (`gap_M`, `gap_f`); worst-case `gap_f ≤ 20%` on ≥4/6. Oracle calls here are NOT counted against any algorithm budget. |
| 4 | code_changes | `formula_guided.py` + `naive_ternary.py`; predicted worst-case calls ≤8, `gap_f ≤ 5%` on dev set. |
| 5 | code_changes | Benchmark Pareto plot + per-regime table; `formula_guided` strictly dominates `naive_ternary` on worst-case (calls, gap). |

Inspect and continue:

`--max-iterations` is a **total ceiling**, not "run N more." A DONE campaign advances to
`completed + 1` only if `completed < max_iterations`. So to gate one iteration at a time,
**bump the ceiling by 1 on each resume**:

```bash
nous status queue-throughput-formulas                  # sanity (status takes the run_id)
nous resume nous/campaign.yaml --max-iterations 2      # runs iteration 2, then stops at the cap
# review iter-2 gate ...
nous resume nous/campaign.yaml --max-iterations 3      # iteration 3
nous resume nous/campaign.yaml --max-iterations 4      # iteration 4
nous resume nous/campaign.yaml --max-iterations 5      # iteration 5
nous report queue-throughput-formulas                  # rolled-up report (takes the run_id)
```

(iter 1 was the initial `nous run ... --max-iterations 1`. If you'd rather not gate, omit
`--max-iterations` and it runs straight to the campaign's `max_iterations: 5`.)

> **CLI gotchas:**
> - `status` / `report` take the **run_id** (`queue-throughput-formulas`); `run` / `resume`
>   take a **campaign.yaml path**. Passing the run_id to `resume` errors "resume requires campaign.yaml".
> - `resume nous/campaign.yaml` reads `run_id`+`repo_path` from the file to locate the existing
>   `.nous/<run_id>/` work dir and continues it (does NOT start a new run). Editing
>   `nous/campaign.yaml` between iterations DOES take effect on the next resume (it loads the file
>   you pass), unlike a fresh `run` which froze its own copy at init.
> - `--max-iterations N` caps the **total** iteration count. Re-running with the same N as a
>   completed campaign is a no-op ("iteration N already complete"). Raise N to advance.

## Cautions

- **Iters 4–5 are `code_changes`** — NOUS adds `formula_guided.py` / `naive_ternary.py` under
  `nous/harness/strategies/`. Before scoring, confirm they load with the widened contract:
  ```bash
  python -c "from nous.harness.run import load_strategy; load_strategy('nous/harness/strategies/formula_guided.py')"
  ```
  The iter-5 benchmark run uses `--cache-dir nous/cache/bench` (truth filenames `bench-XXX.json`);
  the plan (Task 15 Step 1) flags a possible one-line `load_truth_for` prefix fix there.
- **If an iteration stalls or a truth/analyzer anomaly appears, STOP** — the plan and spec §8.3
  treat those as blocking. Surface it for review.
- If `nous run` prompts for approval interactively at each gate, you can omit `--max-iterations 1`
  and approve in-shell; the one-at-a-time loop is just cleaner for getting a second opinion per gate.

## Reference

- Plan: `docs/superpowers/plans/2026-06-11-nous-reformulation-campaign.md`
- Spec: `docs/superpowers/specs/2026-06-11-nous-reformulation-design.md`
- NOUS install: editable in `nous/.venv` (source before any `nous` command); install dir
  `~/Projects/nous/agentic-strategy-evolution`.
