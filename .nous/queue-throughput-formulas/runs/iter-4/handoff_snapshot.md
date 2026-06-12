# Campaign Handoff — queue-throughput-formulas (living document)

_Last updated: iter-4 (FIRST code-changes stage: implement formula_guided +
naive_ternary + naive_max, validate on the 6-scenario DEV set, headline = gap_M).
Builds on iter-1 closed forms, iter-2 regime partition, iter-3 oracle validation._

## CRITICAL NUMBERING / SCOPE CORRECTION (read first)

The previous handoff was labelled "iter-5 benchmark stage" and assumed strategy files
`formula_guided.py`, `naive_ternary.py`, `formula_seed_only.py` already existed. **Both
were wrong.** The brief's stage plan (`nous/description.txt:160-194`) is authoritative:

- iter-1/2/3 = observe stages (closed form / regime partition / dev oracle validation) — DONE.
- **iter-4 (THIS one) = the FIRST code-changes stage: implement `formula_guided.py`,
  `naive_ternary.py`, `naive_max.py` and validate on the DEV set** (`nous/scenarios.json`,
  6 scenarios). Gate: `calls<=8 AND gap_f<=epsilon AND formula_guided worst gap_M strictly
  beats BOTH naive_max and naive_ternary`.
- iter-5 = run those strategies on the 30-scenario benchmark grid.

The only strategy files that exist are the iter-3 dev probes (`seed_upper.py`,
`seed_lower.py`, `naive_max.py`) staged in `runs/iter-3/inputs/` and copied to
`runs/iter-4/inputs/`. `formula_guided.py` and `naive_ternary.py` **do not exist yet** —
the executor creates them.

## THE REFRAME THAT GOVERNS EVERYTHING: gap_M, not gap_f

The brief (`description.txt:133-148`) makes **gap_M = |M_chosen - M_truth| the headline**,
with `gap_f <= epsilon=0.02` only a feasibility constraint. Reason: f(M) is monotone-rising
then flat, so ANY M>=M* (incl. M_max=256) achieves peak within ~3% in ONE call — gap_f
cannot reward a precise predictor. `M_truth` in the caches **is the onset M\*** (smallest M
with f within epsilon of peak), verified this iteration. The deployed value of M̂ is
concurrency: the SMALLEST M reaching near-peak, so we don't waste KV-cache/batch slots.
Every earlier handoff that scored on gap_throughput_rel was optimizing the wrong axis.

## Goal (for the executor)

Implement the three strategy files in `nous/harness/strategies/`, run each on the dev set,
and confirm the iter-4 gate. The headline result is the **gap_M table**: formula_guided
worst gap_M must be << naive_max (239) and << naive_ternary (~127), at gap_f<=0.02 and
calls<=8.

## Key Discoveries (this iteration — all grounded in live runs + offline sim)

- **naive_max is throughput-perfect but concurrency-worst (LIVE on dev):** gap_f<=0.0027,
  1 call, but gap_M = {baseline 187, itl-only 239, ttft-only 164, unbounded 0, alpha-low 86,
  alpha-high 239}. This single table is the campaign's motivation.
- **M_truth = onset M\* (verified):** computed `smallest M with f>=0.98*peak` ≈ M_truth
  (alpha-high 16/17, baseline 66/69, itl-only 17/17, alpha-low 154/170, unbounded 238/256).
- **naive_ternary lands on the plateau but NOT the onset (offline sim, cache-faithful):**
  gap_f~0 everywhere but it converges to an interior/high plateau point — worst gap_M~127
  (ttft-only, lands ~219), ~25-30 calls. Generic max-search has no incentive to find the
  SMALLEST plateau point.
- **formula_guided downward onset search WORKS (offline sim):** probe high seed for f*,
  binary-search down for smallest M with f>=(1-eps/2)*f*. Worst gap_M ~22 (ttft-only),
  <=9 elsewhere (alpha-high 1, baseline 2, itl-only 0, alpha-low 9, unbounded 0); gap_f
  worst ~0.010 with the eps/2 margin. This strictly dominates both baselines on gap_M.
