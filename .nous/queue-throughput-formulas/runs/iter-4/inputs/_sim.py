"""Offline simulator over cached f_curves to ground iter-4 predictions.

Cache fidelity (cache == live /target) was verified in the iter-3 handoff and
re-confirmed by this iteration's live seed_upper / naive_max smoke runs. So we
can prototype the two NEW strategies (formula_guided, naive_ternary) offline.

Call-counting semantics mirror oracle.py + run.py:
  - a probe at M with throughput > 0 is a feasible /target -> COUNTED
  - a probe at M with throughput == 0 is treated as HTTP 400 -> UNCOUNTED
  - the harness adds +1 confirmatory eval at the chosen M (counted unless 0)
Scoring mirrors scoring.py: gap = max(0, (truth - chosen)/truth), 0 if truth<=0.
"""
import json, sys
sys.path.insert(0, ".")
import nous.harness.formulas as F

SC = {s["name"]: s for s in json.load(open("nous/scenarios_benchmark.json"))["scenarios"]}
M_MIN, M_MAX = 1, 256


def params_of(name):
    s = SC[name]
    return {"alpha": s["alpha"], "beta": s["beta"], "gamma": s["gamma"],
            "AvgInputTokens": s["AvgInputTokens"], "AvgOutputTokens": s["AvgOutputTokens"],
            "targetITL": s["targetITL"], "targetTTFT": s["targetTTFT"],
            "maxQueueSize": s["maxQueueSize"]}


def fcurve(name):
    t = json.load(open(f"nous/cache/bench/{name}.json"))
    f = {d["m"]: d["throughput"] for d in t["f_curve"]}
    return f, t["M_truth"], t["throughput_truth"]


def _largest_feasible(metric, p, target):
    feas = [B for B in range(M_MIN, M_MAX + 1) if metric(B, p) <= target]
    return max(feas) if feas else None


def seed_U(p):
    itl_binds = F.itl(M_MAX, p) > p["targetITL"]
    ttft_binds = F.ttft_prefill(M_MAX, p) > p["targetTTFT"]
    M_ITL = _largest_feasible(F.itl, p, p["targetITL"]) or M_MIN
    M_TPF = _largest_feasible(F.ttft_prefill, p, p["targetTTFT"]) or M_MIN
    if (not itl_binds) and (not ttft_binds):
        return M_MAX
    if M_TPF < M_ITL:
        return M_TPF
    return min(M_TPF, M_MAX)


class Oracle:
    def __init__(self, f):
        self.f = f; self.calls = 0
    def __call__(self, m):
        m = max(M_MIN, min(M_MAX, int(m)))
        v = self.f.get(m, 0.0)
        if v > 0.0:
            self.calls += 1
        return v


def run(strategy, name):
    f, mt, tt = fcurve(name)
    orc = Oracle(f)
    m = strategy(orc, params_of(name))
    final = orc(m)  # +1 confirmatory
    gap = 0.0 if tt <= 0 else max(0.0, (tt - final) / tt)
    return m, orc.calls, gap, mt


# ---- strategies -----------------------------------------------------------

def s_naive_max(orc, p):
    return M_MAX


def s_seed_upper(orc, p):
    return seed_U(p)


def s_naive_ternary(orc, p):
    """parameter-blind ternary on [1,256]; ~ceil(log_1.5) iters, 2 probes each."""
    lo, hi = M_MIN, M_MAX
    while hi - lo > 2:
        m1 = lo + (hi - lo) // 3
        m2 = hi - (hi - lo) // 3
        if orc(m1) < orc(m2):
            lo = m1
        else:
            hi = m2
    best, bv = lo, orc(lo)
    for x in range(lo + 1, hi + 1):
        v = orc(x)
        if v > bv:
            best, bv = x, v
    return best


def s_formula_guided(orc, p):
    """seed U + bounded bidirectional refinement.

    1. start at seed U (constraint bracket upper endpoint)
    2. UP-probe: while a probe above current best strictly improves, climb
       (geometric steps toward M_MAX) -- recovers TTFT-undershoot (bench-018/023)
    3. DOWN-probe: probe below best; if it strictly improves, ternary-refine the
       interior bracket [m_min, best] -- catches interior peaks (bench-025/014)
    Capped at ~8 internal probes.
    """
    best = max(M_MIN, min(M_MAX, seed_U(p)))
    bv = orc(best)
    # UP refinement: geometric climb toward M_MAX
    cur = best
    while cur < M_MAX:
        nxt = min(M_MAX, cur + max(1, (M_MAX - cur) // 2))
        v = orc(nxt)
        if v > bv * 1.001:
            best, bv = nxt, v; cur = nxt
        else:
            break
    # DOWN refinement: probe a point below best; refine if it improves
    if best > 2:
        probe = max(M_MIN, best // 2)
        v = orc(probe)
        if v > bv * 1.001:
            lo, hi = M_MIN, best
            for _ in range(5):
                if hi - lo <= 2:
                    break
                m1 = lo + (hi - lo) // 3
                m2 = hi - (hi - lo) // 3
                if orc(m1) < orc(m2):
                    lo = m1
                else:
                    hi = m2
            for x in range(lo, hi + 1):
                vv = orc(x)
                if vv > bv:
                    best, bv = x, vv
    return best


STRATS = {"naive_max": s_naive_max, "seed_upper": s_seed_upper,
          "naive_ternary": s_naive_ternary, "formula_guided": s_formula_guided}

if __name__ == "__main__":
    names = sorted(SC)
    for sname, fn in STRATS.items():
        worst_gap = 0.0; worst_n = None; max_calls = 0; tot_calls = 0; nfeas = 0
        rows = []
        for n in names:
            m, c, g, mt = run(fn, n)
            rows.append((n, m, c, g, mt))
            tot_calls += c; max_calls = max(max_calls, c)
            if g > worst_gap:
                worst_gap, worst_n = g, n
        print(f"\n=== {sname} ===  worst_gap={worst_gap:.4f}({worst_n}) max_calls={max_calls} mean_calls={tot_calls/len(names):.2f}")
        for n, m, c, g, mt in rows:
            if g > 0.005 or c > 6:
                print(f"   {n}: M={m} calls={c} gap={g:.4f} (M_truth={mt})")
