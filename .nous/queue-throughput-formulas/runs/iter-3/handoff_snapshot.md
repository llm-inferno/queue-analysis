# Campaign Handoff — queue-throughput-formulas (living document)

_Last updated: iter-3 (observe + first oracle). Builds on iter-1's closed forms and
iter-2's regime partition._

## Goal

Iter-3 deliverable: **validate the iter-2 per-cell M-hat against the live `/target`
oracle and the truth caches on the six dev scenarios**, and pin down which bracket
endpoint a formula-guided strategy should seed at. The executor runs three standalone
strategy files through `python -m nous.harness.run` (which spawns the Go server, calls
`/target`, and scores against `nous/cache/truth-*.json`), producing `(calls,
gap_throughput_rel)` per scenario. No edits to the target Go repo or to `nous/harness/`.

## Key Discoveries (oracle-confirmed this iteration)

- **THE REFRAME: the UPPER bracket endpoint, not the iter-2 lower endpoint, is the
  throughput-optimal one-call seed.** `seed_upper` (unbounded→256, ttft-only→M_TPF,
  itl-or-crossover→min(M_TPF,256)) scores `gap_rel ≤ 0.0027` on ALL six with **1 call**.
  The iter-2 point estimate `M_ITL` (`seed_lower`) scores `gap_rel` up to **0.758**
  (alpha-high), 0.483 (itl-only), 0.235 (baseline), 0.101 (alpha-low). `M_ITL` lands on
  the RISING part of f(M); the plateau onset `M*` is well above it.
- **`M_truth` is consistently ABOVE the iter-2 lower M-hat** (occupancy gap is real,
  RP-2): baseline 40→69, itl-only 8→17, ttft-only 70→92, alpha-low 107→170, alpha-high
  6→17, unbounded 256→256. Ratios `M_truth/M_ITL` span 1.31–2.83 — **NOT a clean constant**,
  so do not try to fit a single multiplicative occupancy correction (iter-2 was right to
  bracket rather than point-correct). The upper endpoint sidesteps the need for a
  correction entirely on the throughput axis.
- **The f-plateau extends to M_MAX on the nc=1 dev set.** Truth f_curves: the 99%-plateau
  reaches M=256 on every scenario; peak-to-f(256) drop ≤ 0.0027. Hence `naive_max`
  (constant 256, no formula) ALSO scores `gap_rel ≤ 0.0027` everywhere — **it ties
  seed_upper on the throughput axis.** Implication: on the dev set the throughput metric
  CANNOT discriminate a precise predictor from "always 256". Discrimination requires the
  plateau to break (nc>1 → tau super-linear → S(B) peaks and declines → M_MAX falls off
  the plateau). **That is the iter-5 benchmark regime and the whole reason the predictor
  matters.**
- **The iter-2 bracket FAILS to contain M_truth for ttft-only** (M_truth=92 > U=M_TPF=70),
  yet `gap_rel(U)=0.0009`. So RP-5's `M_TPF` upper bound is on the TTFT-CONSTRAINT crossing,
  NOT on the throughput argmax. Throughput only cares about being past the plateau onset.
- **All six dev scenarios are nc=1 across [1,256]** (probed via
  `num_iterations_per_prefill`) — the closed-form endpoints are exact and the plateau
  mechanism holds. This is a dev-set property, NOT a law (RP-4).

## System Interface

- **Build:** none. Harness runs `go run main.go` (repo root) and waits for `:8080`
  (`nous/harness/server.py:38-52`). `go1.26.4` on PATH; activate `nous/.venv` first.
- **Run a strategy (validated, exit 0):**
  ```bash
  source nous/.venv/bin/activate
  python -m nous.harness.run \
      --scenarios nous/scenarios.json \
      --strategy .nous/queue-throughput-formulas/runs/iter-3/inputs/seed_upper.py \
      --m-min 1 --m-max 256 \
      --out .nous/queue-throughput-formulas/runs/iter-3/results/seed_upper.json
  ```
  Repeat with `seed_lower.py` and `naive_max.py`. Reference corner:
  `nous/harness/strategies/example_linear_scan.py` (256 calls, gap 0).
