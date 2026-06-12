"""Offline replay of the committed onset-search strategies against the truth
caches, for the paper's Experiments section. No Go server: the truth cache is
the analytic oracle tabulated at every M in [1, 256], so a cache lookup IS the
oracle value. Deterministic strategies => exact reproduction of M_chosen/calls.

Outputs paper/data/eval_results.json (per-scenario records + aggregates).
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))  # so `nous` (pure-stdlib formulas/strategies) imports

DATA_DIR = REPO / "paper" / "data"
EPS = 0.02
M_MIN, M_MAX = 1, 256
PARAM_KEYS = ("alpha", "beta", "gamma", "AvgInputTokens", "AvgOutputTokens",
              "targetITL", "targetTTFT", "maxQueueSize")


def cache_oracle(f_curve: list[dict]):
    """Return (target_eval, stats). Mirrors nous/harness/oracle.py: an
    infeasible reading (throughput <= 0) is uncounted; every probe is recorded."""
    f = {pt["m"]: pt["throughput"] for pt in f_curve}
    stats = {"calls": 0, "probes": []}

    def target_eval(m: int) -> dict:
        stats["probes"].append(m)
        thr = f.get(m, 0.0)
        if thr > 0.0:
            stats["calls"] += 1
        return {"throughput": thr}

    return target_eval, stats


def epsilon_onset(f_curve: list[dict], eps: float = EPS):
    """Smallest m with f(m) >= (1-eps)*peak; None if the scenario is infeasible."""
    f = {pt["m"]: pt["throughput"] for pt in f_curve}
    peak = max(f.values())
    if peak <= 0.0:
        return None
    thresh = (1.0 - eps) * peak
    for m in sorted(f):
        if f[m] >= thresh:
            return m
    return max(f)


def replay(search, params: dict, cache: dict, m_min: int = M_MIN, m_max: int = M_MAX) -> dict:
    """Run one strategy against one cached scenario; return a scored record.

    Adds one confirmatory oracle(M_chosen) call after the strategy returns,
    matching nous/harness/run.py (so `calls` includes that +1)."""
    f_curve = cache["f_curve"]
    f = {pt["m"]: pt["throughput"] for pt in f_curve}
    M_truth = int(cache["M_truth"])
    f_truth = float(cache["throughput_truth"])
    onset = epsilon_onset(f_curve)
    onset_eff = onset if onset is not None else M_truth

    ev, stats = cache_oracle(f_curve)
    m_chosen = int(search(ev, params, m_min, m_max))
    if not (m_min <= m_chosen <= m_max):
        raise ValueError(f"strategy returned M={m_chosen} outside [{m_min}, {m_max}]")
    thr_chosen = ev(m_chosen)["throughput"]  # confirmatory (counted if feasible)

    gap_f = max((f_truth - thr_chosen) / f_truth, 0.0) if f_truth > 0 else 0.0
    return {
        "M_chosen": m_chosen,
        "calls": stats["calls"],
        "probes": list(stats["probes"]),
        "throughput_chosen": thr_chosen,
        "M_onset": onset_eff,
        "M_truth": M_truth,
        "throughput_truth": f_truth,
        "feasible": f_truth > 0,
        "gap_onset": abs(m_chosen - onset_eff),
        "gap_argmax": abs(m_chosen - M_truth),
        "gap_f": gap_f,
    }


from nous.harness.strategies import formula_guided, naive_max, naive_ternary

STRATEGIES = {
    "formula_guided": formula_guided.search,
    "naive_ternary": naive_ternary.search,
    "naive_max": naive_max.search,
}


def _load_set(scenarios_path: Path, cache_for):
    scns = json.loads(scenarios_path.read_text())["scenarios"]
    out = []
    for s in scns:
        params = {k: s[k] for k in PARAM_KEYS}
        cache = json.loads(cache_for(s["name"]).read_text())
        out.append((s["name"], params, cache))
    return out


def _aggregate(records: list[dict]) -> dict:
    """Worst/mean gaps over the FEASIBLE records only, per strategy."""
    by_strat: dict[str, list[dict]] = {}
    for r in records:
        by_strat.setdefault(r["strategy"], []).append(r)
    agg = {}
    n_feasible = None
    for strat, recs in by_strat.items():
        feas = [r for r in recs if r["feasible"]]
        n_feasible = len(feas)
        agg[strat] = {
            "calls_worst": max(r["calls"] for r in feas),
            "gap_onset_worst": max(r["gap_onset"] for r in feas),
            "gap_onset_mean": round(statistics.mean(r["gap_onset"] for r in feas), 2),
            "gap_f_worst": round(max(r["gap_f"] for r in feas), 4),
            "gap_argmax_worst": max(r["gap_argmax"] for r in feas),
        }
    agg["n_scenarios"] = n_feasible
    return agg


def evaluate_all() -> dict:
    dev = _load_set(REPO / "nous" / "scenarios.json",
                    lambda n: REPO / "nous" / "cache" / f"truth-{n}.json")
    bench = _load_set(REPO / "nous" / "scenarios_benchmark.json",
                      lambda n: REPO / "nous" / "cache" / "bench" / f"{n}.json")

    records = []
    for setname, dataset in (("dev", dev), ("benchmark", bench)):
        for name, params, cache in dataset:
            for strat, search in STRATEGIES.items():
                rec = replay(search, params, cache)
                rec.update(strategy=strat, scenario=name, set=setname,
                           regime=cache.get("regime", ""))
                rec.pop("probes", None)  # keep JSON compact; trace recomputed for the figure
                records.append(rec)

    aggregates = {
        "dev": _aggregate([r for r in records if r["set"] == "dev"]),
        "benchmark": _aggregate([r for r in records if r["set"] == "benchmark"]),
    }
    return {"eps": EPS, "records": records, "aggregates": aggregates}


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = evaluate_all()
    (DATA_DIR / "eval_results.json").write_text(json.dumps(out, indent=2))
    b = out["aggregates"]["benchmark"]["formula_guided"]
    print(f"wrote eval_results.json; formula_guided bench: calls<={b['calls_worst']} "
          f"gap_onset {b['gap_onset_worst']}/{b['gap_onset_mean']} "
          f"gap_f {b['gap_f_worst']} gap_argmax {b['gap_argmax_worst']}")


if __name__ == "__main__":
    main()
