"""Probe the predictor M_est accuracy across all scenarios.

Computes M_est from the closed-form formula, then checks the ratio R(M_est)
to measure how close the predictor lands to the actual crossover.
"""

import json
import math
import subprocess
import time

import requests

SCENARIOS = [
    {"name": "baseline", "avgIn": 256, "avgOut": 512, "tITL": 20, "tTTFT": 60, "qSize": 128, "M_truth": 40},
    {"name": "long-loose-itl", "avgIn": 256, "avgOut": 1024, "tITL": 40, "tTTFT": 200, "qSize": 128, "M_truth": 93},
    {"name": "small-queue", "avgIn": 256, "avgOut": 512, "tITL": 20, "tTTFT": 60, "qSize": 4, "M_truth": 38},
    {"name": "short-tight-ttft", "avgIn": 128, "avgOut": 256, "tITL": 20, "tTTFT": 35, "qSize": 128, "M_truth": 69},
]

ALPHA, BETA, GAMMA = 12.0, 0.05, 0.0005


def predict_m_star(avgIn, avgOut, tITL, tTTFT):
    """Closed-form predictor for M*. Returns (M_est, has_crossover)."""
    tc = (avgIn + avgOut) / (avgOut + 1)
    tm = avgIn + avgOut / 2
    d_slope = BETA * tc + GAMMA * tm
    d_intercept = ALPHA + BETA + GAMMA * (avgIn + (avgOut + 1) / 2)
    n_ITL = (tITL - d_intercept) / d_slope

    pt_n = ALPHA + n_ITL * d_slope + (BETA + GAMMA) * avgIn
    wait_budget = tTTFT - tITL - pt_n

    if wait_budget <= 0:
        return None, False

    M_est = round(n_ITL + 3.0 * math.sqrt(n_ITL) + 0.05 * wait_budget)
    return M_est, True


def main():
    results = []
    for s in SCENARIOS:
        M_est, has_crossover = predict_m_star(s["avgIn"], s["avgOut"], s["tITL"], s["tTTFT"])
        results.append({
            "scenario": s["name"],
            "M_truth": s["M_truth"],
            "M_est": M_est,
            "has_crossover": has_crossover,
            "error": abs(M_est - s["M_truth"]) if M_est is not None else None,
        })
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
