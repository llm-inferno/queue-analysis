Validation passes. Here's a summary of what was accomplished:

## Iter-4 Complete

**Three strategy files implemented:**
- `nous/harness/strategies/formula_guided.py` — closed-form guided downward onset search
- `nous/harness/strategies/naive_ternary.py` — parameter-blind ternary max search  
- `nous/harness/strategies/naive_max.py` — constant M=m_max baseline

**Live dev-set results (6 scenarios):**

| scenario | naive_max gap_M | naive_ternary gap_M | **formula_guided gap_M** | calls | gap_f |
|---|---|---|---|---|---|
| baseline | 187 | 0 | **2** | 8 | 0.0101 |
| itl-only | 239 | 0 | **0** | 6 | 0.0000 |
| ttft-only | 164 | 127 | **20** | 8 | 0.0005 |
| unbounded | 0 | 0 | **0** | 2 | 0.0000 |
| alpha-low | 86 | 0 | **9** | 8 | 0.0100 |
| alpha-high | 239 | 23 | **1** | 6 | 0.0015 |
| **worst** | **239** | **127** | **20** | **8** | **0.0101** |

**Gate checks:**
- Feasibility: worst gap_f = 0.0101 < 0.02 ✓  
- Concurrency: worst gap_M = 20, strictly beats naive_max (239) and naive_ternary (127) ✓  
- Calls: max = 8 ≤ 8 ✓

**Key engineering insight:** `MAX_ITERS=6` cap + `hi = min(seed, 3*M_ITL)` bracket tightening fits all 6 scenarios within 8 total calls. The ttft-only cell-aware high seed (RP-7) fires correctly: M_TPF=70 < M_ITL=95 → seed=256, achieving gap_M=20 vs ~36 without it.