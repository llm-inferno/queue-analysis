Validation passed. Here's a summary of the iteration 5 findings:

---

**Iteration 5 complete — all 4 arms confirmed, validation passed.**

**Key findings:**

| Arm | Strategy | Crossover calls | No-crossover calls | Gap |
|-----|----------|----------------|-------------------|-----|
| h-main | adaptive_interpolation | **7** | **3** | 0 |
| h-control-negative | ratio_binary_search | 9 | 9 | 0 |
| h-ablation | adaptive_binary | 9 | 3 | 0 |
| h-robustness | adaptive_interpolation (m_max=512) | **8** | 3 | 0 |

**Confirmed principles extracted (RP-15, RP-16, RP-17, RP-12 updated):**
- **RP-15**: The scenario-agnostic floor for crossover scenarios on [2,256] is **7 calls** (6 strategy + 1 confirm) — adaptive_interpolation achieves this exactly.
- **RP-16**: Interpolation is the load-bearing mechanism — removing it (adaptive_binary) reverts to 9 calls, proving the 2-call saving comes entirely from linear interpolation of R(M).
- **RP-17**: Scaling is exactly **+1 call per range doubling** (7→8 for m_max 256→512). No-crossover detection is range-independent at 3 calls.
- **RP-12 updated**: Pareto front now has 3 points: (3, 2.47%) predictor_naive, (5, ~0%) predictor_direct, (7, 0%) adaptive_interpolation. The 2-call gap to predictor_direct is the O(1) cost of not having scenario knowledge.