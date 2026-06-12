Validation passes. Here's a summary of iteration 4's design.

## Summary

**Key correction made during exploration:** The prior handoff was misleading — it described a "benchmark stage (iter-5)" and assumed `formula_guided.py`/`naive_ternary.py` already existed. Neither was true. Grounding against the brief's stage plan (`description.txt:160-194`) and the actual filesystem, **iter-4 is the FIRST code-changes stage**: implement three strategies and validate on the **6-scenario dev set**.

**The governing reframe (confirmed live):** the headline metric is **`gap_M` (concurrency / plateau-onset M\*)**, not `gap_throughput_rel`. I verified live that `naive_max` is throughput-perfect (gap_f ≤ 0.0027, 1 call) yet concurrency-worst (**worst gap_M = 239**) — proving gap_f cannot discriminate. I also confirmed `M_truth` *is* the onset M*.

**Bundle (4 arms → 3 deliverable files):**
- **h-main `formula_guided`** — high-seed f* probe + downward monotone-predicate binary search for the smallest M with f(M) ≥ (1−ε/2)·f*, bracketed by closed-form M_ITL. Sim: worst gap_M ≈ 22, ≤9 elsewhere, gap_f ≤ 0.010 — strictly beats both baselines.
- **h-control-negative `naive_max`** — the degenerate constant; gap_f vanishes as a discriminator, gap_M maximal (239).
- **h-ablation `naive_ternary`** — remove formula, keep search: lands on plateau but not the onset (worst gap_M ≈ 127) at ~25-30 calls.
- **h-robustness** — `formula_guided` on ttft-only, where U=M_TPF=70 < onset 92 (RP-5); cell-aware high seeding keeps f* reliable.

**Implementation risk flagged for the executor:** the ≤8-call gate is genuinely tight (f*-seed + confirmatory = 2 fixed; log2(256)=8). A naive full-range binary search hit 10-13 calls on wide-bracket scenarios in sim. The executor must tighten the upper bracket via the RP-2 occupancy-gap bound (~3·M_ITL). The gap_M dominance is robust to this; only the call budget depends on it.

All three artifacts written, handoff copied to the campaign level, and `nous validate design` returns `{"status": "pass"}`.