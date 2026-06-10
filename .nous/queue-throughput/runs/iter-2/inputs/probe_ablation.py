"""Ablation probe: characterize f(M) shape with single active constraint.

Queries the oracle directly for baseline scenario parameters with one
constraint relaxed (set to 9999). Outputs shape characterization JSON.
"""
import json
import requests
import sys

BASE_URL = "http://localhost:8080/target"
BASELINE = {
    "AvgInputTokens": 256,
    "AvgOutputTokens": 512,
    "alpha": 12,
    "beta": 0.05,
    "gamma": 0.0005,
    "maxQueueSize": 128,
}

M_RANGE = list(range(2, 257))


def query(m: int, target_ttft: float, target_itl: float) -> dict | None:
    body = {**BASELINE, "RPS": 0.0, "maxBatchSize": m,
            "targetTTFT": target_ttft, "targetITL": target_itl}
    resp = requests.post(BASE_URL, json=body, timeout=10)
    if resp.status_code == 400:
        return None
    resp.raise_for_status()
    return resp.json()


def scan(target_ttft: float, target_itl: float) -> list[dict]:
    curve = []
    for m in M_RANGE:
        r = query(m, target_ttft, target_itl)
        if r is None:
            curve.append({"m": m, "throughput": 0.0, "infeasible": True})
        else:
            curve.append({"m": m, "throughput": r["throughput"],
                          "RPSTargetTTFT": r["RPSTargetTTFT"],
                          "RPSTargetITL": r["RPSTargetITL"]})
    return curve


def characterize(curve: list[dict]) -> dict:
    feasible = [c for c in curve if c["throughput"] > 0]
    if not feasible:
        return {"peak_m": None, "peak_throughput": 0.0, "is_monotone": False}
    peak = max(feasible, key=lambda c: c["throughput"])
    # Check monotonicity (ignoring infeasible)
    is_monotone = all(
        feasible[i]["throughput"] <= feasible[i + 1]["throughput"]
        for i in range(len(feasible) - 1)
    )
    # Plateau: is the drop from peak to end < 0.1%?
    last_t = feasible[-1]["throughput"]
    has_plateau = (peak["throughput"] - last_t) / peak["throughput"] < 0.001
    return {
        "peak_m": peak["m"],
        "peak_throughput": peak["throughput"],
        "is_monotone": is_monotone,
        "has_plateau_to_end": has_plateau,
        "end_throughput": last_t,
        "drop_from_peak_pct": (peak["throughput"] - last_t) / peak["throughput"] * 100,
    }


results = {}

# ITL-only: targetTTFT=9999
print("Scanning ITL-only (targetTTFT=9999)...", file=sys.stderr)
itl_curve = scan(9999.0, 20.0)
results["itl_only"] = {
    "description": "baseline with targetTTFT=9999 (only ITL active)",
    "characterization": characterize(itl_curve),
    "sample_points": [c for c in itl_curve if c["m"] in [2, 5, 10, 20, 25, 26, 30, 40, 50, 100, 200, 256]],
}

# TTFT-only: targetITL=9999
print("Scanning TTFT-only (targetITL=9999)...", file=sys.stderr)
ttft_curve = scan(60.0, 9999.0)
results["ttft_only"] = {
    "description": "baseline with targetITL=9999 (only TTFT active)",
    "characterization": characterize(ttft_curve),
    "sample_points": [c for c in ttft_curve if c["m"] in [2, 5, 10, 20, 30, 40, 50, 100, 200, 256]],
}

# Both active (reference)
print("Scanning both active (reference)...", file=sys.stderr)
both_curve = scan(60.0, 20.0)
results["both_active"] = {
    "description": "baseline with both constraints active (reference)",
    "characterization": characterize(both_curve),
}

print(json.dumps(results, indent=2))
