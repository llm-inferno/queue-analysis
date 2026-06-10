Design complete. Here's the summary:

**Iteration 5 — Adaptive Interpolation Search**

Key finding: A scenario-agnostic algorithm (`adaptive_interpolation`) achieves **7 total oracle calls** worst-case with gap=0, beating ratio_binary_search (9 calls) by 2 but falling short of predictor_direct (5 calls) by 2. This quantifies the value of predictor knowledge at exactly **2 calls**.

The algorithm combines:
1. **Smart midpoint start** — probing M=129 first serves as both the first binary step AND enables cheap no-crossover detection
2. **Linear interpolation** — once a bracket is established, exploits the actual R values (not just comparisons) to converge 3-4x per step instead of binary's 2x

Arms designed:
- **h-main**: adaptive_interpolation → worst=7, gap=0
- **h-control-negative**: ratio_binary_search → worst=9, gap=0 (baseline)
- **h-ablation**: adaptive_binary (no interpolation) → worst=9 (proves interpolation is load-bearing)
- **h-robustness**: adaptive_interpolation at m_max=512 → worst=8 (+1 per range doubling)

All predictions pre-validated by running each strategy through the harness. Artifacts at `.nous/queue-throughput/runs/iter-5/`.