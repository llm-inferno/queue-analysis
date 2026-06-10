Validation passes.

---

**Summary of Iteration 2 Results:**

All 4 arms **CONFIRMED**:

- **h-main (ratio binary search):** Found M* exactly for all 3 crossover scenarios (baseline M=40, long-loose-itl M=93, small-queue M=38) with `gap=0.0` in exactly **9 calls** (8 binary search + 1 harness confirmatory) — within the ≤9 budget.

- **h-control-negative (no-crossover):** For short-tight-ttft, the fallback correctly detected no crossover, returned M=224 on the plateau with `gap=0.0` in **10 calls** — well under the ≤15 budget.

- **h-ablation:** ITL-only peaks at M=24 with 3% decay (no plateau); TTFT-only is monotone-then-flat (0.000079% variation). The two-phase structure is caused entirely by the `min(lambdaStarTTFT, lambdaStarITL)` operation at `queueanalyzer.go:242`.

- **h-robustness:** First-difference ratio at M* = 0.30–0.54 (all < 0.55); normal concavity = 0.969–0.984 (all in [0.96, 0.99]); minimum separation = 0.444 (> 0.40). The crossover signature is unambiguous.

Two new principles extracted: **RP-6** (O(log N) ratio binary search for M*) and **RP-7** (two-phase structure requires both constraints) and **RP-8** (first-difference ratio signature).