- **CALL-BUDGET TENSION is the real iter-4 implementation risk:** f*-seed + confirmatory =
  2 fixed calls; log2(256)=8, so a naive full-range binary search busts the <=8 gate on
  WIDE-bracket scenarios (large M_ITL with U=M_max: itl-only M_ITL=8→256, alpha-low
  M_ITL=107→256 cost 10-13 calls in sim). The executor MUST tighten the upper bracket
  (occupancy-gap bound ~3*M_ITL, RP-2) or interpolate. gap_M dominance is robust to this;
  only the call gate depends on it.
- **ttft-only needs a HIGH seed (RP-5):** U=M_TPF=70 < onset M*=92, so seeding f* at U
  underestimates the peak and the descent stops too low (~56, gap_M 36). Cell-aware seeding
  (M_TPF<M_ITL signature → seed at M_max) keeps f* reliable (lands ~70, gap_M 22). ALSO note
  M_ITL=95 > M*=92 for ttft-only, so M_ITL is NOT a valid lower bracket there — floor the
  bracket at min(M_ITL, M_TPF).

## System Interface

- **Build:** none. Harness runs `go run main.go`, waits for `:8080` (`server.py`).
  `go1.26.4` on PATH. `source nous/.venv/bin/activate` first.
- **Run a strategy on the DEV set (validated exit 0 this iteration):**
  ```bash
  source nous/.venv/bin/activate
  python -m nous.harness.run \
      --scenarios nous/scenarios.json \
      --strategy nous/harness/strategies/<name>.py \
      --m-min 1 --m-max 256 \
      --out .nous/queue-throughput-formulas/runs/iter-4/results/<arm>.json
  ```
  Dev needs NO symlink cache-dir: default `--cache-dir nous/cache` already has
  `truth-<name>.json`. (The `truth-` prefix symlink trick is only for the iter-5 benchmark,
  whose caches are `nous/cache/bench/bench-NNN.json` without the prefix — symlinks already
  staged in `runs/iter-4/inputs/bench_truth/` for iter-5 reuse.)
- **Output format:** JSON list of records; headline keys `M_chosen, calls, gap_M,
  gap_throughput_rel`. Per-scenario stdout `[name] M=.. calls=.. gap_rel=..` (note: stdout
  prints gap_rel, but READ gap_M from the JSON — it is the headline).
- **Baseline result (LIVE this iteration):** naive_max exit 0, 6 records, gap_f<=0.0027,
  worst gap_M=239, 1 call each.

## Code Map (troubleshooting index)

- `nous/harness/run.py:42` `load_truth_for` — reads `truth-<name>.json` from `--cache-dir`.
  Dev: fine by default. Bench: needs the symlink dir.
- `nous/harness/run.py:78` — the +1 confirmatory `eval_(m_chosen)`, COUNTED unless 400.
- `nous/harness/oracle.py:31-36` — `stats.calls` increments ONLY on non-400; HTTP 400 ->
  `{"throughput":0.0}`, uncounted.
- `nous/harness/scoring.py:34-46` — gap_f = max(0,(truth-chosen)/truth) (0 if truth<=0);
  **gap_M = abs(m_chosen - m_truth)** (the headline).
- `nous/harness/formulas.py:99` `itl`, `:93` `ttft_prefill` (queue wait EXCLUDED), `:82`
  `tau`, `:44` `num_iterations_per_prefill` (nc — check first if nc>1 suspected).
- `nous/harness/scenarios.py:scenario_to_params` — the params dict keys passed to strategies.
- `nous/cache/truth-<name>.json` — dev truths; `f_curve` is a list of `{m, throughput}`
  dicts (extract `d['throughput']`). `M_truth` IS the onset.
