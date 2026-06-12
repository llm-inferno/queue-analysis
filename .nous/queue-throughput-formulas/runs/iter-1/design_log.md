Done. **`nous validate design` → `{"status": "pass"}`.**

## Iter-1 (observe) design complete

This iteration derives `M-hat(params)` closed-form and validates the derivation's load-bearing facts **without the oracle** — exactly matching the campaign's iter-1 gate (closed form for ≥1 binding case + open cases listed; no `/target` calls, no code changes).

**What I grounded in the actual code** (`nous/harness/formulas.py`, probed directly):
- **`nc(B)=1` across `[1,256]` on all six dev scenarios** → `delta` is constant → `itl`, `ttft_prefill` are exactly affine, `tau` affine. Chunking (`nc>1`) only appears in the benchmark grid.
- **ITL closed form is exact:** `M_ITL = clamp(⌊1+(targetITL−itl(1))/delta⌋,1,256)` equals a brute scan of `itl(B)` with **zero discrepancy on all 6 scenarios**.
- **Honest scoping** (cross-checked against cached truth for framing only): `M_ITL` is a *lower* bound on the oracle `M*` (realized AvgITL averages over occupancy < B; e.g. itl-only 8 vs M_truth 17), and prefill-only `M_TTFT` is an *upper* bound (queue wait excluded). Bracketing `M*` is deferred to iter-3/4 as "needs case analysis."
- **Ablation found by probing:** `n=7500,m=64,targetITL=200` puts the ITL crossing *above* an nc jump → affine inversion gives 30 vs brute 31, proving `nc=1` is necessary for exactness.

**Artifacts written** to `.nous/queue-throughput-formulas/runs/iter-1/`:
- `problem.md` — full symbolic derivation (M_ITL exact, M_TTFT upper bound, saturation ceiling) with `file:line` evidence.
- `bundle.yaml` — 4 arms: **h-main** (ITL closed form exact + monotonicity), **h-control-negative** (unbounded → M_max), **h-ablation** (nc=1 necessity), **h-robustness** (saturation monotone/concave below `1000/((1+m)δ)`). Skipped h-super-additivity (single-mechanism analytic).
- `handoff_snapshot.md` (+ campaign-level `handoff.md` copy).
- `inputs/validate_predictors.py` — the formulas-only validator; **smoke-tested, exit 0, all 8 gates `true`**, writes `results/baseline.json`.

The executor runs `validate_predictors.py` (no oracle), then iter-2 maps the regime partition.