# Structural Properties of f(M) and Optimal Argmax Search

## Answer

f(M) = max-RPS-meeting-targets is a two-phase function: a concave monotone rise from M=2 to M* (the TTFT-to-ITL binding-constraint crossover), followed by an essentially flat plateau (variation < 0.08%) for all M ≥ M*. The optimal algorithm is **predictor_direct** (5 total oracle calls, gap_throughput_rel < 0.001%) for scenarios with predictor knowledge, or **adaptive_interpolation** (7 total oracle calls, gap_throughput_rel = 0%) for fully scenario-agnostic search—both dominating the naive 9-call ratio binary search baseline on the Pareto frontier.

---

## Evidence

### Iteration 1 — Shape Characterization
- Confirmed the two-phase structure across all 4 test scenarios: monotone concave rise then flat plateau (plateau variation < 0.08% of f*).
- M=1 is universally infeasible (HTTP 400); harness does not count infeasible calls.
- Confirmed the plateau onset at M* = the TTFT/ITL binding-constraint crossover (R(M) = RPSTargetTTFT/RPSTargetITL crosses 1.0 exactly at M*).
- 100% prediction accuracy on 3 arms.

### Iteration 2 — Crossover Ratio Detection
- R(M) is monotone increasing; binary search on R(M) crossing 1.0 finds M* in exactly 9 oracle calls (8 bisection + 1 harness confirmation) over [2, 256].
- Ablation isolating each constraint confirmed the min() interaction as the sole source of the two-phase shape; ITL-only or TTFT-only constraints individually do not produce the exploitable plateau.
- First-difference ratio at crossover drops to < 0.55 (vs. normal concavity 0.96–0.99)—a separation of > 0.40, providing independent validation.
- 100% prediction accuracy on 4 arms.

### Iteration 3 — Closed-Form Predictor
- Derived closed-form: **M_est = round(n_ITL + 3.0√n_ITL + 0.05·wait_budget)**, where n_ITL = (targetITL − d_intercept)/d_slope and wait_budget = targetTTFT − targetITL − PrefillTime(n_ITL).
- Accuracy |M_est − M*| ≤ 2 for all 3 crossover scenarios.
- wait_budget sign perfectly classifies crossover (positive) vs. no-crossover (negative) with zero oracle calls—100% accuracy across all 4 scenarios.
- 100% prediction accuracy on 4 arms.

### Iteration 4 — Predictor-Guided Algorithm
- **predictor_direct** (±2 sequential probing): ≤ 5 total calls, gap_throughput_rel < 0.001% on all 4 scenarios.
- **predictor_naive** (no refinement): 3 calls but gap up to 2.47% (baseline: M_est=38 vs M*=40).
- **predictor_hybrid** (±5 binary search): ≤ 5 worst-case calls, 4.75 mean calls—slightly more than predictor_direct's 4.25 mean.
- For no-crossover (short-tight-ttft): algorithm correctly returns m_max; gap_throughput_rel = 8.3×10⁻⁶ confirming genuine plateau flatness.
- 100% prediction accuracy on 4 arms.

### Iteration 5 — Adaptive Interpolation Search
- **adaptive_interpolation** (scenario-agnostic): 7 total calls for crossover, 3 total calls for no-crossover (early exit), gap = 0% on all 4 scenarios.
- **adaptive_binary** (no interpolation): 9 calls—same as ratio_binary_search—confirming that interpolation on R(M) is the load-bearing component for the 9→7 reduction.
- Scaling: each doubling of m_max adds +1 call (8 calls at m_max=512, verified).
- 100% prediction accuracy on 4 arms.

### Pareto Front Summary

| Algorithm | Worst-case Calls | Worst-case gap_throughput_rel | Dominated? |
|---|---|---|---|
| predictor_naive | 3 | 2.47% | Non-dominated (fewest calls) |
| predictor_direct | 5 | < 0.001% | **Non-dominated** |
| adaptive_interpolation | 7 | 0% | Non-dominated (no scenario knowledge needed) |
| ratio_binary_search | 9 | 0% | Dominated by adaptive_interpolation |

---

## Principles Discovered

