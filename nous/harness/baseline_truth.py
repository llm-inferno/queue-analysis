"""One-time brute-force scan to compute M* and f(M*) per scenario.

Writes <cache-dir>/truth-<name>.json:
    {"scenario": "...", "M_truth": ..., "throughput_truth": ...,
     "f_curve": [{"m": 1, "throughput": ...}, ...]}

Re-run only when scenarios.json changes.
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path

from nous.harness.oracle import make_oracle
from nous.harness.scenarios import load_campaign
from nous.harness.server import AnalyzerServer


REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=Path, default=REPO_ROOT / "nous" / "scenarios.json")
    ap.add_argument("--cache-dir", type=Path, default=REPO_ROOT / "nous" / "cache")
    ap.add_argument("--repo-dir", type=Path, default=REPO_ROOT)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--m-min", type=int, default=None)
    ap.add_argument("--m-max", type=int, default=None)
    args = ap.parse_args()

    config = load_campaign(args.scenarios)
    m_min = args.m_min if args.m_min is not None else config.m_min
    m_max = args.m_max if args.m_max is not None else config.m_max
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    with AnalyzerServer(repo_dir=args.repo_dir, port=args.port) as base_url:
        for s in config.scenarios:
            eval_, stats = make_oracle(base_url, s)
            curve = []
            best_m, best_t = m_min, 0.0  # 0 matches the oracle's infeasibility convention
            for m in range(m_min, m_max + 1):
                out = eval_(m)
                t = float(out["throughput"])
                curve.append({"m": m, "throughput": t})
                if t > best_t:
                    best_t, best_m = t, m
            payload = {
                "scenario": s.name,
                "M_truth": best_m,
                "throughput_truth": best_t,
                "f_curve": curve,
            }
            (args.cache_dir / f"truth-{s.name}.json").write_text(json.dumps(payload, indent=2))
            print(f"[{s.name}] M*={best_m} f*={best_t:.4f}  (calls={stats.calls})")


if __name__ == "__main__":
    main()
