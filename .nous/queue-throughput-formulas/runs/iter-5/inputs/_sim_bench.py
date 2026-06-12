"""Offline cache-faithful simulator for the 30-scenario benchmark.

Runs the REAL strategy modules (formula_guided, naive_ternary, naive_max)
against each bench f_curve, replicating the oracle's call accounting:
  - target_eval(m) returns {"throughput": f_curve[m-1]}
  - a call counts only if throughput > 0 (HTTP 400 -> 0.0, uncounted)
  - the harness adds +1 confirmatory eval_(m_chosen), counted unless f==0

Reports M_chosen, calls, gap_M=|M_chosen-M_truth|, gap_f per scenario.
M_truth in the cache is the ARGMAX (smallest M at peak throughput).
"""
from __future__ import annotations
import importlib.util
import json
import glob
from pathlib import Path

REPO = Path("/Users/tantawi/Projects/llm-inferno/queue-analysis")
STRAT_DIR = REPO / "nous/harness/strategies"
BENCH = REPO / "nous/scenarios_benchmark.json"
CACHE = REPO / "nous/cache/bench"


def load_strategy(name):
    path = STRAT_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"strategy_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.search


def scenario_to_params(s):
    return {
        "alpha": s["alpha"], "beta": s["beta"], "gamma": s["gamma"],
        "AvgInputTokens": s["AvgInputTokens"], "AvgOutputTokens": s["AvgOutputTokens"],
        "targetITL": s["targetITL"], "targetTTFT": s["targetTTFT"],
        "maxQueueSize": s["maxQueueSize"],
    }


def make_mock(f_curve):
    stats = {"calls": 0}
    f = [d["throughput"] for d in f_curve]

    def target_eval(m):
        t = f[m - 1] if 1 <= m <= len(f) else 0.0
        if t > 0.0:
            stats["calls"] += 1
        return {"throughput": t}
    return target_eval, stats, f


def run(strategy_name):
    search = load_strategy(strategy_name)
    cfg = json.load(open(BENCH))
    m_min, m_max = cfg["search_range"]["m_min"], cfg["search_range"]["m_max"]
    out = []
    for s in cfg["scenarios"]:
        truth = json.load(open(CACHE / f"{s['name']}.json"))
        Mt = truth["M_truth"]
        ft = truth["throughput_truth"]
        target_eval, stats, f = make_mock(truth["f_curve"])
        params = scenario_to_params(s)
        m_chosen = int(search(target_eval, params, m_min, m_max))
        # harness confirmatory eval_(m_chosen)
        fin = target_eval(m_chosen)["throughput"]
        gap_M = abs(m_chosen - Mt)
        gap_f = max(0.0, (ft - fin) / ft) if ft > 0 else 0.0
        out.append({
            "scenario": s["name"], "M_chosen": m_chosen, "M_truth": Mt,
            "calls": stats["calls"], "gap_M": gap_M, "gap_f": round(gap_f, 4),
            "feasible": ft > 0,
        })
    return out


if __name__ == "__main__":
    import sys
    for strat in ["formula_guided", "naive_ternary", "naive_max"]:
        rows = run(strat)
        feas = [r for r in rows if r["feasible"]]
        wc_calls = max(r["calls"] for r in rows)
        wc_gapM = max(r["gap_M"] for r in feas)
        wc_gapf = max(r["gap_f"] for r in feas)
        mean_gapM = sum(r["gap_M"] for r in feas) / len(feas)
        print(f"\n===== {strat} =====")
        print(f"worst calls={wc_calls}  worst gap_M={wc_gapM}  mean gap_M={mean_gapM:.1f}  worst gap_f={wc_gapf}")
        print(f"{'scenario':12} {'M_ch':>4} {'M_tr':>4} {'calls':>5} {'gap_M':>5} {'gap_f':>6}")
        for r in rows:
            flag = "" if r["feasible"] else "  (infeasible)"
            print(f"{r['scenario']:12} {r['M_chosen']:4} {r['M_truth']:4} {r['calls']:5} {r['gap_M']:5} {r['gap_f']:6}{flag}")
