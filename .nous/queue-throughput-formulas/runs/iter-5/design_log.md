Design complete and validation passes. Summary of iter-5:

## iter-5 design — benchmark generalization of the formula-guided onset search

**Approach:** Rather than speculate, I ran all candidate strategies **live on the 30-scenario benchmark** first, then designed the bundle around the ground-truth numbers.

**Two framing corrections that drove the design:**
1. **Cache `M_truth` is the argmax, not the 0.98-onset** (`baseline_truth.py`: smallest m at the *strict* float-max). On the DEV float-flat plateau argmax≈onset; on the wiggly benchmark plateau they diverge (bench-019: onset≈44 vs argmax=118) — so a concurrency-correct onset finder carries a *structural* gap_M floor (~72) that is not strategy error.
2. **gap_f is reported 0 when `throughput_truth≤0`** — the 5 fully-infeasible scenarios are discriminated only by gap_M.

**Key empirical finding:** the committed iter-4 `formula_guided` **fails the benchmark** — gap_f violation on bench-023 (0.2238; seeded f* at U=9 ≪ peak@57) and gap_M=255 on the 5 infeasible scenarios. The fix (validated as `inputs/formula_guided_v3.py`): **always anchor f* at m_max** + **return m_min on an infeasible seed** → worst gap_M 72, mean 14.0, **zero gap_f violations**, calls≤8, DEV gate intact.

**Bundle (4 arms, every prediction backed by a live number):**
- **h-main** — benchmark-robust `formula_guided` (2 edits) dominates both baselines on aggregate gap_M, uniquely gap_f-clean.
- **h-control-negative** — `naive_max` (worst gap_M 255/mean 173; *violates* gap_f on the non-monotone bench-025).
- **h-ablation** — `naive_ternary` (lands on plateau but 30 calls, gap_M 145, still violates gap_f on bench-025).
- **h-robustness** — two component-necessity ablations proving each fix is load-bearing on its target regime.

**Excluded with evidence:** the legacy predictor cohort can't even import under the harness (`from ._common import` → ImportError) and uses scenario-mismatched constants.

Artifacts written to `runs/iter-5/` (problem.md, bundle.yaml, handoff_snapshot.md), campaign handoff copied, `nous validate design` → **`{"status": "pass"}`**.