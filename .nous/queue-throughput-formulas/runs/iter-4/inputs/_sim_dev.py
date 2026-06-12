"""Offline sim on the DEV set with the gap_M headline (brief iter-4 scoring).

M* = onset = smallest M with f(M) >= (1-eps)*f_peak, eps=0.02.
Headline Pareto axes: (calls, gap_M) subject to gap_f <= eps.
Mechanism for formula_guided: probe high seed -> downward binary search for the
smallest M with f(M) >= (1-eps)*f_seed  (monotone predicate).

Call counting mirrors oracle.py/run.py: feasible probe (f>0) counted; f==0 (400)
uncounted; +1 confirmatory eval at chosen M.
"""
import json, sys, glob
sys.path.insert(0, ".")
import nous.harness.formulas as F

EPS = 0.02
M_MIN, M_MAX = 1, 256
SC = {s["name"]: s for s in json.load(open("nous/scenarios.json"))["scenarios"]}


def params_of(name):
    s = SC[name]
    return {"alpha": s["alpha"], "beta": s["beta"], "gamma": s["gamma"],
            "AvgInputTokens": s["AvgInputTokens"], "AvgOutputTokens": s["AvgOutputTokens"],
            "targetITL": s["targetITL"], "targetTTFT": s["targetTTFT"],
            "maxQueueSize": s["maxQueueSize"]}


def load(name):
    d = json.load(open(f"nous/cache/truth-{name}.json"))
    f = {x["m"]: x["throughput"] for x in d["f_curve"]}
    return f, d["M_truth"], d["throughput_truth"]


def onset(f):
    peak = max(f.values())
    for m in range(M_MIN, M_MAX + 1):
        if f.get(m, 0.0) >= (1 - EPS) * peak:
            return m, peak
    return M_MAX, peak


def _largest_feasible(metric, p, target):
    feas = [B for B in range(M_MIN, M_MAX + 1) if metric(B, p) <= target]
    return max(feas) if feas else None


def seed_U(p):
    itl_b = F.itl(M_MAX, p) > p["targetITL"]
    ttft_b = F.ttft_prefill(M_MAX, p) > p["targetTTFT"]
    M_ITL = _largest_feasible(F.itl, p, p["targetITL"]) or M_MIN
    M_TPF = _largest_feasible(F.ttft_prefill, p, p["targetTTFT"]) or M_MIN
    if (not itl_b) and (not ttft_b):
        return M_MAX
    if M_TPF < M_ITL:
        return M_TPF
    return min(M_TPF, M_MAX)


def M_ITL_of(p):
    return _largest_feasible(F.itl, p, p["targetITL"]) or M_MIN


class Oracle:
    def __init__(self, f):
        self.f = f; self.calls = 0
    def __call__(self, m):
        m = max(M_MIN, min(M_MAX, int(m)))
        v = self.f.get(m, 0.0)
        if v > 0.0:
            self.calls += 1
        return v


# --- strategies ---
def naive_max(orc, p):
    return M_MAX


def naive_ternary(orc, p):
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


def formula_guided(orc, p):
    """Probe high seed for f*, then downward binary search for the smallest M
    with f(M) >= (1-eps)*f*.  Bracket low end at M_ITL (closed-form lower bound,
    RP-1/RP-2); below the onset the predicate is monotone-false."""
    seed = max(M_MIN, min(M_MAX, seed_U(p)))
    fstar = orc(seed)
    if fstar <= 0.0:  # seed infeasible: fall back to max
        seed = M_MAX; fstar = orc(seed)
    thresh = (1 - EPS) * fstar
    lo = max(M_MIN, min(M_ITL_of(p), seed))  # lower bracket = closed-form M_ITL
    hi = seed
    # ensure predicate false at lo-1 region: binary search smallest M in [lo,hi] with f>=thresh
    # guarantee f(lo) may already be >= thresh; search for the smallest such M down to M_MIN.
    lo2 = M_MIN
    while lo2 < hi:
        mid = (lo2 + hi) // 2
        if orc(mid) >= thresh:
            hi = mid
        else:
            lo2 = mid + 1
    return hi


STRATS = {"naive_max": naive_max, "naive_ternary": naive_ternary, "formula_guided": formula_guided}


def run(fn, name):
    f, mt, tt = load(name)
    orc = Oracle(f)
    m = fn(orc, params_of(name))
    final = orc(m)
    gap_f = 0.0 if tt <= 0 else max(0.0, (tt - final) / tt)
    gap_M = abs(m - mt)
    return m, orc.calls, gap_f, gap_M, mt


print("onset check (M*_computed vs M_truth):")
for n in sorted(SC):
    f, mt, tt = load(n)
    mstar, peak = onset(f)
    print(f"  {n}: M*_computed={mstar} M_truth={mt} peak={peak:.4f} U={seed_U(params_of(n))} M_ITL={M_ITL_of(params_of(n))}")

for sname, fn in STRATS.items():
    print(f"\n=== {sname} ===")
    wc=wm=0; mc=0
    for n in sorted(SC):
        m, c, gf, gm, mt = run(fn, n)
        wc=max(wc,gf); wm=max(wm,gm); mc=max(mc,c)
        print(f"  {n}: M={m} calls={c} gap_f={gf:.4f} gap_M={gm} (M_truth={mt})")
    print(f"  -> worst gap_f={wc:.4f} worst gap_M={wm} max calls={mc}")
