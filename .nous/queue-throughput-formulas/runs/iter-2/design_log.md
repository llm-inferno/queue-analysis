Validation passed. Iter-2 design is complete.

## Summary

**Iteration 2 (observe) — regime partition + boundary equations.** Designed, validated, and smoke-tested entirely against `nous/harness/formulas.py` (no oracle, no truth caches, no code changes). All four files written and `nous validate design` returns `{"status": "pass"}`.

### Central finding: **4 groups are NOT enough — only 3 cells are primitive-decidable**

Building on iter-1's bound directions (RP-2: `M_ITL` lower bound; RP-5: `M_TPF` upper bound), the signed-bracket partition resolves three cells cleanly:

| cell | rule | per-cell M-hat |
|---|---|---|
| `unbounded` | ¬itl_binds ∧ ¬ttft_pf_binds | 256 (exact) |
| `ttft-only` | `M_TPF < M_ITL` (**provable**: TTFT_M ≤ M_TPF < M_ITL ≤ ITL_M) | `M_TPF` (upper bound) |
| `itl-or-crossover` | else (**FUSED**) | bracket `[M_ITL, min(M_TPF,256)]` |

The `itl-only`↔`crossover` split collapses because `itl-only` and `alpha-low` (crossover) share the **identical** primitive signature `(1,0,+)` — the deciding factor is the M/M/1 **queue-wait term**, absent from every primitive. That's the question scoped sharply for iter-3's oracle.

### The four arms (all gates `true`, exit 0)
- **h-main** — the 3-cell partition is label-consistent on all six dev scenarios.
- **h-control-negative** — the fused cell is irreducible: differently-labelled scenarios share a primitive signature (proves the queue-wait term's necessity).
- **h-robustness** — both boundaries are closed-form & exact (`targetITL* = itl(256)` to <1e-6; `M_TPF<M_ITL ⟺ targetTTFT<ttft_prefill(M_ITL)`); perturbation flips `baseline` into ttft-only at the predicted threshold (28.114).
- **h-ablation** — dropping the `M_TPF<M_ITL` ordering (naive 2×2) misclassifies `ttft-only` as `crossover`, proving the ordering is the load-bearing component.

Files at `runs/iter-2/`: `problem.md`, `bundle.yaml`, `handoff_snapshot.md` (+ campaign `handoff.md`), `inputs/validate_regimes.py`, `results/baseline.json`.