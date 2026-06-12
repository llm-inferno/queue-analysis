# Iter-1 (observe) — Closed-form derivation of M-hat(params)

## Research Question

Given the analytic primitives `itl(B)`, the TTFT components, and `tau(B)` for the
vLLM-style queueing model, derive `M-hat(params) = argmax_M f(M)` closed-form by
solving each binding constraint (ITL, TTFT, queue) in isolation, with explicit
assumptions. **Iter-1 is an `observe` stage: NO `/target` (oracle) calls, NO
truth-cache reads, NO code changes.** The deliverable is the symbolic derivation plus
numerical confirmation of its load-bearing facts against the parity-checked primitive
module.

Mechanism source files:
- `nous/harness/formulas.py` — Python port of the analyzer primitives (single source
  of truth for iter-1): `itl`, `ttft_prefill`, `tau`, `delta`,
  `num_iterations_per_prefill`.
- `pkg/analyzer/queueanalyzer.go:275-327` — the Go primitives the port mirrors.
- `pkg/analyzer/utils.go:8-47` — chunk-count (`nc`) step-function logic.

## Derivation

Let `n = AvgInputTokens`, `m = AvgOutputTokens`, and `nc = nc(B)` the chunked-prefill
iteration count (`formulas.py:num_iterations_per_prefill`).

**Key structural fact (probed, see Baseline Validation): `nc(B) = 1` for every
`B ∈ [1,256]` on all six dev scenarios.** The chunk split (`nc>1`) only triggers for
high-input/low-output profiles whose `(n+m)` budget exceeds `MaxNumTokens = 8192`
(`formulas.py:21`). With `nc = 1`, `delta` is **constant in B**:

```
delta = (w_prefill(1) + w_decode) / (1 + m)            # independent of B
bg(B) = alpha + (B-1)*delta                            # positive throughout [1,256]
itl(B)         = [alpha + beta + gamma*(n+(m+1)/2)] + (B-1)*delta     # affine, slope delta
ttft_prefill(B)= [alpha + w_prefill(1)]             + (B-1)*delta     # affine, slope delta
tau(B)         = (1+m)*(alpha + B*delta)                              # affine, slope (1+m)*delta
```

### 1. M_ITL — ITL constraint (closed form, exact under nc=1) — BINDING CASE

`itl` is the per-iteration batch time; it does **not** depend on arrival rate, so once
`itl(B) > targetITL` a full batch of `B` already violates the SLO. Solving the affine form:

```
itl(B) <= targetITL
  ⟺  B <= 1 + (targetITL - itl(1)) / delta
M_ITL = clamp( floor( 1 + (targetITL - itl(1)) / delta ), 1, 256 )
```

Because `nc=1` makes `itl` exactly affine, this closed form equals a brute scan of
`itl(B)` with **zero discrepancy on all six dev scenarios** (verified).

**Assumption / scope:** `M_ITL` is the *batch-saturated* crossing. The solver's realized
`AvgITL` averages over occupancy `≤ B`, so `AvgITL ≤ itl(B)`; hence `M_ITL` is a **lower
bound** on the plateau-onset `M*`, not `M*` itself. Closing this occupancy gap requires
the queue solver → deferred to iter-2/3 (**needs case analysis**).

### 2. M_TTFT — prefill-only TTFT crossing (closed form, upper bound)

```
ttft_prefill(B) <= targetTTFT
  ⟺  B <= 1 + (targetTTFT - ttft_prefill(1)) / delta
M_TTFT_prefill = clamp( floor( 1 + (targetTTFT - ttft_prefill(1)) / delta ), 1, 256 )
```

**Assumption / scope:** full `TTFT = ttft_prefill(B) + queue_wait`, and the M/M/1 solver
adds the (positive) queue-wait term. So `M_TTFT_prefill` is an **upper bound** on the
true TTFT-binding `M`. Quantifying the wait term needs the solver → **needs case
analysis** (iter-2/3).