- **Output format:** `--out` writes a JSON list of records; per-scenario stdout line is
  `[name] M=.. calls=.. gap_rel=..`. Score axes in `scoring.py`: `gap_throughput_rel`
  (clamped ≥0), `gap_M`.
- **Validated results (live oracle, this iteration):**
  | scenario | seed_upper | seed_lower | naive_max |
  |---|---|---|---|
  | baseline | 0.0001 | 0.2345 | 0.0001 |
  | itl-only | 0.0027 | 0.4831 | 0.0027 |
  | ttft-only | 0.0009 | 0.0009 | 0.0000 |
  | unbounded | 0.0000 | 0.0000 | 0.0000 |
  | alpha-low | 0.0001 | 0.1011 | 0.0001 |
  | alpha-high | 0.0001 | 0.7580 | 0.0001 |
  All strategies: `calls=1` (the harness confirmatory eval).

## Code Map

- `nous/harness/run.py:78-86` — the +1 confirmatory `eval_(m_chosen)` call, COUNTED in
  `calls`. Every predict-and-confirm strategy costs `internal_calls + 1`.
- `nous/harness/oracle.py:30-38` — `target_eval`; HTTP 400 → `{"throughput":0.0}` and
  **uncounted**; per-scenario alpha/beta/gamma come from the scenario, not a global.
- `nous/harness/scenarios.py:scenario_to_params` — the `params` dict given to `search`
  (alpha/beta/gamma/AvgIn/AvgOut/targetITL/targetTTFT/maxQueueSize). Strategies compute
  predictors LIVE from this — no need to read scenarios.json out-of-band.
- `nous/harness/formulas.py:99-102` (`itl`), `:93-96` (`ttft_prefill`, queue wait
  EXCLUDED), `:72-76` (`delta`, recomputes nc per B), `:83-86` (`tau`). Single source of
  truth for predictors.
- `nous/cache/truth-<name>.json` — `M_truth`, `throughput_truth`, full `f_curve`. Read for
  plateau-shape / gap analysis (NOW allowed).
- `.nous/.../runs/iter-3/inputs/{seed_upper,seed_lower,naive_max}.py` — the three arms.
  `seed_upper`/`seed_lower` share `_largest_feasible` + cell logic; only the endpoint
  differs.
- `.nous/.../runs/iter-2/inputs/validate_regimes.py` — `classify()` (the partition) and
  `brute_largest_feasible`. Reuse for M_ITL/M_TPF.

## Code Targets

None for iter-3 (observe+oracle; arms are standalone strategy input files, no target-repo
patches). **First code targets are iter-4:** promote `seed_upper` into
`nous/harness/strategies/formula_guided.py` as the production seed, plus a refinement tail
for `gap_M` if the benchmark needs the true argmax. The legacy `strategies/predictor_*.py`
and `strategies/_common.py` are STALE (hardcode pre-fix ALPHA=12/BETA=0.05/GAMMA=0.0005 and
an "iter-3 regression fit RP-9" that predates commit 99024df) — do NOT build on them;
rebuild from `formulas.py` + `params`.

## What I Tried That Didn't Work

- **The iter-2 lower-endpoint point estimate `M_ITL` is throughput-pessimal** — gap up to
  0.758. Confirmed against the live oracle. Do not seed there.
- **Fitting a single occupancy-gap constant `c = M_truth/M_ITL`** — the ratios are
  1.31–2.83, not constant; a single `c` cannot map M_ITL→M_truth across scenarios. The
  upper endpoint makes this moot for throughput. (For `gap_M`, a per-cell refinement search
  would be needed — deferred to iter-4 and only if the benchmark rewards `gap_M`.)
- **Trusting the iter-2 bracket to contain M_truth** — it does NOT for ttft-only (92>70).
  The bracket is a constraint-crossing bracket, not an argmax bracket.

## What I Excluded and Why

- **The benchmark grid** (`nous/cache/bench/`, 30 scenarios, where nc>1 lives) — reserved
  for iter-5. It is the regime where the plateau is expected to break (S(B) peaks and
  declines) and therefore the ONLY regime where seed_upper should beat naive_max on
  throughput. Iter-3's dev-set evidence cannot discriminate the two; that is the headline
  caveat for iter-4 design.
