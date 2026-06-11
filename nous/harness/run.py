"""Harness CLI: orchestrate one strategy across all scenarios.

    python -m nous.harness.run \
        --scenarios nous/scenarios.json \
        --strategy nous/harness/strategies/<name>.py \
        --m-min 1 --m-max 256 \
        --out nous/results/<arm>.json

For each scenario it spawns the Go analyzer once, runs the strategy,
records (calls, M_chosen, throughput, gap), kills the analyzer, and
writes one JSON file containing a list of records.
"""

from __future__ import annotations
import argparse
import importlib.util
import json
import time
from pathlib import Path
from typing import Callable

from nous.harness.oracle import make_oracle
from nous.harness.scenarios import Scenario, load_campaign
from nous.harness.scoring import ScenarioResult, compute_gap
from nous.harness.server import AnalyzerServer


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_strategy(path: str | Path) -> Callable[[Callable[[int], dict], int, int], int]:
    """Import a Python file by path and return its `search` callable."""
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(f"strategy_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "search"):
        raise AttributeError(f"{path} must define a top-level `search(target_eval, m_min, m_max) -> int`")
    return module.search


def load_truth_for(scenario_name: str, cache_dir: Path) -> dict:
    fp = cache_dir / f"truth-{scenario_name}.json"
    if not fp.exists():
        raise FileNotFoundError(
            f"missing truth cache {fp}; run baseline_truth.py first"
        )
    return json.loads(fp.read_text())


def run_strategy_on_scenario(
    *,
    base_url: str,
    scenario: Scenario,
    search: Callable[[Callable[[int], dict], int, int], int],
    m_min: int,
    m_max: int,
    truth: dict,
    strategy_name: str,
) -> ScenarioResult:
    """Run one strategy against one scenario; return a scored ScenarioResult.

    Note: this harness always makes one extra confirmatory eval_(m_chosen) call
    after the strategy returns, so the recorded throughput_chosen is the
    analyzer's reading at the chosen M. That extra call IS counted in
    `result.calls` (calls = strategy_calls + 1). Strategy authors comparing
    call budgets should account for this constant overhead.
    """
    eval_, stats = make_oracle(base_url, scenario)
    t0 = time.monotonic()
    m_chosen = int(search(eval_, m_min, m_max))
    if not (m_min <= m_chosen <= m_max):
        raise ValueError(f"strategy returned M={m_chosen} outside [{m_min}, {m_max}]")
    elapsed = time.monotonic() - t0
    final = eval_(m_chosen)  # one extra confirmatory call so we record the throughput at chosen M
    throughput_chosen = float(final["throughput"])
    gap = compute_gap(
        m_chosen=m_chosen, throughput_chosen=throughput_chosen,
        m_truth=int(truth["M_truth"]), throughput_truth=float(truth["throughput_truth"]),
    )
    return ScenarioResult(
        scenario=scenario.name,
        strategy=strategy_name,
        M_chosen=m_chosen,
        calls=stats.calls,
        throughput_chosen=throughput_chosen,
        M_truth=int(truth["M_truth"]),
        throughput_truth=float(truth["throughput_truth"]),
        gap_throughput_rel=gap["gap_throughput_rel"],
        gap_M=gap["gap_M"],
        wall_clock_seconds=elapsed,
        internal_solve_calls=0,  # not reported by /target; left at 0 for now
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", required=True, type=Path)
    ap.add_argument("--strategy", required=True, type=Path)
    ap.add_argument("--m-min", type=int, default=None)
    ap.add_argument("--m-max", type=int, default=None)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cache-dir", type=Path, default=REPO_ROOT / "nous" / "cache")
    ap.add_argument("--repo-dir", type=Path, default=REPO_ROOT)
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    config = load_campaign(args.scenarios)
    m_min = args.m_min if args.m_min is not None else config.m_min
    m_max = args.m_max if args.m_max is not None else config.m_max
    search = load_strategy(args.strategy)
    strategy_name = args.strategy.stem

    args.out.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    with AnalyzerServer(repo_dir=args.repo_dir, port=args.port) as base_url:
        for scenario in config.scenarios:
            truth = load_truth_for(scenario.name, args.cache_dir)
            result = run_strategy_on_scenario(
                base_url=base_url, scenario=scenario, search=search,
                m_min=m_min, m_max=m_max, truth=truth,
                strategy_name=strategy_name,
            )
            records.append(result.to_dict())
            print(f"[{scenario.name}] M={result.M_chosen} calls={result.calls} "
                  f"gap_rel={result.gap_throughput_rel:.4f}")
    args.out.write_text(json.dumps(records, indent=2))
    print(f"wrote {len(records)} records to {args.out}")


if __name__ == "__main__":
    main()
