"""Test the closed-form M* predictor across all scenarios.

Predictor formula:
    n_ITL = (targetITL - d_intercept) / d_slope
    wait_budget = targetTTFT - targetITL - PrefillTime(n_ITL)
    M_est = round(n_ITL + 3.0 * sqrt(n_ITL) + 0.05 * wait_budget)

    Crossover detection: wait_budget > 0

Where:
    d_slope = beta * tc + gamma * tm
    tc = (avgIn + avgOut) / (avgOut + 1)
    tm = avgIn + avgOut / 2
    d_intercept = alpha + beta + gamma * (avgIn + (avgOut+1)/2)
    PrefillTime(n) = alpha + n * d_slope + (beta + gamma) * avgIn

Usage:
    python .nous/queue-throughput/runs/iter-3/inputs/run_predictor.py [--no-wait-budget]

Output: JSON with per-scenario predictions and accuracy metrics.
"""

import json
import math
import sys
from pathlib import Path

ALPHA, BETA, GAMMA = 12.0, 0.05, 0.0005

CACHE_DIR = Path(__file__).resolve().parents[5] / "nous" / "cache"

SCENARIOS = [
    {"name": "baseline", "avgIn": 256, "avgOut": 512, "tITL": 20, "tTTFT": 60, "qSize": 128},
    {"name": "short-tight-ttft", "avgIn": 128, "avgOut": 256, "tITL": 20, "tTTFT": 35, "qSize": 128},
    {"name": "long-loose-itl", "avgIn": 256, "avgOut": 1024, "tITL": 40, "tTTFT": 200, "qSize": 128},
    {"name": "small-queue", "avgIn": 256, "avgOut": 512, "tITL": 20, "tTTFT": 60, "qSize": 4},
]


def predict_m_star(avgIn, avgOut, tITL, tTTFT, wait_budget_coeff=0.05):
    """Closed-form predictor for M*.

    Returns: (M_est, has_crossover, n_ITL, wait_budget, components)
    """
    tc = (avgIn + avgOut) / (avgOut + 1)
    tm = avgIn + avgOut / 2
    d_slope = BETA * tc + GAMMA * tm
    d_intercept = ALPHA + BETA + GAMMA * (avgIn + (avgOut + 1) / 2)
    n_ITL = (tITL - d_intercept) / d_slope

    pt_n = ALPHA + n_ITL * d_slope + (BETA + GAMMA) * avgIn
    wait_budget = tTTFT - tITL - pt_n

    has_crossover = wait_budget > 0

    if not has_crossover:
        return None, False, n_ITL, wait_budget, {
            "tc": tc, "tm": tm, "d_slope": d_slope, "d_intercept": d_intercept,
            "PT_n_ITL": pt_n,
        }

    M_est = round(n_ITL + 3.0 * math.sqrt(n_ITL) + wait_budget_coeff * wait_budget)
    return M_est, True, n_ITL, wait_budget, {
        "tc": tc, "tm": tm, "d_slope": d_slope, "d_intercept": d_intercept,
        "PT_n_ITL": pt_n, "sqrt_n_ITL": math.sqrt(n_ITL),
        "base_term": n_ITL, "buffer_term": 3.0 * math.sqrt(n_ITL),
        "wait_term": wait_budget_coeff * wait_budget,
    }


def load_truth(scenario_name):
    fp = CACHE_DIR / f"truth-{scenario_name}.json"
    if not fp.exists():
        return None
    return json.loads(fp.read_text())


def main():
    no_wait_budget = "--no-wait-budget" in sys.argv
    wait_budget_coeff = 0.0 if no_wait_budget else 0.05

    results = []
    for s in SCENARIOS:
        truth = load_truth(s["name"])
        M_truth = truth["M_truth"] if truth else None

        M_est, has_crossover, n_ITL, wait_budget, components = predict_m_star(
            s["avgIn"], s["avgOut"], s["tITL"], s["tTTFT"],
            wait_budget_coeff=wait_budget_coeff,
        )

        error = abs(M_est - M_truth) if (M_est is not None and M_truth is not None) else None

        results.append({
            "scenario": s["name"],
            "M_truth": M_truth,
            "M_est": M_est,
            "has_crossover_predicted": has_crossover,
            "n_ITL": round(n_ITL, 4),
            "wait_budget_ms": round(wait_budget, 4),
            "error_abs": error,
            "within_5": error is not None and error <= 5,
            "wait_budget_coeff": wait_budget_coeff,
            "components": {k: round(v, 4) for k, v in components.items()},
        })

    output = {
        "mode": "ablation_no_wait_budget" if no_wait_budget else "full_predictor",
        "formula": "M_est = round(n_ITL + 3.0*sqrt(n_ITL) + {:.2f}*wait_budget)".format(wait_budget_coeff),
        "results": results,
        "summary": {
            "crossover_scenarios": [r for r in results if r["has_crossover_predicted"]],
            "no_crossover_scenarios": [r for r in results if not r["has_crossover_predicted"]],
            "max_error": max((r["error_abs"] for r in results if r["error_abs"] is not None), default=None),
            "all_within_5": all(r["within_5"] for r in results if r["error_abs"] is not None),
        },
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
