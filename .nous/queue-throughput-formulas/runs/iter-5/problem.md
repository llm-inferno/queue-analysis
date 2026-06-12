# Problem Framing — iter-5: Benchmark generalization of the formula-guided onset search

## Research Question

Does the iter-4 concurrency-optimal **formula_guided** onset search generalize from the
6-scenario DEV set to the **30-scenario benchmark grid** (`nous/scenarios_benchmark.json`)?
Specifically: when evaluated on the benchmark and scored on the harness Pareto axes
**(calls, gap_M) subject to gap_f ≤ epsilon=0.02**, does formula_guided Pareto-dominate BOTH
naive baselines — `naive_max` (constant M_max) and `naive_ternary` (parameter-blind search) —
in aggregate worst-case and mean? The benchmark introduces three scenario classes the DEV set
never contained, each of which breaks an assumption the iter-4 strategy relied on:

1. **Fully-infeasible scenarios** (5 of 30): every `/target` returns HTTP 400 → throughput 0;
   the truth convention sets `M_truth = m_min = 1` (`baseline_truth.py`: `best_m` defaults to
   `m_min` and only advances on strict `t > best_t`).
2. **Occupancy-gap underestimate scenarios** (e.g. bench-023): the M/M/1 queue wait lets
   realized throughput climb far past the per-iteration binding batch `B`, so the closed-form
   constraint endpoint `U = max(M_ITL, M_TPF)` sits far below the plateau — seeding f* at U
   underestimates the peak (RP-2).
3. **Interior-peak / nc-jump scenarios** (bench-025: `nc` jumps 1→67 at M=256): f is
   **non-monotone** — it peaks at M=6 then *declines* 2.86% by M=256, violating the
   monotone-to-plateau assumption (RP-3, RP-4).

The mechanism under study is `nous/harness/strategies/formula_guided.py` (the downward
monotone-predicate onset search) and the closed-form primitives it uses in
`nous/harness/formulas.py`.

## System Interface

- **Build:** none. The harness spawns the Go analyzer with `go run main.go` and waits for
  `:8080` (`nous/harness/server.py`); `go1.26.4` is on PATH. Activate the venv first:
  `source nous/.venv/bin/activate`.
- **Run a strategy on the benchmark** (validated this iteration, exit 0):
  ```bash
  source nous/.venv/bin/activate
  python -m nous.harness.run \
      --scenarios nous/scenarios_benchmark.json \
      --strategy nous/harness/strategies/<name>.py \
      --m-min 1 --m-max 256 \
      --cache-dir .nous/queue-throughput-formulas/runs/iter-5/inputs/bench_truth \
      --out .nous/queue-throughput-formulas/runs/iter-5/results/<arm>.json
  ```
- **Code evidence (flags / mechanism):**
  - `nous/harness/run.py:106-116` — CLI flags `--scenarios --strategy --m-min --m-max --out
    --cache-dir --repo-dir --port`.
  - `nous/harness/run.py:42-49` `load_truth_for` — reads `truth-<name>.json` from `--cache-dir`.
    The benchmark caches are `nous/cache/bench/bench-NNN.json` **without** the `truth-` prefix,
    so the run **requires** the symlink dir `runs/iter-5/inputs/bench_truth/`
    (`truth-bench-NNN.json → ../../../../nous/cache/bench/bench-NNN.json`, all 30 staged & resolving).
  - `nous/harness/run.py:78` — the +1 confirmatory `eval_(m_chosen)`; counted unless it 400s.
  - `nous/harness/oracle.py:32-35` — `stats.calls` increments **only** on non-400; HTTP 400 →
    `{"throughput": 0.0}`, uncounted.
  - `nous/harness/scoring.py:compute_gap` — `gap_M = abs(m_chosen - m_truth)` (the headline);
    `gap_throughput_rel = max(0,(truth-chosen)/truth)`, **reported 0 when `throughput_truth ≤ 0`**
    (the 5 infeasible scenarios → gap_f is trivially 0 there).
  - `nous/harness/baseline_truth.py` — cache generator. **`M_truth` is the argmax**: the
    *smallest* m reaching the *strict* float-maximum throughput over [m_min, m_max], NOT the
    0.98-onset. On a float-flat plateau (DEV) argmax ≈ onset; on the wiggly benchmark plateau
    the float-exact max lands at an interior point (e.g. bench-023 argmax=57 while the 0.98-onset
    is 13). gap_M is therefore measured against the argmax.
  - `nous/harness/formulas.py:99` `itl`, `:93` `ttft_prefill` (queue wait EXCLUDED), `:83` `tau`,
    `:44` `num_iterations_per_prefill` (nc — check first when nc>1 is suspected).
- **Output:** JSON list of records; headline keys `M_chosen, calls, gap_M, gap_throughput_rel,
  M_truth, throughput_truth`. Per-scenario stdout prints `gap_rel`, but **read `gap_M` from the
  `--out` JSON** — it is the headline.

## Baseline Command

```bash
source nous/.venv/bin/activate
python -m nous.harness.run \
    --scenarios nous/scenarios_benchmark.json \
    --strategy nous/harness/strategies/formula_guided.py \
    --m-min 1 --m-max 256 \
    --cache-dir .nous/queue-throughput-formulas/runs/iter-5/inputs/bench_truth \
    --out .nous/queue-throughput-formulas/runs/iter-5/results/formula_guided.json
```

