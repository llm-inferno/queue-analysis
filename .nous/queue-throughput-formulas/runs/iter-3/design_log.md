Validation passed. Iteration 3 design is complete.

## Summary

Iter-3 is the first **oracle-enabled** iteration, and the live `/target` data **inverts iter-2's framing**.

**What I verified (live Go server + `/target` + truth caches, all smoke-tested exit 0):**

| scenario | seed_upper | seed_lower (iter-2 est.) | naive_max |
|---|---|---|---|
| baseline | 0.0001 | **0.2345** | 0.0001 |
| itl-only | 0.0027 | **0.4831** | 0.0027 |
| ttft-only | 0.0009 | 0.0009 | 0.0000 |
| unbounded | 0.0000 | 0.0000 | 0.0000 |
| alpha-low | 0.0001 | **0.1011** | 0.0001 |
| alpha-high | 0.0001 | **0.7580** | 0.0001 |

(`gap_throughput_rel`, all at `calls=1`)

**The reframe:** iter-2 designated the bracket **lower** endpoint `M_ITL` as the per-cell point estimate. The oracle shows that's throughput-pessimal (up to 76% gap) — `M_truth` sits well above `M_ITL` (occupancy gap real, ratios 1.3–2.8, *not* a clean constant). The **upper** endpoint `min(M_TPF, 256)` is on the f-plateau and near-optimal everywhere with one call.

**The crux for scoping (h-control-negative):** under nc=1 (verified for all six scenarios across [1,256]) the f-plateau extends to `M_MAX`, so **`naive_max`=256 ties `seed_upper`**. The dev set *cannot* discriminate a formula predictor from "always 256" on the throughput axis — discrimination requires nc>1 (the iter-5 benchmark) where `S(B)` peaks and declines.

**Correction to RP-5 (h-robustness):** for `ttft-only`, `M_truth=92 > M_TPF=70`, so the bracket misses the argmax — yet `seed_upper` still scores 0.0009. `M_TPF` upper-bounds the TTFT *constraint crossing*, not the throughput argmax.

**Artifacts written** (`runs/iter-3/`): `problem.md`, `bundle.yaml` (4 arms: h-main, h-ablation, h-control-negative, h-robustness), `handoff_snapshot.md` + campaign-level `handoff.md`, three validated strategy files in `inputs/`. `nous validate design` → `{"status": "pass"}`.