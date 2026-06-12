"""One-shot /target sweep over M in [1, 256] for the baseline scenario.

Caches RPSTargetTTFT, RPSTargetITL, throughput per M to
paper/data/baseline_lambda_sweep.json so figure scripts run without
hitting the analyzer. Requires the queue-analysis Go server on :8080
(`go run main.go` from the repo root).

scenarios.json is an object {search_range, scenarios:[...]} with per-scenario
alpha/beta/gamma; /target uses camelCase request/response fields
(see pkg/service/analyzer.go).
"""
import json
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
SCN = json.loads((REPO / "nous" / "scenarios.json").read_text())
OUT = REPO / "paper" / "data" / "baseline_lambda_sweep.json"
URL = "http://localhost:8080/target"
M_MIN, M_MAX = 1, 256


def main() -> int:
    baseline = next(s for s in SCN["scenarios"] if s["name"] == "baseline")
    base_payload = {
        "avgInputTokens": baseline["AvgInputTokens"],
        "avgOutputTokens": baseline["AvgOutputTokens"],
        "alpha": baseline["alpha"],
        "beta": baseline["beta"],
        "gamma": baseline["gamma"],
        "maxQueueSize": baseline["maxQueueSize"],
        "targetTTFT": baseline["targetTTFT"],
        "targetITL": baseline["targetITL"],
    }

    rows = []
    for m in range(M_MIN, M_MAX + 1):
        payload = dict(base_payload, maxBatchSize=m)
        r = requests.post(URL, json=payload, timeout=30)
        if r.status_code == 400:
            rows.append({"m": m, "infeasible": True})
            continue
        r.raise_for_status()
        body = r.json()
        for key in ("throughput", "RPSTargetTTFT", "RPSTargetITL"):
            if body.get(key) is None:
                raise RuntimeError(f"M={m}: /target response missing '{key}': {body}")
        rows.append({
            "m": m,
            "infeasible": False,
            "throughput": body["throughput"],
            "RPSTargetTTFT": body["RPSTargetTTFT"],
            "RPSTargetITL": body["RPSTargetITL"],
        })
        if m % 32 == 0:
            print(f"  M={m}: lam_TTFT={body['RPSTargetTTFT']:.4f}  "
                  f"lam_ITL={body['RPSTargetITL']:.4f}  f={body['throughput']:.4f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"scenario": "baseline", "rows": rows}, indent=2))
    print(f"\nWrote {len(rows)} rows to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