## Baseline Validation

Ran the command above (the **committed iter-4** `formula_guided.py`) live on all 30 benchmark
scenarios: **exit 0, 30 records written**. Observed aggregate:
`worst gap_M=255, mean gap_M=56.8, worst gap_f=0.2238, worst calls=8`. Critically it
**VIOLATES the gap_f≤epsilon feasibility constraint on bench-023** (gap_f=0.2238: it seeded f*
at U=9, set the threshold too low, and descended to M=9 ≪ the true peak at M=57). It also
returns M=256 on all 5 infeasible scenarios (gap_M=255, tying `naive_max`). This proves the
command works AND that the iter-4 strategy does **not** clear the benchmark as-is — motivating
the h-main code change.

## Experimental Conditions

All conditions run the baseline command with a different `--strategy` (and, for h-main / the
ablations, a code change to `formula_guided.py` that the executor patches via `git diff`).

- **h-main — benchmark-robust formula_guided (CODE CHANGE).** Two changes to
  `formula_guided.py`: (1) **always anchor f* at m_max** (drop the cell-aware U-seed branch),
  so the threshold is set from the true plateau peak rather than an occupancy-underestimating
  U; (2) **on an infeasible high-anchor seed** (m_max returns throughput≤0), **return m_min**,
  matching the `M_truth=1` convention for fully-infeasible scenarios (instead of m_max).
  Validated this iteration via the probe `runs/iter-5/inputs/formula_guided_v3.py`.
- **h-control-negative — naive_max.** Existing `nous/harness/strategies/naive_max.py`
  (returns m_max). Flag-only; no code change.
- **h-ablation — naive_ternary.** Existing `nous/harness/strategies/naive_ternary.py`
  (parameter-blind ternary max-search). Flag-only; no code change.
- **h-robustness — component-necessity ablations (CODE CHANGE).** Two ablation variants of the
  h-main strategy: **(a) revert-high-anchor** (re-instate the iter-4 U-seed) and
  **(b) revert-infeasibility** (return m_max instead of m_min on an infeasible seed, = "v2").
  Each is run on the benchmark to show the corresponding fix is load-bearing on its target
  regime.

## Success Criteria (directional; observable metrics)

- **h-main** Pareto-dominates BOTH baselines in **aggregate (worst-case AND mean) gap_M** while
  holding **gap_f ≤ epsilon on all 30 scenarios** at **worst-case calls ≤ 8**. It must
  strictly reduce worst-case and mean gap_M versus naive_max, and reduce calls *and* gap_M
  versus naive_ternary. (Probe values: v3 worst gap_M=72, mean=14.0, worst gap_f=0.0138,
  worst calls=8; naive_max worst gap_M=255, mean=173.0, gap_f viol on bench-025; naive_ternary
  worst gap_M=145, mean=38.8, 30 calls, gap_f viol on bench-025.)
- **h-control-negative**: naive_max has maximal aggregate gap_M and **violates gap_f on the one
  non-monotone scenario** (bench-025, gap_f≈0.0286).
- **h-ablation**: naive_ternary lands on the plateau (gap_f≈0 on monotone scenarios) but costs
  ~30 calls, has higher gap_M than h-main, and still violates gap_f on bench-025.
- **h-robustness**: reverting the high-anchor re-introduces a gap_f violation on bench-023
  (≈0.22); reverting the infeasibility fix re-inflates worst/mean gap_M to 255/≈56.5 on the 5
  infeasible scenarios. h-main (both fixes) holds gap_f≤epsilon and gap_M=0 on bench-025.

## Constraints

- epsilon = 0.02 (gap_f feasibility constraint; `campaign.yaml`, brief `description.txt`).
- Worst-case calls ≤ 8 (= seed + ≤6 search probes + 1 harness confirmatory).
- Out of scope: Go analyzer / `/solve` / `/target` changes; only `nous/harness/*` and
  `nous/harness/strategies/*` (`description.txt`).
- The h-main change must NOT regress the iter-4 DEV gate. Verified this iteration: v3 on DEV
  gives worst gap_M=20, worst gap_f=0.0101, calls=8, zero violations — identical to iter-4.

## Prior Knowledge (active principles applied)

- **RP-2** (occupancy gap, M_truth/M_ITL ∈ [1.59,2.83]) explains why U=max(M_ITL,M_TPF)
  underestimates the peak on bench-023 → the high-anchor fix.
- **RP-3/RP-4** (monotone-to-plateau under nc=1; piecewise-affine when nc jumps) predict the
  interior-peak break on bench-025/bench-020 where nc jumps 1→67.
- **RP-8/RP-9** (downward-onset binary search beats blind ternary on gap_M; the formula's
  downward targeting, not search per se, delivers low gap_M) are the iter-4 mechanism this
  iteration stress-tests on a heterogeneous grid.
- **NEW this iteration:** the cache `M_truth` is the *argmax*, not the 0.98-onset; on the
  wiggly benchmark plateau these diverge (e.g. bench-019 onset≈44 vs argmax=118), so a
  concurrency-correct onset finder incurs a structural gap_M floor that no strategy can close
  without over-provisioning. This is the honest ceiling on the headline gap_M and must be
  reported per-regime, not hidden in the aggregate.
