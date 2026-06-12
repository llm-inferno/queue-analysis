# Campaign Handoff — queue-throughput-formulas (living document)

_Last updated: iter-2 (observe). Builds on iter-1's closed-form derivation._

## Goal

Iter-2 deliverable: a **regime partition** of params-space (≤5 cells) with **closed-form
boundary equations** and a **per-cell M-hat**, derived purely from the analytic primitives
(`nous/harness/formulas.py`) plus the iter-1 bound directions (RP-2, RP-5), answering
"are 4 groups enough?". The executor runs ONE deterministic Python validator
(`inputs/validate_regimes.py`) that imports `formulas.py` and confirms the eight
falsifiable arm assertions in `bundle.yaml`. **Do NOT call `/target` and do NOT read
truth caches in iter-2** — both are reserved for iter-3. No code changes to the target
repo or `nous/harness/strategies/`.

## Key Discoveries

- **Three primitive-decidable cells, not four.** With `itl_binds = itl(256)>targetITL`,
  `ttft_pf_binds = ttft_prefill(256)>targetTTFT`, `M_ITL` (lower bound on ITL-binding M*),
  `M_TPF` (upper bound on TTFT-binding M*): `unbounded` = {¬itl_binds ∧ ¬ttft_pf_binds};
  `ttft-only` = {M_TPF < M_ITL}; `itl-or-crossover` = everything else. On the dev set this
  classifies all six **consistently with their labels**, but `itl-only` and `crossover`
  FUSE into one cell.
- **The `ttft-only` rule is PROVABLE from bound directions.** `M_TPF < M_ITL` ⟹
  `true_TTFT_M ≤ M_TPF < M_ITL ≤ true_ITL_M`, so TTFT strictly binds first regardless of
  the (unknown) queue wait. On the dev set `ttft-only` is the UNIQUE scenario with
  `M_TPF=70 < M_ITL=95`.
- **"4 groups are NOT enough" — the fused cell is irreducible from primitives.**
  `itl-only` (M_ITL=8) and `alpha-low`/crossover (M_ITL=107) share the **identical**
  primitive signature `(itl_binds=1, ttft_pf_binds=0, M_TPF=256>M_ITL)` yet carry
  different labels. The deciding factor is the M/M/1 **queue-wait** term (absent from
  every primitive): in `alpha-low` it pushes TTFT over target at small M (→crossover);
  in `itl-only` the loose `targetTTFT=400` keeps TTFT slack (→itl-only). Splitting this
  cell needs the oracle → iter-3.
- **Both cell boundaries are closed-form and exact under nc=1.**
  (1) Unbounded↔ITL: `targetITL* = itl(1)+(255)·delta(1) = itl(256)` matches to <1e-6 on
  all six. (2) ttft-only on/off: `M_TPF < M_ITL ⟺ targetTTFT < ttft_prefill(M_ITL)`,
  an exact iff on all six. Perturbation confirmed: lowering `baseline` `targetTTFT` below
  `ttft_prefill(M_ITL=40)=28.114` flips it into the `ttft-only` cell at exactly that
  threshold.
- **The ORDERING — not the binding booleans — is the load-bearing component.** A naive
  2×2 on `(itl_binds, ttft_pf_binds)` misclassifies `ttft-only` as `crossover` (it binds
  on both: itl(256)=148>60 AND ttft_prefill(256)=182>80); only `M_TPF<M_ITL` recovers it.
- **Per-cell M-hat (primitive-only point estimates, to be corrected in iter-3):**
  unbounded→256 (exact, assuming Q slack); ttft-only→`M_TPF` (upper bound, queue wait
  pulls down); itl-or-crossover→bracket `[M_ITL, min(M_TPF,256)]`, point `M_ITL` (lower
  bound, occupancy/queue gap closes upward).

## System Interface

- **Build:** none. `formulas.py` is pure-`math`; import resolves from repo root.
- **Run baseline (validated, exit 0):**
  ```bash
  python3 .nous/queue-throughput-formulas/runs/iter-2/inputs/validate_regimes.py \
      --scenarios nous/scenarios.json \
      --out .nous/queue-throughput-formulas/runs/iter-2/results/baseline.json
  ```
