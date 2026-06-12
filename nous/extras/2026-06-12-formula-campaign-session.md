# Session log — NOUS reformulation (formula-guided optimal-concurrency) campaign

**Date:** 2026-06-11 → 2026-06-12
**Branch:** `nous-formula-campaign` (off `main`) · **run_id:** `queue-throughput-formulas`
**Model:** DESIGN phase on `claude-opus-4-8` (override of NOUS default `claude-opus-4-6`).

> Curated decision/findings log of the session (not a verbatim transcript). Companion to the
> machine artifacts in `.nous/queue-throughput-formulas/` (per-iteration `problem.md`,
> `findings.json`, `report.md`) and the spec/plan/runbook under `docs/superpowers/`.

---

## 0. Arc in one paragraph

Starting from the approved spec `docs/superpowers/specs/2026-06-11-nous-reformulation-design.md`,
we wrote an implementation plan, built the harness (Tasks 0–10) via subagent-driven development,
then ran a 5-iteration NOUS campaign with a controller gate-review after each iteration. Iterations
1–3 (observe) derived a closed-form predictor and a regime partition and validated them against the
`/target` oracle. Iteration 3 surfaced a campaign-level problem: **f(M) is monotone-rise-then-flat,
so the throughput objective is trivially satisfied by M=M_max** — the predictor adds no throughput
value. We **reframed the campaign to concurrency efficiency** (minimize provisioned batch size M at
near-peak throughput), nullified the original iter-4/5, and redid them. The reframed `formula_guided`
(downward onset search) **Pareto-dominates both baselines on (calls, gap_M)** on the 30-scenario
benchmark. Campaign succeeded on all four spec §8.2 criteria.

---

## 1. Harness preparation (plan Tasks 0–10)

Built and reviewed; full `pytest nous/harness/tests/` = 44 green. Key pieces:

- **`nous/harness/formulas.py`** — Python port of the analyzer service-time primitives
  (`itl`, `ttft_prefill`, `tau`, `delta`, `num_iterations_per_prefill`). Parity-checked at **real
  nc>1** against a white-box Go test `pkg/analyzer/primitives_parity_test.go`
  (`TestGeneratePrimitivesGolden`, gated by `GOLDEN_OUT`), because the exported
  `IterationTime/PrefillTime/DecodeTime` shims hardcode nc=1 and can't reference chunked prefill.
  `MAX_NUM_TOKENS=8192` (analyzer `DefaultMaxNumTokens`).
- **Per-scenario α/β/γ + `regime`** schema; 6 regime-spanning dev scenarios (`nous/scenarios.json`)
  + a deterministic 30-sample LHS benchmark (`nous/scenarios_benchmark.json`, seed 42).
- **Widened strategy contract** `search(target_eval, params, m_min, m_max)`; 8 prior strategies
  retrofitted as a parameter-blind baseline cohort (signature-only).
- **Truth caches** regenerated on the corrected analyzer (`99024df`): dev `nous/cache/truth-<name>.json`,
  benchmark `nous/cache/bench/<idx>.json` (5/30 bench scenarios are genuinely all-infeasible).
- **Brief** `nous/description.txt` + `nous/campaign.yaml`.

**Analyzer-fix verification (the gate that had paused the paper) PASSED:** dev-set f\* reproduce the
spec §4.2 design probes within rounding. M\* differed from probes only because brute-force argmax
lands on the plateau onset while probes sampled mid-plateau.

---

## 2. Per-iteration findings + controller gate reviews

Each iteration was independently re-verified against the truth caches before sign-off.

- **Iter-1 (observe) — PASS.** Closed form `M_ITL = clamp(⌊1+(targetITL−itl(1))/δ⌋, 1, 256)`,
  exact vs brute on all 6 dev scenarios because **nc=1 across [1,256]** there. Controller correction:
  NOUS's "M_ITL always lower / M_TPF always upper" was too strong; correct rule is
  `M* ∈ [min(M_ITL, M_TPF), max(...)]` (verified against oracle on all 6).
- **Iter-2 (observe) — PASS.** 3-cell regime partition (unbounded / ttft-only / fused
  itl-or-crossover) with machine-ε boundary equations. **"Is K=4 enough?" → No: primitives decide
  only 3 cells** (itl-only vs crossover share signature `(1,0,1)`; separating needs the queue-wait
  term). Controller cross-check: the raw point estimate `M̂=M_ITL` would fail the iter-3 gap_f gate
  on 3/6 (undershoots into the rising phase).
