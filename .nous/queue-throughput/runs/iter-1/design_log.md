Validation passes. Here's a summary of what was produced:

**Iteration 1 — f-curve shape characterization** is complete. Three artifacts written to `.nous/queue-throughput/runs/iter-1/`:

**Key findings:**
1. f(M) is **not unimodal** in the classical sense — it's a **concave monotone rise followed by a flat plateau** (< 0.03% variation after M*).
2. The peak M* is the **TTFT/ITL binding crossover** — where `RPSTargetTTFT` first exceeds `RPSTargetITL`. Below M*, TTFT constrains throughput; above, ITL constrains it (but barely decreases).
3. `short-tight-ttft` never crosses over (TTFT always dominates), so its "peak" is noise in a perfectly flat region.
4. The rising portion is concave after M≈8, making the problem amenable to algorithms that detect diminishing returns or first-difference thresholds.

**Implication for algorithm design (iter 4-5):** This is a saturation-onset detection problem, not a peak-finding problem. An efficient algorithm should detect when first differences drop below a threshold, or exploit the auxiliary `RPSTargetTTFT`/`RPSTargetITL` information returned by the oracle to detect proximity to the crossover.