- **A multi-call refinement tail for `gap_M`** — iter-3 scores `gap_throughput_rel`, where
  1 call already suffices. Spending calls to pinpoint the exact argmax buys nothing on the
  throughput axis under nc=1. Revisit only if iter-5 rewards `gap_M` or the plateau breaks.
- **The queue-wait / finite-Q term itself** — still not closed-form from primitives; it is
  what would split itl-only↔crossover and what makes ttft-only's M_truth exceed M_TPF. Not
  needed for the throughput-optimal seed, so left unfit.

## Evolution of Thinking

Iter-2 framed `M_ITL` (lower) as the per-cell point estimate and `M_TPF` (upper) as a
soft ceiling, expecting iter-3 to fit an occupancy correction mapping `M_ITL → M*`. The
oracle inverted this: **on the throughput axis you don't want M* at all — you want any
plateau point, and the UPPER endpoint is already one.** The "occupancy gap" is real but
irrelevant to `gap_throughput_rel`; it only matters for `gap_M`. The deeper shift: the dev
set is *throughput-trivial* — `naive_max` ties the best formula — so iter-3's real
contribution is negative/scoping: it proves the dev set cannot justify a predictor on the
throughput axis, and that the justification must come from the nc>1 benchmark where the
plateau breaks. The research question for iter-4/5 sharpens from "what's the best seed?"
to "where does M_MAX stop being good enough, and does seed_upper track the receding
plateau onset there?"

## Current Status

- **Validated (live `/target` oracle + truth caches):** seed_upper `gap_rel ≤ 0.0027` on
  all six at 1 call; seed_lower up to 0.758; naive_max ties seed_upper (≤0.0027); ttft-only
  bracket misses M_truth (92>70) yet seed_upper gap 0.0009; all six are nc=1 over [1,256].
- **Uncertain (needs the nc>1 benchmark, iter-5):** whether seed_upper strictly beats
  naive_max once the plateau peaks-and-declines; whether `min(M_TPF,256)` stays on the
  (now finite) plateau or overshoots past the peak when tau goes super-linear; whether a
  refinement tail is needed for `gap_M`.
- **Suggested next (iter-4, code):** promote `seed_upper` to
  `nous/harness/strategies/formula_guided.py`; add a guard so that if the confirmatory
  `eval_(U)` returns throughput 0 (queue-infeasible at U), the strategy steps M down toward
  the queue-feasible frontier. Then (iter-5) run formula_guided vs naive_max on the
  benchmark grid — the decisive test of whether the predictor earns its keep where the
  plateau breaks.

## Warnings & Constraints

- **`nc=1` is a dev-set property, not a law (RP-4).** Every "plateau extends to M_MAX"
  claim here assumes constant delta. On the benchmark grid the plateau is expected to break
  above the first nc jump — carry the `nc(B)` check; that is the point of iter-5.
- **`naive_max` ties seed_upper on the dev set.** Do NOT conclude the predictor is
  unnecessary — the dev set simply cannot discriminate. The discriminating evidence is
  iter-5. State this explicitly in any iter-4 write-up.
- **`M_ITL` is a LOWER bound (RP-2); `M_TPF` is an UPPER bound on the CONSTRAINT crossing,
  not the throughput argmax (corrected this iteration).** The bracket can miss M_truth
  (ttft-only) while still being throughput-optimal.
- **The harness adds +1 confirmatory call** (`run.py:78-86`), counted. A 0-internal-call
  predictor still reports `calls=1`.
- **HTTP 400 = infeasible (M, target-set)**, mapped to throughput 0.0, uncounted
  (`oracle.py:30-38`). A predict-and-confirm strategy whose seed is queue-infeasible scores
  `gap_rel ~ 1.0` from the confirmatory 0 — guard against this in iter-4.
- **Legacy `strategies/predictor_*.py` + `_common.py` are STALE** (pre-fix constants, old
  regression fit). Rebuild from `formulas.py` + `params`, never import `_common`.
- **Analyzer service-time fix (`99024df`)** — any pre-fix numbers are stale; `formulas.py`
  is the parity-checked port.