- **Output format:** structured JSON via `--out`. Keys: `per_scenario`
  (cell/M_ITL/M_TPF/m_hat/bracket/primitive_signature/regime_label/naive_2x2_label),
  `boundary_itl_unbounded`, `boundary_ttftonly`, `perturbation_baseline_ttft`,
  `naive_2x2_mismatches`, `indistinguishable_label_sets`, `gates` (eight booleans).
- **Baseline result:** all eight gates `true`; `indistinguishable_label_sets =
  {"(1,0,1)": ["crossover","itl-only"]}`; `naive_2x2_mismatches = {"ttft-only":
  "crossover", "alpha-low": "itl-only"}`.

## Code Map

- `nous/harness/formulas.py:72-76` — `delta(B)` recomputes `nc` per B. Look here if a
  closed form deviates from a brute scan (a hidden nc jump changes the slope).
- `formulas.py:89-90` — `_bg(B)=max(0, alpha+(B-1)delta)`. The `max(0,.)` floor is
  inactive for dev alphas; check only if `itl`/`ttft` look clipped at small B.
- `formulas.py:99-102` — `itl(B)`; `:93-96` — `ttft_prefill(B)` (NOTE the docstring: queue
  wait is excluded; the solver adds it — this is the source of the M_TPF upper-bound
  direction and the fused-cell irreducibility); `:83-86` — `tau(B)`.
- `formulas.py:44-56` + `pkg/analyzer/utils.go:8-47` — `nc` step function vs
  `MaxNumTokens=8192`. Look here to predict where chunking starts for a new profile.
- `nous/scenarios.json` — six dev scenarios with per-scenario `alpha/beta/gamma` and a
  `regime` label (the ground truth the partition is checked against in iter-2).
- `nous/cache/truth-<name>.json` — full `f_curve` + `M_truth`/`throughput_truth`.
  **Off-limits until iter-3**; that is where the per-cell M-hat brackets get validated.
- `.nous/queue-throughput-formulas/runs/iter-2/inputs/validate_regimes.py` — the iter-2
  validator (self-locates repo root onto `sys.path`). `classify()` is the partition;
  `naive_2x2()` is the ablation classifier.
- `.nous/.../runs/iter-1/inputs/validate_predictors.py` — iter-1 validator (M_ITL closed
  form, monotonicity, saturation, nc>1 ablation). Reuse its `brute_largest_feasible`.

## Code Targets

None for iter-2 (observe; no `code_changes` in any arm). The first code targets are
iter-4: new strategy files under `nous/harness/strategies/` (e.g. `formula_guided.py`,
`naive_ternary.py`). The partition + per-cell M-hat here is the blueprint those
strategies will encode: classify the scenario, then seed the search at the per-cell
M-hat / bracket.

## What I Tried That Didn't Work

- **The naive prefill-only 2×2 classifier fails on 2 of 6.** Keying on
  `(itl_binds, ttft_pf_binds)` alone calls `ttft-only`→`crossover` (binds on both) and
  `alpha-low`→`itl-only` (ttft_prefill slack). The first mismatch is fixable by the
  `M_TPF<M_ITL` ordering (→ h-ablation); the second is NOT fixable from primitives
  (→ h-control-negative, the queue-wait term).
- **No primitive signal separates `itl-only` from `crossover`.** I searched for one:
  binding booleans, M_ITL/M_TPF ordering, clamp status, M_TPF==256 — `itl-only` and
  `alpha-low` are identical on all of them. The difference lives entirely in the queue
  wait. Do not waste iter-3 budget trying to separate them analytically; just call the
  oracle on the fused-cell scenarios.

## What I Excluded and Why

- **The queue-wait / finite-Q term** (the part of TTFT and the RPS cap the M/M/1 solver
  computes). Not closed-form from primitives; it is precisely the thing that (a) splits
  the fused cell and (b) corrects the per-cell M-hat magnitudes. Out of scope for an
  observe iteration; it is the single biggest open case for iter-3.
