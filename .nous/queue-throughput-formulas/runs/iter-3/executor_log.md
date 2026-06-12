Validation passes. Here's a summary of what was done and found:

**Phase summary — iter-3 oracle-validated endpoint predictor:**

All four arms **CONFIRMED**:

- **h-main:** `seed_upper` (bracket upper endpoint) achieves `gap_rel ≤ 0.0027` on all six dev scenarios at exactly 1 oracle call, strictly better than `seed_lower` on every ITL-binding scenario (up to 0.758 → 0.00009 on alpha-high).

- **h-ablation:** `seed_lower` (M_ITL, iter-2 point estimate) inflates `gap_rel` by 0.23–0.76 on the four ITL-binding scenarios; ttft-only and unbounded are unchanged (endpoints coincide). The upper endpoint is the necessary component.

- **h-control-negative:** `naive_max` (constant 256) ties `seed_upper` to within 0.001 on all six. The throughput axis cannot discriminate formula precision from "always 256" under nc=1 — the plateau extends to M_MAX on the dev set.

- **h-robustness:** ttft-only's M_truth=92 exceeds the bracket upper endpoint U=70, yet `gap_rel=0.000886`. RP-5 is corrected: M_TPF upper-bounds the TTFT-constraint crossing, not the throughput argmax.

**New principles added:** RP-8 (upper endpoint is the throughput-optimal one-call seed) and RP-9 (naive_max ties seed_upper under nc=1; formula precision requires nc>1 benchmark to discriminate). **Next:** iter-4 promotes `seed_upper` to `formula_guided.py` with a queue-infeasibility guard; iter-5 tests seed_upper vs naive_max on the nc>1 benchmark grid.