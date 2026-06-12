#!/usr/bin/env python3
"""Iter-2 (observe) validation of the regime partition + boundary equations.

NO oracle (/target) calls and NO truth-cache reads. Every claim is checked
purely against nous/harness/formulas.py, the parity-checked port of the Go
analyzer primitives. This script is the iter-2 "experiment": it confirms which
regime cells are decidable from the analytic primitives alone, derives the
closed-form cell boundaries, and shows exactly where the primitive partition is
insufficient (and why the queue-wait term — only available via the oracle in
iter-3 — is required to finish the split).

Partition (primitive-decidable cells):
    itl_binds      = itl(M_MAX) > targetITL
    ttft_pf_binds  = ttft_prefill(M_MAX) > targetTTFT
    M_ITL = largest B with itl(B) <= targetITL      (LOWER bound on ITL-binding M*)
    M_TPF = largest B with ttft_prefill(B) <= targetTTFT  (UPPER bound on TTFT-binding M*)

    cell(params):
        unbounded         if not itl_binds and not ttft_pf_binds      -> M-hat = M_MAX
        ttft-only         elif M_TPF < M_ITL                          -> M-hat = M_TPF
        itl-or-crossover  else (M_ITL <= M_TPF, at least one binds)    -> bracket [M_ITL, min(M_TPF,M_MAX)]

The "ttft-only" rule is PROVABLE from the bound directions: M_TPF < M_ITL implies
true_TTFT_M <= M_TPF < M_ITL <= true_ITL_M, so TTFT strictly binds first. The
"itl-or-crossover" cell is FUSED: itl-only and crossover are primitive-
indistinguishable (the queue-wait term decides), so it is left as one cell here.

Usage (run from repo root, or anywhere — the script self-locates):
    python3 .nous/queue-throughput-formulas/runs/iter-2/inputs/validate_regimes.py \
        --scenarios nous/scenarios.json \
        --out .nous/queue-throughput-formulas/runs/iter-2/results/baseline.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_d = os.path.abspath(os.path.dirname(__file__))
while _d != "/" and not os.path.exists(os.path.join(_d, "nous", "harness", "formulas.py")):
    _d = os.path.dirname(_d)
if _d not in sys.path:
    sys.path.insert(0, _d)

from nous.harness import formulas as F  # noqa: E402

M_MIN, M_MAX = 1, 256


def brute_largest_feasible(metric, params: dict, target: float):
    feas = [B for B in range(M_MIN, M_MAX + 1) if metric(B, params) <= target]
    return max(feas) if feas else None


def classify(params: dict) -> dict:
    """Primitive-only regime classification + per-cell M-hat."""
    i256 = F.itl(M_MAX, params)
    t256 = F.ttft_prefill(M_MAX, params)
    itl_binds = i256 > params["targetITL"]
    ttft_pf_binds = t256 > params["targetTTFT"]

    M_ITL = brute_largest_feasible(F.itl, params, params["targetITL"])
    M_TPF = brute_largest_feasible(F.ttft_prefill, params, params["targetTTFT"])
    # When a constraint never binds the brute scan returns M_MAX (clamped).
    M_ITL_c = M_ITL if M_ITL is not None else M_MIN
    M_TPF_c = M_TPF if M_TPF is not None else M_MIN

    if (not itl_binds) and (not ttft_pf_binds):
        cell = "unbounded"
        m_hat = M_MAX
        bracket = [M_MAX, M_MAX]
    elif M_TPF_c < M_ITL_c:
        cell = "ttft-only"
        m_hat = M_TPF_c                       # upper bound; queue-wait pulls it down (iter-3)
        bracket = [M_MIN, M_TPF_c]
    else:
        cell = "itl-or-crossover"             # FUSED: itl-only vs crossover undecidable here
        m_hat = M_ITL_c                        # lower bound / bracket start
        bracket = [M_ITL_c, min(M_TPF_c, M_MAX)]

    return {
        "itl_binds": itl_binds,
        "ttft_pf_binds": ttft_pf_binds,
        "M_ITL": M_ITL_c,
        "M_TPF": M_TPF_c,
        "M_TPF_lt_M_ITL": M_TPF_c < M_ITL_c,
        "cell": cell,
        "m_hat": m_hat,
        "bracket": bracket,
        # primitive "signature": what a primitive-only classifier can observe
        "primitive_signature": [int(itl_binds), int(ttft_pf_binds),
                                 int(M_TPF_c > M_ITL_c) - int(M_TPF_c < M_ITL_c)],
    }


def naive_2x2(params: dict) -> str:
    """Ablation: classify using ONLY the two binding booleans (no M_TPF<M_ITL order)."""
    i256 = F.itl(M_MAX, params)
    t256 = F.ttft_prefill(M_MAX, params)
    a = i256 > params["targetITL"]
    b = t256 > params["targetTTFT"]
    return {(False, False): "unbounded", (True, False): "itl-only",
            (False, True): "ttft-only", (True, True): "crossover"}[(a, b)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    scen = json.load(open(args.scenarios))["scenarios"]
    per = {}
    for s in scen:
        p = dict(s)
        c = classify(p)
        c["regime_label"] = s.get("regime")
        c["naive_2x2_label"] = naive_2x2(p)
        per[s["name"]] = c

    # ---- Boundary equation 1: unbounded<->ITL-bound threshold (closed form) ----
    # targetITL* = itl(1) + (M_MAX-1)*delta(1)   (nc=1) must equal itl(M_MAX).
    bnd_itl = {}
    for s in scen:
        p = dict(s)
        d1 = F.delta(1, p)
        thr = F.itl(1, p) + (M_MAX - 1) * d1
        bnd_itl[s["name"]] = {"closed_form_thr": thr, "itl_256": F.itl(M_MAX, p),
                              "abs_err": abs(thr - F.itl(M_MAX, p))}

    # ---- Boundary equation 2: ttft-only cell turns on when targetTTFT < ttft_prefill(M_ITL) ----
    bnd_ttft = {}
    for s in scen:
        p = dict(s)
        M_ITL = brute_largest_feasible(F.itl, p, p["targetITL"]) or M_MIN
        tpf_at = F.ttft_prefill(M_ITL, p)
        M_TPF = brute_largest_feasible(F.ttft_prefill, p, p["targetTTFT"]) or M_MIN
        bnd_ttft[s["name"]] = {
            "M_ITL": M_ITL, "ttft_pf_at_M_ITL": tpf_at, "targetTTFT": p["targetTTFT"],
            "order_says_ttftonly": M_TPF < M_ITL,
            "boundary_says_ttftonly": tpf_at > p["targetTTFT"],
            "iff_holds": (M_TPF < M_ITL) == (tpf_at > p["targetTTFT"]),
        }

    # ---- Perturbation: drive `baseline` across the ttft-only boundary by lowering targetTTFT ----
    base = dict(next(s for s in scen if s["name"] == "baseline"))
    M_ITL_b = brute_largest_feasible(F.itl, base, base["targetITL"]) or M_MIN
    thr_ttft = F.ttft_prefill(M_ITL_b, base)
    below = dict(base); below["targetTTFT"] = thr_ttft - 1e-3
    above = dict(base); above["targetTTFT"] = thr_ttft + 1e-3
    pert = {
        "baseline_M_ITL": M_ITL_b,
        "ttft_threshold": thr_ttft,
        "below_cell": classify(below)["cell"],     # expect "ttft-only"
        "above_cell": classify(above)["cell"],     # expect "itl-or-crossover"
        "flips_at_threshold": classify(below)["cell"] == "ttft-only"
        and classify(above)["cell"] != "ttft-only",
    }

    # ---- Gates (the falsifiable arm checks) ----
    labels = {n: per[n]["regime_label"] for n in per}

    # h-main: unbounded exact; ttft-only iff M_TPF<M_ITL; fused cell carries only itl/crossover
    h_main_unbounded_exact = all(
        (per[n]["cell"] == "unbounded") == (lab == "unbounded") for n, lab in labels.items()
    )
    h_main_ttftonly_iff_order = all(
        (per[n]["cell"] == "ttft-only") == (lab == "ttft-only") for n, lab in labels.items()
    )
    h_main_fused_only_itl_crossover = all(
        labels[n] in ("itl-only", "crossover")
        for n in per if per[n]["cell"] == "itl-or-crossover"
    )

    # h-control-negative: at least one pair of DIFFERENTLY-labelled scenarios shares the
    # primitive signature -> fused cell is irreducible from primitives (4 prim groups not enough)
    sig_to_labels: dict = {}
    for n in per:
        sig_to_labels.setdefault(tuple(per[n]["primitive_signature"]), set()).add(labels[n])
    h_control_fused_indistinguishable = any(len(v) > 1 for v in sig_to_labels.values())
    indistinct_pairs = {str(k): sorted(v) for k, v in sig_to_labels.items() if len(v) > 1}

    # h-robustness: boundary equations are closed-form / exact, and perturbation flips at thr
    h_robustness_itl_boundary_exact = all(v["abs_err"] < 1e-6 for v in bnd_itl.values())
    h_robustness_ttftonly_iff = all(v["iff_holds"] for v in bnd_ttft.values())
    h_robustness_perturbation_flips = pert["flips_at_threshold"]

    # h-ablation: dropping the M_TPF<M_ITL ordering (naive 2x2) loses the ttft-only cell
    ttft_scn = next(n for n in per if labels[n] == "ttft-only")
    h_ablation_ttftonly_lost = (
        per[ttft_scn]["naive_2x2_label"] != "ttft-only"
        and per[ttft_scn]["cell"] == "ttft-only"
    )
    naive_mismatches = {n: per[n]["naive_2x2_label"] for n in per
                        if per[n]["naive_2x2_label"] != labels[n]}

    gates = {
        "h_main_unbounded_exact": h_main_unbounded_exact,
        "h_main_ttftonly_iff_order": h_main_ttftonly_iff_order,
        "h_main_fused_only_itl_crossover": h_main_fused_only_itl_crossover,
        "h_control_fused_indistinguishable": h_control_fused_indistinguishable,
        "h_robustness_itl_boundary_exact": h_robustness_itl_boundary_exact,
        "h_robustness_ttftonly_iff": h_robustness_ttftonly_iff,
        "h_robustness_perturbation_flips": h_robustness_perturbation_flips,
        "h_ablation_ttftonly_lost_without_order": h_ablation_ttftonly_lost,
    }

    out = {
        "iteration": 2,
        "stage": "observe",
        "oracle_calls": 0,
        "truth_cache_reads": 0,
        "per_scenario": per,
        "boundary_itl_unbounded": bnd_itl,
        "boundary_ttftonly": bnd_ttft,
        "perturbation_baseline_ttft": pert,
        "naive_2x2_mismatches": naive_mismatches,
        "indistinguishable_label_sets": indistinct_pairs,
        "gates": gates,
    }
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2)
    print(json.dumps(gates, indent=2))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
