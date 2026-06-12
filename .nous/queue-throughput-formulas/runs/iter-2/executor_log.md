Validation passes. Here's a summary of what was done and what was found:

---

**Iter-2 complete — `nous validate execution` returned `{"status": "pass"}`.**

**Findings (all 4 arms CONFIRMED, all 8 gates true):**

- **h-main:** The 3-cell signed-bracket partition correctly classifies all 6 dev scenarios — `unbounded` (no-bind → M-hat=256), `ttft-only` (M_TPF=70 < M_ITL=95 → M-hat=70), and `itl-or-crossover` (4 remaining scenarios, labels 'itl-only' or 'crossover', M-hat=M_ITL).

- **h-control-negative:** The fused cell is irreducible from primitives. `itl-only` and `alpha-low` (crossover) share identical primitive signature `(1,0,1)` but carry different labels — the split requires the queue-wait term, scoped to iter-3.

- **h-robustness:** Both boundary equations are exact under nc=1. ITL boundary abs_err ≤ 2.84e-14 (< 1e-6) on all 6. The ttft-only iff holds exactly on all 6. Perturbation flips `baseline` into ttft-only at exactly `ttft_prefill(M_ITL=40) = 28.114`.

- **h-ablation:** Naive 2×2 on binding booleans alone misclassifies `ttft-only` as `crossover` (2 errors vs 0 for signed partition), confirming that the M_TPF < M_ITL ordering — not the booleans — is the load-bearing signal.

**New principles extracted:** RP-6 (3 primitive-decidable cells, not 4) and RP-7 (ordering M_TPF < M_ITL is the load-bearing ttft-only classifier). RP-1 through RP-5 carried forward with updated evidence.

**Suggested next (iter-3):** Call `/target` oracle on the 6 dev scenarios to validate per-cell M-hat brackets, fit the occupancy-gap correction from M_ITL toward M*, and confirm whether `unbounded` (Q=4) truly peaks at M=256 despite the small queue capacity.