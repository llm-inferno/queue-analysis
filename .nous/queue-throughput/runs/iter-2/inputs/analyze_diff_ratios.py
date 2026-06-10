"""Analyze first-difference ratios at crossover for robustness arm."""
import json
import sys
from pathlib import Path

CACHE_DIR = Path("nous/cache")
SCENARIOS_WITH_CROSSOVER = ["baseline", "long-loose-itl", "small-queue"]

results = []

for name in SCENARIOS_WITH_CROSSOVER:
    d = json.loads((CACHE_DIR / f"truth-{name}.json").read_text())
    curve = d["f_curve"]
    M_truth = d["M_truth"]
    f_truth = d["throughput_truth"]
    by_m = {c["m"]: c["throughput"] for c in curve}

    diffs = {}
    for m in range(2, 257):
        if m in by_m and m - 1 in by_m:
            diffs[m] = by_m[m] - by_m[m - 1]

    # Ratio at crossover
    ratio_at_star = diffs[M_truth] / diffs[M_truth - 1] if diffs.get(M_truth - 1, 0) != 0 else None

    # Normal concavity ratios (M* - 10 to M* - 1)
    normal_ratios = []
    for m in range(max(3, M_truth - 10), M_truth):
        if m in diffs and m - 1 in diffs and diffs[m - 1] != 0:
            normal_ratios.append(diffs[m] / diffs[m - 1])

    results.append({
        "scenario": name,
        "M_truth": M_truth,
        "ratio_at_crossover": ratio_at_star,
        "normal_concavity_ratios": {
            "min": min(normal_ratios) if normal_ratios else None,
            "max": max(normal_ratios) if normal_ratios else None,
            "mean": sum(normal_ratios) / len(normal_ratios) if normal_ratios else None,
        },
        "crossover_detectable": ratio_at_star is not None and ratio_at_star < 0.55,
        "separation": (min(normal_ratios) - ratio_at_star) if normal_ratios and ratio_at_star else None,
    })

print(json.dumps(results, indent=2))
