Validation passes. Here's a summary of all findings from iteration 3:

---

## Iteration 3 Results Summary

All 4 arms **CONFIRMED**:

**h-main (Predictor Accuracy):** `M_est = round(n_ITL + 3.0*sqrt(n_ITL) + 0.05*wait_budget)` achieves max error = 2 across all 3 crossover scenarios (baseline, long-loose-itl, small-queue). The two dominant components (n_ITL + buffer) account for 99% of M_est for small-wait-budget scenarios.

**h-ablation (Wait Budget Term):** Removing the wait_budget coefficient causes long-loose-itl error to jump from 2 → 8 (increase of 6), while baseline (error=2) and small-queue (error=0) are unaffected — confirming the term is load-bearing for high-utilization scenarios.

**h-control-negative (Crossover Detection):** `sign(wait_budget)` perfectly classifies all 4 scenarios: short-tight-ttft has wait_budget = −11.29ms (no crossover), all others > 0 (crossover). Zero oracle calls needed.

**h-robustness (Predictor-Guided Search):** The `predictor_hybrid` strategy achieves:
- baseline: M_chosen=40 (exact), calls=5, gap=0
- long-loose-itl: M_chosen=93 (exact), calls=5, gap=0
- small-queue: M_chosen=38 (exact), calls=4, gap=0
- short-tight-ttft: M_chosen=92, calls=5, gap_throughput_rel≈0 (plateau landing)

**44% call reduction** (5 vs 9) confirmed. The algorithm uses M_est anchors as dual-purpose identification+binary-search probes, eliminating any identification overhead.

Three new principles extracted: RP-9 (closed-form predictor), RP-10 (wait_budget sign detects crossover), RP-11 (predictor-guided hybrid achieves 5-call budget).