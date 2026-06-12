#!/usr/bin/env python3
"""Iter-1 (observe) validation of the closed-form M-hat derivation.

NO oracle (/target) calls and NO truth-cache reads. Every claim is checked
purely against nous/harness/formulas.py, the parity-checked port of the Go
analyzer primitives. This script is the iter-1 "experiment": it confirms the
load-bearing facts behind the symbolic derivation of M_ITL, M_TTFT, M_queue.

Usage:
    python3 .nous/queue-throughput-formulas/runs/iter-1/inputs/validate_predictors.py \
        --scenarios nous/scenarios.json \
        --out .nous/queue-throughput-formulas/runs/iter-1/results/baseline.json

Run from the repo root (so `import nous.harness.formulas` resolves).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

# Locate the repo root (dir containing nous/harness/formulas.py) and put it on
# sys.path so this script imports the same primitives the harness uses,
# regardless of the cwd it is launched from.
_d = os.path.abspath(os.path.dirname(__file__))
while _d != "/" and not os.path.exists(os.path.join(_d, "nous", "harness", "formulas.py")):
    _d = os.path.dirname(_d)
if _d not in sys.path:
    sys.path.insert(0, _d)

from nous.harness import formulas as F

M_MIN, M_MAX = 1, 256


def closed_form_M_ITL(params: dict) -> int:
    """Affine inversion of itl(B)=itl(1)+(B-1)*delta at the B=1 slope, clamped."""
    i1 = F.itl(1, params)
    d1 = F.delta(1, params)
    if d1 <= 0:
        return M_MAX
    m = math.floor(1 + (params["targetITL"] - i1) / d1)
    return max(M_MIN, min(M_MAX, m))


def closed_form_M_TTFT_prefill(params: dict) -> int:
    """Affine inversion of the prefill-only TTFT bound (queue wait excluded)."""
    t1 = F.ttft_prefill(1, params)
    dp = F.ttft_prefill(2, params) - F.ttft_prefill(1, params)
    if dp <= 0:
        return M_MAX
    m = math.floor(1 + (params["targetTTFT"] - t1) / dp)
    return max(M_MIN, min(M_MAX, m))


def brute_largest_feasible(metric, params: dict, target: float) -> int | None:
    feas = [B for B in range(M_MIN, M_MAX + 1) if metric(B, params) <= target]
    return max(feas) if feas else None


def analyze(params: dict) -> dict:
    itls = [F.itl(B, params) for B in range(M_MIN, M_MAX + 1)]
    ttfts = [F.ttft_prefill(B, params) for B in range(M_MIN, M_MAX + 1)]
    taus = [F.tau(B, params) for B in range(M_MIN, M_MAX + 1)]
    sat = [1000.0 * B / F.tau(B, params) for B in range(M_MIN, M_MAX + 1)]
    ncs = [F.num_iterations_per_prefill(B, params) for B in range(M_MIN, M_MAX + 1)]

    mono = lambda v: all(v[i] < v[i + 1] for i in range(len(v) - 1))
    secdiff = [sat[i + 1] - 2 * sat[i] + sat[i - 1] for i in range(1, len(sat) - 1)]
    concave = all(x <= 1e-9 for x in secdiff)

    m_out = float(params["AvgOutputTokens"])
    d1 = F.delta(1, params)
    ceiling = 1000.0 / ((1.0 + m_out) * d1) if d1 > 0 else float("inf")

    m_itl_cf = closed_form_M_ITL(params)
    m_itl_brute = brute_largest_feasible(F.itl, params, params["targetITL"])
    m_ttft_cf = closed_form_M_TTFT_prefill(params)

    # "no interior crossing" => constraint does not bind in [1,256]
    itl_binds = itls[-1] > params["targetITL"]
    ttft_prefill_binds = ttfts[-1] > params["targetTTFT"]

    return {
        "nc_min": min(ncs),
        "nc_max": max(ncs),
        "nc_is_one_everywhere": (min(ncs) == 1 and max(ncs) == 1),
        "itl_monotonic": mono(itls),
        "ttft_prefill_monotonic": mono(ttfts),
        "tau_monotonic": mono(taus),
        "sat_monotonic": mono(sat),
        "sat_concave": concave,
        "itl_1": itls[0],
        "itl_256": itls[-1],
        "delta_1": d1,
        "sat_256": sat[-1],
        "sat_ceiling_analytic": ceiling,
        "sat_256_over_ceiling": sat[-1] / ceiling if ceiling else None,
        "itl_binds_in_range": itl_binds,
        "ttft_prefill_binds_in_range": ttft_prefill_binds,
        "M_ITL_closed_form": m_itl_cf,
        "M_ITL_brute": m_itl_brute,
        "M_ITL_exact_match": (m_itl_cf == m_itl_brute),
        "M_TTFT_prefill_closed_form": m_ttft_cf,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    scen = json.load(open(args.scenarios))["scenarios"]
    per_scenario = {}
    for s in scen:
        per_scenario[s["name"]] = {"regime": s.get("regime"), **analyze(dict(s))}

    # --- Ablation: high-input profile where nc>1 within the feasible range ---
    abl = {
        "alpha": 8.0, "beta": 0.033, "gamma": 0.000333,
        "AvgInputTokens": 7500, "AvgOutputTokens": 64,
        "targetITL": 200.0, "targetTTFT": 9999.0, "maxQueueSize": 128,
    }
    abl_ncs = [F.num_iterations_per_prefill(B, abl) for B in range(M_MIN, M_MAX + 1)]
    abl_jumps = [B for B in range(2, M_MAX + 1)
                 if F.num_iterations_per_prefill(B, abl) != F.num_iterations_per_prefill(B - 1, abl)]
    abl_cf = closed_form_M_ITL(abl)
    abl_brute = brute_largest_feasible(F.itl, abl, abl["targetITL"])
    ablation = {
        "params": abl,
        "nc_max": max(abl_ncs),
        "nc_jump_batch_sizes": abl_jumps[:8],
        "M_ITL_closed_form": abl_cf,
        "M_ITL_brute": abl_brute,
        "M_ITL_exact_match": (abl_cf == abl_brute),
        "itl_monotonic": all(F.itl(B, abl) < F.itl(B + 1, abl) for B in range(M_MIN, M_MAX)),
    }

    # --- Gate summaries (the falsifiable arm checks) ---
    dev = per_scenario
    gates = {
        # h-main: ITL closed form exact on every dev scenario (nc=1 -> affine exact)
        "h_main_itl_closed_form_exact_all": all(v["M_ITL_exact_match"] for v in dev.values()),
        "h_main_all_monotonic": all(
            v["itl_monotonic"] and v["ttft_prefill_monotonic"] and v["tau_monotonic"]
            for v in dev.values()
        ),
        # h-control-negative: unbounded -> no constraint binds -> predictor = M_max
        "h_control_unbounded_no_itl_bind": (not dev["unbounded"]["itl_binds_in_range"]),
        "h_control_unbounded_M_ITL_is_max": (dev["unbounded"]["M_ITL_closed_form"] == M_MAX),
        # h-robustness: saturation monotone+concave, below analytic ceiling
        "h_robustness_sat_concave_all": all(v["sat_concave"] for v in dev.values()),
        "h_robustness_sat_below_ceiling_all": all(
            v["sat_256_over_ceiling"] is not None and v["sat_256_over_ceiling"] < 1.0
            for v in dev.values()
        ),
        # h-ablation: removing nc=1 (high input) breaks closed-form exactness
        "h_ablation_nc_gt_1": (ablation["nc_max"] > 1),
        "h_ablation_closed_form_breaks": (not ablation["M_ITL_exact_match"]),
    }

    out = {
        "iteration": 1,
        "stage": "observe",
        "oracle_calls": 0,
        "truth_cache_reads": 0,
        "per_scenario": per_scenario,
        "ablation_high_input": ablation,
        "gates": gates,
    }
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2)
    print(json.dumps(gates, indent=2))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
