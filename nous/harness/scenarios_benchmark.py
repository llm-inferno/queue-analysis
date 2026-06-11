"""Generate the benchmark grid as a Latin-hypercube sample over the campaign
parameter ranges.

beta and gamma are reconstructed on the realistic-ratio manifold:
    beta  = alpha * (beta/alpha sample)
    gamma = alpha * (gamma/alpha sample)
so reproducibility is a function of (ranges, sampler, seed=42), not a hand list.

    python -m nous.harness.scenarios_benchmark --n 30 --seed 42 \
        --out nous/scenarios_benchmark.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scipy.stats import qmc

REPO_ROOT = Path(__file__).resolve().parents[2]

# Discrete choice sets from the parameter-ranges spec.
ALPHA = [4.0, 8.0, 16.0]
BETA_RATIO = [1 / 400, 1 / 240, 1 / 120]
GAMMA_RATIO = [1 / 40000, 1 / 24000, 1 / 12000]
L_IN = [64, 256, 1024, 4096]
L_OUT = [64, 256, 1024, 4096]
T_ITL = [15.0, 20.0, 30.0, 40.0, 60.0]
T_TTFT = [30.0, 60.0, 120.0, 200.0, 400.0]
Q = [4, 32, 128]

# Order of the 8 LHS dimensions; each maps a unit-interval sample to an index
# into the choice set above.
_DIMS = [ALPHA, BETA_RATIO, GAMMA_RATIO, L_IN, L_OUT, T_ITL, T_TTFT, Q]


def _pick(choices: list, u: float):
    """Map u in [0,1) to a choice index."""
    idx = min(int(u * len(choices)), len(choices) - 1)
    return choices[idx]


def generate(n: int = 30, seed: int = 42) -> list[dict]:
    sampler = qmc.LatinHypercube(d=len(_DIMS), seed=seed)
    sample = sampler.random(n=n)
    recs: list[dict] = []
    for i, row in enumerate(sample):
        alpha = _pick(ALPHA, row[0])
        beta_ratio = _pick(BETA_RATIO, row[1])
        gamma_ratio = _pick(GAMMA_RATIO, row[2])
        recs.append({
            "name": f"bench-{i:03d}",
            "regime": "bench",
            "alpha": alpha,
            "beta": round(alpha * beta_ratio, 6),
            "gamma": round(alpha * gamma_ratio, 8),
            "AvgInputTokens": _pick(L_IN, row[3]),
            "AvgOutputTokens": _pick(L_OUT, row[4]),
            "targetITL": _pick(T_ITL, row[5]),
            "targetTTFT": _pick(T_TTFT, row[6]),
            "maxQueueSize": _pick(Q, row[7]),
        })
    return recs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path,
                    default=REPO_ROOT / "nous" / "scenarios_benchmark.json")
    args = ap.parse_args()
    recs = generate(n=args.n, seed=args.seed)
    args.out.write_text(json.dumps(
        {"search_range": {"m_min": 1, "m_max": 256}, "scenarios": recs}, indent=2))
    print(f"wrote {len(recs)} benchmark scenarios to {args.out}")


if __name__ == "__main__":
    main()