- **Iter-3 (observe, first oracle) — PASS, but surfaced the campaign-level problem.** NOUS passed by
  seeding the bracket **upper** endpoint (≈M_max) → trivially on the flat plateau, gap_f ≤ 0.27% in
  1 call. Controller benchmark scan: **M=256 is within ≤2.86% of peak f on all 25 feasible bench
  scenarios** (nc>1 up to 67, yet f never meaningfully declines). ⇒ `gap_throughput_rel` cannot
  reward a precise predictor — naive_max ties everything.

### The reframe decision

User chose **"continue, reframe as concurrency efficiency."** Primary objective for iter-4/5 became
**(calls, gap_M) at gap_f ≤ ε=0.02**; `formula_guided` must find the plateau **onset M\*** via a
**downward binary search** (`f(M) ≥ (1−ε)f*` is a monotone predicate → ~6–8 calls) and beat **both**
naive baselines on gap_M. Implemented by editing `nous/description.txt` (commit `57a096e`).

### Nullify + redo (mechanics worth remembering)

The first iter-4/5 (run before the reframe) built `formula_guided` as seed-high + up-probe →
over-provisioned (benchmark gap_M mean 65, *worse* than naive_ternary). We nullified them:
- `_resume_completed_campaign` derives `completed` from the **ledger** (not `state.json`), so trimming
  the ledger to rows `[0,1,2,3]` + setting `state.json {DONE, iter 3}` + removing `runs/iter-4|5`
  re-targets iteration 4.
- Trimmed `principles.json` to RP-1..RP-7 (dropped RP-8 "seed-upper-optimal" / RP-9 "naive_max ties"
  / RP-10–12, which would fight the reframe). Backup at `/tmp/nous-backup-qtf-*` (ephemeral).

- **Iter-4 (redo, code_changes) — PASS.** `formula_guided` (downward onset search) worst gap_M=20,
  mean 5, gap_f ≤ 0.0101, calls ≤ 8 — strictly beats naive_max (239) and naive_ternary (127) on the
  dev set.
- **Iter-5 (code_changes, benchmark) — PASS; CAMPAIGN SUCCEEDED.** On 25 feasible bench scenarios
  (truth-verified): `formula_guided` worst gap_M **72** / mean **16.8**, worst gap_f **0.0138** (no ε
  violations), calls ≤ **8** — **Pareto-dominates both** naive_max (251/156.6, violates gap_f on
  bench-025) and naive_ternary (145/46.5, 30 calls, also violates bench-025). A real bug-and-fix:
  the U-seed underestimated f\* on bench-023 (gap_f=0.2238) → fixed by always anchoring f\* at
  f(m_max). Worst gap_M=72 (bench-019: chose 46 vs strict argmax 118) is the **ε-onset-vs-argmax
  scoring floor**, not strategy error — and arguably *more* concurrency-efficient than the argmax.

---

## 3. Result

A derivation-grounded predictor (closed-form `M_ITL` + 3-cell regime partition) drives a **downward
onset search that finds near-minimal serving concurrency in ≤8 oracle calls**, Pareto-beating both a
blind ternary search and a max-batch heuristic on gap_M at gap_f ≤ 2%. All four spec §8.2 success
criteria met. Report: `.nous/queue-throughput-formulas/report.md`.

**Deliverable strategies** (`nous/harness/strategies/`): `formula_guided.py`, `naive_max.py`,
`naive_ternary.py`.

---

## 4. Reusable gotchas (also in memory / runbook)

- **NOUS CLI:** only `status` takes the run_id; `run`/`resume`/`report` take a **campaign.yaml path**.
  `--max-iterations` is a **total ceiling** (bump by 1 per gated resume).
- **Model default:** `orchestrator/defaults.yaml` hardcodes `design: claude-opus-4-6`; precedence is
  `campaign.models > defaults.yaml > --model`, so override via a `models:` block in `campaign.yaml`.
- **Frozen config:** a fresh `nous run` copies `campaign.yaml` into the work dir; edits to the source
  don't take effect until restart. `resume` re-reads the path you pass.
- **Analyzer nc=1 shims:** exported `IterationTime/PrefillTime/DecodeTime` hardcode nc=1 — parity-test
  the port against the unexported primitives. See `[[reference-analyzer-nc1-shims]]`.
- **Structural:** f(M) is monotone-rise-then-flat on this model/ranges (max post-peak drop 2.86% even
  at nc=67) — so throughput alone is a degenerate objective; concurrency (gap_M) is the meaningful axis.

---

## 5. Pointers

- Spec: `docs/superpowers/specs/2026-06-11-nous-reformulation-design.md`
- Plan: `docs/superpowers/plans/2026-06-11-nous-reformulation-campaign.md`
- Runbook: `docs/superpowers/plans/2026-06-11-nous-reformulation-runbook.md`
- Campaign report: `.nous/queue-throughput-formulas/report.md`
- Paper revival (next): branch `paper-analysis-section`; see memory `project-paper-analysis-section`.