### 3. Saturation / queue — structural bound (closed form for the ceiling)

```
S(B) = 1000 * B / tau(B) = 1000 / (1+m) * B/(alpha + B*delta)   # req/s ceiling at batch B
```

`S(B)` is monotonically increasing and concave, approaching `S_inf = 1000/((1+m)*delta)`
as `B → ∞`. **Consequence:** throughput is never capped from above by `M` itself —
larger `M` always yields `≥` saturation throughput, at the cost of latency. Therefore
the *useful* upper bound on `M` is set by whichever **latency** constraint binds first,
not by saturation. The finite-queue (`Q = maxQueueSize`) wait term enters only through
the solver → **needs case analysis**.

### Combination rule (candidate; refined iters 2-4)

```
if itl(256) <= targetITL AND ttft_prefill(256) <= targetTTFT:   # nothing binds in range
    M-hat = M_max = 256                                          # "unbounded" regime
else:
    M-hat lies in a bracket: M_ITL (lower bound) .. M_TTFT_prefill (upper bound);
    the binding constraint and the occupancy/queue corrections set the exact M*.
```

This satisfies the iter-1 gate: a **closed form for ≥1 binding case (ITL, exact under
nc=1) with full derivation**; open cases (ITL occupancy-gap correction, TTFT queue-wait
correction, finite-queue term, and the `nc>1` piecewise regime) are explicitly listed as
**needs case analysis**.

## System Interface

This iter-1 experiment uses **only** the primitive module — no server, no oracle.

- **Build/deps:** none beyond the repo's Python (`nous/harness/formulas.py` is pure
  `math`). Import resolves from repo root (`nous/__init__.py`, `nous/harness/__init__.py`).
- **Primitive API** (`nous/harness/formulas.py`): `itl(B, params)`,
  `ttft_prefill(B, params)`, `tau(B, params)`, `delta(B, params)`,
  `num_iterations_per_prefill(B, params)`. `params` keys: `alpha, beta, gamma,
  AvgInputTokens, AvgOutputTokens, targetITL, targetTTFT, maxQueueSize`.
- **Code evidence:**
  - `formulas.py:69-73` — `delta(B, params)` recomputes `nc` per `B` (so the closed form
    is exact only where `nc` is constant).
  - `formulas.py:81-83` — `_bg(B)` = `max(0, alpha + (B-1)*delta)`.
  - `formulas.py:93-96` — `itl(B)` = `_bg(B) + beta + gamma*(n+(m+1)/2)`.
  - `formulas.py:86-89` — `ttft_prefill(B)` = `nc*_bg(B) + _w_prefill(nc)`.
  - `formulas.py:76-79` — `tau(B)` = `(nc+m)*_t_iter(B)`.
  - `formulas.py:33-46` / `utils.go:8-47` — `nc` step function vs `MaxNumTokens=8192`.
- **Output mechanism:** the validator writes a structured JSON via its `--out` flag
  (native; **no shell redirect**).

## Baseline Command

Run from the repo root:

```bash
python3 .nous/queue-throughput-formulas/runs/iter-1/inputs/validate_predictors.py \
    --scenarios nous/scenarios.json \
    --out .nous/queue-throughput-formulas/runs/iter-1/results/baseline.json
```

(The script self-locates the repo root and inserts it on `sys.path`, so cwd is not
critical, but repo root is the canonical invocation.)

## Baseline Validation

Ran the exact command above. **Exit 0.** Output:
`.nous/queue-throughput-formulas/runs/iter-1/results/baseline.json`. All eight gate
booleans returned `true`:

```
h_main_itl_closed_form_exact_all : true   # M_ITL closed-form == brute scan, all 6 scenarios
h_main_all_monotonic             : true   # itl, ttft_prefill, tau monotonic ↑, all 6
h_control_unbounded_no_itl_bind  : true   # unbounded: itl(256)=15.94 < targetITL=200
h_control_unbounded_M_ITL_is_max : true   # unbounded: M_ITL = 256
h_robustness_sat_concave_all     : true   # S(B) concave, all 6
h_robustness_sat_below_ceiling   : true   # S(256) < 1000/((1+m)*delta), all 6 (ratio 0.75–0.96)
h_ablation_nc_gt_1               : true   # high-input profile: nc reaches 2
h_ablation_closed_form_breaks    : true   # affine-from-1 M_ITL = 30 vs brute 31 (mismatch)
```

Representative per-scenario closed-form values (from `baseline.json`):
`M_ITL` = baseline 40, itl-only 8, ttft-only 95, unbounded 256, alpha-low 107,
alpha-high 6 — each an **exact** match to the brute scan of `itl(B)`.

## Experimental Conditions

The derivation is deterministic and closed-form, so there is a **single command** (the
baseline above); the four arms are distinct falsifiable assertions evaluated against
fields of the one `baseline.json`. No flag/seed variation applies (analytic, no
randomness). For the ablation, the script additionally evaluates a synthetic high-input
profile (`n=7500, m=64, targetITL=200`) inside the same run.

- **h-main:** `gates.h_main_itl_closed_form_exact_all` and `gates.h_main_all_monotonic`
  over the six dev scenarios.
- **h-control-negative:** `gates.h_control_unbounded_no_itl_bind` and
  `gates.h_control_unbounded_M_ITL_is_max`.
- **h-robustness:** `gates.h_robustness_sat_concave_all` and
  `gates.h_robustness_sat_below_ceiling_all`.
- **h-ablation:** `ablation_high_input` block — `nc_max > 1` and
  `M_ITL_exact_match == false`.

## Success Criteria

- **h-main:** for all six dev scenarios, `M_ITL_closed_form == M_ITL_brute` (discrepancy
  = 0) and `itl`, `ttft_prefill`, `tau` each strictly increasing in `B`.
- **h-control-negative:** for `unbounded`, `itl_binds_in_range == false` **and**
  `M_ITL_closed_form == 256`.
- **h-robustness:** for all six, `sat_concave == true` and `sat_256_over_ceiling < 1.0`
  (S approaches the analytic ceiling from below).
- **h-ablation:** the high-input profile has `nc_max > 1` **and**
  `M_ITL_exact_match == false`, establishing `nc=1` as necessary for exactness.

(Gate threshold from the campaign brief: "closed form for ≥1 binding case, with
derivation; open cases listed as needs case analysis" — met by the ITL case.)

## Constraints

- **No oracle calls** and **no truth-cache reads** in the iter-1 experiment (truth
  validation is reserved for iter-3). The validator imports only `formulas.py`.
- **No code changes** to the target repo or to `nous/harness/strategies/` (those begin
  iter-4). The validator lives under the iter-1 `inputs/` artifact dir only.
- `MaxNumTokens = 8192` is fixed (`/target` never overrides it); the port hardcodes it.
- Deterministic analytic computation — multi-seed significance design does not apply.

## Prior Knowledge

First iteration of the **reformulation** campaign; no active principles extracted yet.
Carried-over facts that shaped this design:
- The analyzer service-time formula was corrected in commit `99024df` (it had
  double-counted the focal request's work). All pre-fix NOUS numbers are stale; iter-1
  derives afresh from the corrected primitives, for which `formulas.py` is the
  parity-checked port.
- `nc=1` shim gotcha: the analyzer's **exported** `IterationTime/PrefillTime/DecodeTime`
  hardcode `nc=1`; `formulas.py` instead ports the **unexported** chunk-aware primitives,
  so it is faithful at `nc>1`. This is why the ablation (high-input, `nc>1`) is
  meaningful rather than an artifact of the shim.
- `/target` returns HTTP 400 on infeasible `(M, target-set)`; the oracle maps that to
  `{"throughput": 0.0}`. Not exercised in iter-1 (no oracle), but relevant from iter-3.
