# Comments on `.nous/queue-throughput/report.md`

Date: 2026-06-10
Reviewer: Claude (Opus 4.7)
Branch: `nous-throughput-campaign`
Subject: Final report from the 5-iteration NOUS campaign on f(M) = max-RPS-meeting-targets.

Ordered by what's worth pushing back on.

## 1. The 4-call hybrid should have been iter 5, not a footnote

Iter 5 chose `adaptive_interpolation` (7 calls, scenario-agnostic) over the predictor+interpolation combo. But RP-12 plus the iter-3 predictor result already implied a 4-call algorithm was reachable:

- Warm-start at `M_est` (1 call)
- ±1–2 interpolation in a tight bracket (2 calls)
- Confirm (1 call)
= 4 calls, 0% gap

That's the obvious Pareto-improving point. The limitations section flags it explicitly ("predicted structure: 1 warm-start probe + 2 interpolation steps + 1 confirmation = 4 calls with 0% gap"). Punting to "next campaign" reads like the campaign stopped one iteration short of its own conclusion.

## 2. RP-9 is curve-fit, not derived

"Closed-form predictor" is generous framing.

> M_est = round(n_ITL + 3.0·√n_ITL + 0.05·wait_budget)

Two free parameters (the 3.0 and 0.05) fit to 3 crossover points — essentially every crossover scenario in the test set. With |error| ≤ 2 as the success criterion, even a flat constant probably hits it.

The Medium confidence label is correctly downgraded, but the framing as a *derivation* overstates what was done. A genuine derivation would start from the queueing model and yield the coefficients; this regressed them against truth. Calibration fragility is acknowledged in limitations, but the body still calls it "Derived closed-form."

## 3. RP-15's "floor" claim isn't proven, only achieved

> Scenario-agnostic call-count floor is 7

What was shown: one specific algorithm (`adaptive_interpolation`) hits 7 calls. There's no lower-bound argument that no scenario-agnostic algorithm can do better. Should read "best observed" not "floor."

(Information-theoretically, 7 calls over [2, 256] is far from a real lower bound — the search space is 255 integers, log₂(255) ≈ 8 bits, but the structure makes it much easier than that. A real floor argument would need to identify the load-bearing oracle queries.)

## 4. Generalization rests on N=4 scenarios at one hardware profile

Most High-confidence rows (RP-1, RP-2, RP-7, RP-8) are effectively "true on all 4 tested scenarios." Fine as a claim about what was tested, but several are stated as structural laws:

- RP-7: "Two-phase shape caused entirely by `min(lambdaStarTTFT, lambdaStarITL)`"
- RP-8: "df ratio drops to < 0.55 at crossover vs. 0.96–0.99 in rising region"

The limitations section calls this out for RP-9; the same caveat applies more broadly. RP-17's scaling formula is verified at m_max ∈ {256, 512} — two points fit to a +1-per-doubling rule.

## 5. What holds up well

- **Pareto framing** is clean and honest: three non-dominated points (3, 2.47%) / (5, <0.001%) / (7, 0%), with the dominated baseline (9, 0%) called out explicitly.
- **RP-10** (sign of `wait_budget` perfectly classifies crossover/no-crossover at zero oracle cost) is the kind of structural finding that should survive generalization. This is the strongest result in the report.
- **Confidence calibration across rows** is reasonable — RP-9 correctly Medium, the rest defensibly High *for the tested set*.
- **Limitations section** is thorough rather than performative: predictor calibration fragility, m_max scaling unverified beyond 512, oracle noise, multi-objective extensions all named.

## Net

Solid 5-iteration campaign that under-shipped iter 5 and over-claims one structural discovery (RP-9 framing). Worth a short follow-up that:

1. Implements and measures the predicted 4-call hybrid.
2. Re-labels RP-9 as "regression-fit predictor" and refits with more crossover scenarios (vary hardware params).
3. Restates RP-15 as "best-observed call count" until a lower bound is shown.

These are framing/scope critiques, not refutations — the empirical findings on the 4 scenarios look correct.