- `runs/iter-4/inputs/_sim_dev.py` — offline, cache-faithful simulator of naive_max,
  naive_ternary, and the formula_guided onset search WITH gap_M scoring. Re-run to re-derive
  any (calls, gap_M, gap_f) prediction without the server. `_sim.py` is the benchmark-grid
  version (for iter-5 sanity).
- `runs/iter-3/inputs/seed_upper.py` — the iter-3 upper-endpoint seed; its `upper_endpoint()`
  is the exact U / M_ITL / M_TPF computation to reuse inside formula_guided.

## Code Targets (iter-4 arms — files the executor creates)

- `nous/harness/strategies/formula_guided.py` (h-main) — high-seed f* probe + downward
  monotone-predicate binary search for the onset, bracketed by closed-form M_ITL (floor at
  min(M_ITL,M_TPF)), upper bracket tightened to ~3*M_ITL when U=m_max to fit <=8 calls.
  Cell-aware high seed when M_TPF<M_ITL (ttft-only, RP-7). eps/2 threshold margin for gap_f.
- `nous/harness/strategies/naive_ternary.py` (h-ablation) — parameter-blind ternary max
  search over [m_min,m_max]; treat throughput-0 as -inf.
- `nous/harness/strategies/naive_max.py` (h-control-negative) — return m_max. Copy from
  `runs/iter-4/inputs/naive_max.py` (already validated live this iteration).

## What I Tried That Didn't Work

- **Trusting the prior handoff's narrative.** It claimed `formula_guided`/`naive_ternary`/
  `formula_seed_only` files existed (untracked) and that iter-4 had built them. `git
  ls-files` and `ls strategies/` show ONLY the legacy cohort + iter-3 dev probes. The
  "benchmark stage" it described is iter-5, not iter-4. Re-derive scope from
  description.txt's stage plan, not the handoff prose.
- **Optimizing gap_throughput_rel.** It is degenerate: naive_max ties everything (gap_f<=
  0.0027 on dev, <=0.0286 on bench) in 1 call. The brief's iter-4+ headline is gap_M. The
  iter-3 findings (all about gap_throughput_rel) validated the WRONG axis; their seed_upper
  is throughput-optimal but gap_M-mediocre (e.g. it returns U, far above the onset on
  ITL-binding scenarios).
- **Naive full-range binary search for the onset.** Costs log2(256)+seed+confirm ≈ 10-13
  feasible calls on wide brackets (itl-only, alpha-low) — busts the <=8 gate. A linear
  residual sweep makes it worse (each feasible probe counts). Must tighten the bracket.
- **Seeding f* at the constraint upper endpoint U.** Fails on ttft-only (U=70 < onset 92,
  RP-5): f(U) underestimates the peak, the (1-eps)f* threshold is too low, descent stops at
  ~56. Seed f* HIGH (m_max).
- **Using M_ITL as the lower bracket on ttft-only.** M_ITL=95 > onset 92 there, so it clips
  the answer above the onset. Floor the bracket at min(M_ITL, M_TPF).

## What I Excluded and Why

- **The legacy parameter-blind cohort** (`predictor_*`, `adaptive_*`, `ratio_binary_search`,
  `example_linear_scan`). They import `_common.py` which hardcodes stale ALPHA,BETA,GAMMA
  (`_common.py:30`) not matching per-scenario constants → meaningless numbers. naive_ternary
  is the correct parameter-blind comparator. (The full cohort returns only at iter-5 if the
  designer first rewrites the predictors to take constants via params.)
- **The benchmark grid (30 scenarios).** That is iter-5's stage. Iter-4 gates on the DEV
  set per the brief. I DID smoke-run seed_upper/naive_max on the benchmark to pre-scout
  iter-5 (results in runs/iter-4/results/smoke_*.json) and staged the bench truth symlinks,
  but the iter-4 bundle is dev-only.