| ID | Statement | Confidence | Regime |
|---|---|---|---|
| RP-1 | f(M) is two-phase: concave rise to M*, then flat plateau with < 0.08% variation | High | All scenarios |
| RP-2 | M* = smallest M where RPSTargetTTFT ≥ RPSTargetITL; R(M) crossing 1.0 | High | Crossover scenarios |
| RP-3 | Rising phase: brief convex onset (M=2–9), then sustained concavity; 90%→99% of f* spans 4–21 steps | High | Rising phase, M < M* |
| RP-4 | M=1 always infeasible; strategies start at M=2 without penalty | High | Universal |
| RP-5 | Optimization reduces to plateau-onset detection; any M ≥ M* achieves f* within 0.08% | High | All scenarios |
| RP-6 | R(M) is monotone; binary search on crossing finds M* in O(log N) calls (9 for N=256) | High | Crossover scenarios |
| RP-7 | Two-phase shape caused entirely by min(lambdaStarTTFT, lambdaStarITL); neither single constraint alone creates it | High | Baseline parameters |
| RP-8 | df ratio drops to < 0.55 at crossover vs. 0.96–0.99 in rising region; separation > 0.40 | High | All crossover scenarios |
| RP-9 | M_est = round(n_ITL + 3.0√n_ITL + 0.05·wait_budget); |error| ≤ 2 for all tested cases | Medium | Crossover, fixed hardware params |
| RP-10 | sign(wait_budget) perfectly classifies crossover/no-crossover with zero oracle calls | High | All 4 tested scenarios |
| RP-11 | Predictor-guided hybrid achieves gap < 0.002% in ≤ 5 calls for all 4 scenarios | High | All scenarios |
| RP-12 | Pareto front has three non-dominated points: (3, 2.47%), (5, <0.001%), (7, 0%) | High | m_max=256, all scenarios |
| RP-13 | No-crossover: optimal algorithm returns m_max; gap_throughput_rel < 0.001% due to genuine plateau flatness | High | No-crossover scenarios |
| RP-14 | Without refinement, predictor error of 2 → gap of 2.47%; gap ≈ slope·(M*−M_est)/f(M*) | High | Crossover, predictor error ≤ 2 |
| RP-15 | Scenario-agnostic call-count floor is 7 (adaptive_interpolation): midpoint-first + no-crossover early exit + interpolation | High | m_max=256, crossover |
| RP-16 | Interpolation on R(M) is the sole source of the 9→7 reduction; smart midpoint alone saves 0 calls for crossover | High | Crossover, m_max=256 |
| RP-17 | adaptive_interpolation scales as 6 + ceil(log₂(m_max/256)) calls; each doubling adds +1 call | High | m_max ∈ {256, 512} |

---

## Limitations & Open Questions

**Calibration fragility (RP-9):** The predictor formula M_est = round(n_ITL + 3.0√n_ITL + 0.05·wait_budget) was calibrated on only 3 crossover data points with 2 free parameters. Its generalization to different hardware profiles (different alpha, beta, gamma), GPU counts, or extreme token length regimes is untested. A next campaign should vary hardware parameters systematically to determine whether the coefficients (3.0, 0.05) are universal or scenario-specific.

**Predictor+Interpolation Hybrid (untested):** RP-12 notes that a 4-call algorithm may be achievable by combining predictor warm-start with interpolation search in a tight bracket. This was identified as a potential Pareto improvement but never implemented. The predicted structure: 1 warm-start probe + 2 interpolation steps + 1 confirmation = 4 calls with 0% gap.

**m_max scaling verification:** RP-17's scaling formula is only verified for m_max ∈ {256, 512}. The prediction of 9 calls at m_max=1024 is unverified. The no-crossover early-exit at 3 calls regardless of range assumes R(m_max) ≥ 1.0 can be evaluated at m_max—this assumption breaks if M* > m_max (i.e., the crossover falls outside the search range).

**No-crossover scenario M*:** For no-crossover scenarios (wait_budget < 0), the analysis returns m_max as the recommended M. However, it is unresolved whether there exists a true M* < m_max for such scenarios under a different throughput model, or whether m_max is genuinely optimal. The gap_throughput_rel = 0.00083% for short-tight-ttft at M=256 vs M_truth=69 is negligible but leaves the structural question open.

**Oracle noise:** All campaigns assumed a deterministic oracle. Real systems may exhibit stochastic throughput estimates (due to queueing variability). The effect of oracle noise on the binary search correctness guarantee (particularly the R(M) ≈ 1.0 boundary) was not investigated.

**Multi-objective extensions:** The current formulation maximizes RPS subject to latency targets. A future campaign could explore the 2D Pareto frontier over (RPS, batch-size cost), where larger M may reduce throughput efficiency per GPU-second.