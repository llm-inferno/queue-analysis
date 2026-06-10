Validation passes. Here's a summary of the findings:

---

**Iteration 1 Complete — All 3 arms CONFIRMED**

**h-main (baseline shape):**
- f(M) is exactly two-phase: 0 monotone violations on rising, plateau variation = 0.017% (< 0.05% predicted)
- Crossover confirmed at M=40: M=39 TTFT-bound (RPSTargetTTFT=2.150 < RPSTargetITL=2.167), M=40 ITL-bound (crossover = M_truth exactly)
- Post-onset concavity holds; convex onset ends at M=8

**h-control-negative (short-tight-ttft):**
- RPSTargetITL is 2.3–2.7× RPSTargetTTFT at all M — ITL never binds
- Gap from M=34 to M=69: 0.00096% (< 0.004% predicted); M_truth=69 is numerical noise

**h-robustness (all 4 scenarios):**
- All plateau variations < 0.08% (< 0.15% predicted): baseline=0.017%, short-tight-ttft=0.001%, long-loose-itl=0.028%, small-queue=0.073%
- Transition widths exactly as predicted: 5, 4, 21, 4 steps — long-loose-itl widest at 21

**5 principles extracted** (RP-1 through RP-5): two-phase structure, binding-crossover identification, transition-width scaling, M=1 infeasibility, and the reframing from peak-finding to plateau-onset detection.