- **seed_lower / seed_upper as iter-4 arms.** They are iter-3 throughput-axis probes; on the
  gap_M axis seed_upper returns U (far above the onset on ITL-binding cells), so it is not a
  concurrency contender. Superseded by formula_guided's downward search.

## Evolution of Thinking

I began expecting (per the prior handoff) to RUN four existing strategies on the benchmark
and add a bidirectional arm. Exploration overturned that completely: (1) the files don't
exist and the benchmark is iter-5, not iter-4; (2) the scoring axis is gap_M, not gap_f, so
the whole iter-3 "seed_upper is throughput-optimal" result, while true, optimizes the wrong
thing — seed_upper returns the bracket UPPER endpoint U, which is far ABOVE the onset and
thus has LARGE gap_M (the brief explicitly calls "seeding high" the prior failure mode,
description.txt:188). The real iter-4 task is a DOWNWARD onset search: seed high only to read
f*, then descend to the smallest near-peak M. The constant M_max and blind ternary are the
two baselines this must beat on gap_M — and both do, by a wide margin in sim. The one
genuine hazard is the call budget (<=8 is tight against log2(256)) and the ttft-only seed
undershoot (RP-5); both are handled by bracket tightening and cell-aware high seeding.

## Current Status

- **Validated (LIVE, this iteration):** dev harness path end-to-end for naive_max (exit 0,
  6 records, gap_f<=0.0027, worst gap_M=239, 1 call). seed_upper/naive_max also run LIVE on
  the 30-scenario benchmark (exit 0) for iter-5 pre-scouting. M_truth=onset verified.
- **Validated (offline, cache-faithful sim):** naive_ternary worst gap_M~127 at ~25-30
  calls; formula_guided onset search worst gap_M~22, gap_f<=0.010. Cache fidelity (cache ==
  live /target) reconfirmed by the matching live seed_upper/naive_max smoke numbers.
- **Uncertain (needs the executor's live run):** the EXACT calls of the implemented
  formula_guided (whether the tightened bracket keeps worst-case <=8 on itl-only/alpha-low),
  and the live naive_ternary call counts (~25-30 expected). gap_M dominance is robust; the
  <=8 gate is the open engineering question.
- **Suggested next (iter-5):** once iter-4 passes on the dev set, run all three strategies +
  the (rewritten) baseline cohort on `nous/scenarios_benchmark.json` using the staged
  `runs/iter-4/inputs/bench_truth/` symlink cache-dir; Pareto-compare on (calls, gap_M) with
  a per-regime breakdown. Watch the interior-peak benchmark scenarios (bench-025 M*=6,
  bench-014 M*=5) where even the onset definition interacts with a real f decline (nc jumps
  to 67 at M=256 on bench-025).

## Warnings & Constraints

- **READ gap_M from the JSON, not gap_rel from stdout.** The per-scenario stdout line prints
  gap_throughput_rel; the headline gap_M is only in the `--out` JSON record.
- **gap_f=0 does NOT mean "solved well"** — it means on-plateau (and =0 trivially when
  truth<=0). The win is LOW gap_M at gap_f<=epsilon. The constant M_max has gap_f~0 and is
  the worst strategy.
- **The +1 confirmatory call** (`run.py:78`) is counted unless it is a 400; a 1-internal-call
  strategy reports calls=2 (or 1 if the confirmatory is the same feasible M already probed —
  no, each call counts). Budget for it: internal probes <= 7 to keep total <= 8.
- **nc=1 holds across [1,256] on the DEV set** (RP-3) so f is monotone-to-plateau and the
  downward predicate is clean. This is NOT benchmark-wide (bench-025 jumps to nc=67 at 256) —
  carry the num_iterations_per_prefill check into iter-5.
- **Do NOT import `_common.py` / `predictor_*.py`** — stale hardcoded constants (`_common.py:30`).
- **Out of scope:** Go analyzer / `/solve` / `/target` changes. Only `nous/harness/*` and
  `nous/harness/strategies/*` (description.txt:198).
