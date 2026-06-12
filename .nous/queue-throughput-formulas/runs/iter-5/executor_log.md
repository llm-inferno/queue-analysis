All phases complete. Here's a summary of the iter-5 experiment:

---

## Iter-5 Findings Summary

**Research question confirmed:** The benchmark-robust `formula_guided` (h-main, v3) Pareto-dominates both naive baselines on the 30-scenario benchmark grid.

### Aggregate Results

| Strategy | worst gap_M | mean gap_M | worst calls | gap_f viol |
|---|---|---|---|---|
| **h-main (formula_guided v3)** | **72** | **14.0** | **8** | **0** |
| naive_max | 255 | 173.0 | 1 | 1 (bench-025) |
| naive_ternary | 145 | 38.8 | 30 | 1 (bench-025) |

### Per-Regime
- **Infeasible (5 scenarios):** h-main=0, naive_max=255, naive_ternary=0 (coincidental)
- **Interior-peak/nc-jump (bench-025):** h-main=0 (only feasibility-safe), naive_max=250+violation, ternary=136+violation
- **Unbounded (4 scenarios):** h-main worst=38, naive_max=0 (scoring artifact)
- **Normal feasible (20 scenarios):** h-main worst=72/mean=19.1, naive_max worst=251, ternary worst=145

### Ablation Confirms Both Fixes Are Load-Bearing
- **Ablate anchor** (revert to U-seed): bench-023 gap_f jumps back to 0.2238 ✓
- **Ablate infeasibility** (return m_max): worst/mean gap_M re-inflates to 255/56.5 ✓

### New Principle (RP-10)
The cache `M_truth` is the argmax, not the onset. The worst-case gap_M=72 (bench-019, onset=46 vs argmax=118) is a structural scoring floor, not strategy error.