- **The occupancy-gap constant `c = M_truth/M_ITL` (≈1.6–2.8 on ITL-binding scenarios per
  iter-1's framing cross-check).** Not a clean constant; needs the oracle to fit. The
  iter-2 M-hat reports the bracket rather than a fitted point.
- **The benchmark grid** (`nous/scenarios_benchmark.json`, 30 scenarios, where `nc>1`
  lives). Reserved for iter-5. The closed-form boundaries here assume `nc=1`; they become
  piecewise above the first nc jump.

## Evolution of Thinking

Iter-1 framed `M_ITL` (lower) and `M_TPF` (upper) as bounds on a single `M*`. Iter-2's
shift: those bounds are not just magnitude estimators — their **relative order**
(`M_TPF<M_ITL` vs `M_ITL<M_TPF`) is a *classifier* that provably decides the `ttft-only`
cell. I expected the four named regimes to be four primitive cells; instead the primitives
yield only three, because `itl-only` and `crossover` differ solely through the queue wait.
This reframes "are 4 groups enough?" from a counting question into a *decidability* one:
the answer is "three cells are decidable; the fourth split is an oracle question." That is
the cleanest possible iter-2 result and it scopes iter-3 sharply (oracle only on the
fused-cell scenarios + the per-cell M-hat brackets).

## Current Status

- **Validated (formulas.py only, no oracle):** the 3-cell signed-bracket partition is
  label-consistent on all six dev scenarios; `ttft-only` ⟺ `M_TPF<M_ITL`; `unbounded` ⟺
  no-bind; both boundary equations are closed-form and exact (<1e-6 / exact iff);
  perturbation flips `baseline` into `ttft-only` at the predicted threshold; the naive
  2×2 (ordering removed) loses `ttft-only`. All eight gates `true`, exit 0.
- **Uncertain (needs the oracle, iter-3):** the `itl-only`↔`crossover` split inside the
  fused cell; whether the `unbounded` prediction survives the small `Q=4`
  (queue could bind even though no latency primitive does); the magnitude correction from
  the bracket endpoints to the true `M*` (occupancy gap upward from `M_ITL`, queue-wait
  gap downward from `M_TPF`).
- **Suggested next (iter-3, observe + oracle):** validate `M-hat`/bracket against
  `/target` on the six dev scenarios — build the `gap_M = |M-hat − M_truth|`,
  `gap_f = (f_truth − f_Mhat)/f_truth` table. Prioritise the fused-cell scenarios
  (`baseline`, `itl-only`, `alpha-low`, `alpha-high`): confirm the queue wait is what
  separates `itl-only` from `crossover`, and fit the occupancy-gap correction that maps
  `M_ITL` (lower) toward `M_truth`. Confirm `unbounded` truly peaks at 256 despite Q=4.

## Warnings & Constraints

- **`nc=1` is a dev-set property, not a law.** Every closed-form boundary here assumes
  constant `delta`. On the benchmark grid (iter-5) the boundaries become piecewise above
  the first nc jump — carry the `nc(B)` check.
- **`M_ITL` is a LOWER bound; `M_TPF` is an UPPER bound.** The per-cell M-hat point
  estimates inherit these directions (itl-or-crossover M-hat under-shoots; ttft-only
  M-hat over-shoots). Do not treat either endpoint as `M*` in iter-3 scoring.
- **The unbounded cell is necessary-not-sufficient from primitives.** It assumes the
  queue capacity `Q` does not bind. `unbounded` has `Q=4` (small!) — iter-3 must confirm
  the oracle still returns `M*=256` there.
- **`/target` HTTP 400 = infeasible** `(M, target-set)`; the oracle maps it to
  `throughput=0.0` and does NOT count it against the call budget. Read the
  `range=[lo,hi]` numbers, not the error prose. Relevant from iter-3 onward.
- **Analyzer service-time fix (`99024df`)** means any pre-fix numbers are stale.
  `formulas.py` is the parity-checked port — use it; show derivations symbolically but
  don't re-derive the arithmetic by hand.
- **Don't peek at truth caches before iter-3.** The iter-2 validator reads neither the
  caches nor the oracle.
