Design complete. Validation passed.

**Summary:** Iteration 2 targets the key discovery that the RPSTargetTTFT/RPSTargetITL ratio is a strictly monotone function of M that crosses 1.0 at exactly M*, enabling O(log N) binary search for the optimum. Four arms:

1. **h-main**: Binary search on ratio crossing 1.0 finds M* exactly in 8 search calls (9 total)
2. **h-ablation**: Single-constraint removal confirms the two-phase structure requires both TTFT and ITL active
3. **h-control-negative**: short-tight-ttft (no crossover) validates the fallback path
4. **h-robustness**: First-difference ratio signature (< 0.55 at crossover vs 0.97 normal) is unambiguous across all scenarios