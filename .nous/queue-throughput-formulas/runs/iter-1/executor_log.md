Validation passes. Here's the iter-1 summary:

---

**Iter-1 complete — all artifacts validated.**

**All 4 arms CONFIRMED:**

- **h-main:** ITL closed form `M_ITL=clamp(floor(1+(targetITL−itl(1))/delta),1,256)` matched the brute scan with **zero discrepancy** on all 6 dev scenarios (nc=1 holds everywhere in [1,256]). All monotonicity checks passed.

- **h-control-negative:** Unbounded scenario correctly returns `M_ITL=256`; `itl(256)=15.94 < targetITL=200` so no interior crossing exists. The clamp-to-max behavior validates mechanism specificity.

- **h-ablation:** High-input profile (n=7500, m=64) drives nc to 174 with jumps at B=6,39,…. The affine-from-1 closed form gives **30 vs brute 31** — establishing nc=1 as a *necessary* condition for exactness.

- **h-robustness:** S(B) monotone+concave on all 6 scenarios; S(256)/S_inf ∈ [0.75, 0.96]. Throughput never decreases with larger M; latency constraints (not saturation) set the binding M upper bound.

**5 principles extracted (RP-1 through RP-5):** exact affine ITL formula (RP-1), M_ITL as lower bound on M* (RP-2), S(B) monotone/concave structure (RP-3), nc=1 necessity condition (RP-4), M_TTFT_prefill as upper bound (RP-5).

**Next (iter-2):** partition params-space into regime cells and derive per-cell M-hat using the closed-form bounds, with boundary equations in (alpha, beta, gamma, n, m, targetITL, targetTTFT, Q).