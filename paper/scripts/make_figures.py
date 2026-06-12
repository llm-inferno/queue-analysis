"""Generates all paper figures and tables from cached data.

Sources:
  - nous/cache/truth-<scenario>.json  (f_curve, M_truth, throughput_truth, regime)
  - paper/data/baseline_lambda_sweep.json
  - paper/scripts/primitives.py        (M_ITL, M_TPF, regime)
Outputs:
  - paper/figs/fig{1..4}_*.pdf
  - paper/tabs/lower_bound_regime.tex
"""
import json
from collections import namedtuple
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import primitives as P
import eval_strategies as EV

REPO = Path(__file__).resolve().parents[2]
TRUTH_DIR = REPO / "nous" / "cache"
DATA_DIR = REPO / "paper" / "data"
FIG_DIR = REPO / "paper" / "figs"
TAB_DIR = REPO / "paper" / "tabs"
M_MAX = 256

# Display order, grouped by regime; baseline first (headline).
SCENARIOS = ["baseline", "alpha-low", "alpha-high", "itl-only", "ttft-only", "unbounded"]
SCN_PARAMS = {s["name"]: s for s in
              json.loads((REPO / "nous" / "scenarios.json").read_text())["scenarios"]}
REGIME_COLOR = {"crossover": "C0", "itl-only": "C2", "ttft-only": "C1", "unbounded": "C3"}


def load_truth(name: str) -> dict:
    return json.loads((TRUTH_DIR / f"truth-{name}.json").read_text())


def load_baseline_sweep() -> dict:
    return json.loads((DATA_DIR / "baseline_lambda_sweep.json").read_text())


def setup_style() -> None:
    plt.rcParams.update({
        "font.size": 10, "axes.labelsize": 11, "axes.titlesize": 11,
        "legend.fontsize": 9, "lines.linewidth": 1.6,
        "figure.dpi": 150, "savefig.bbox": "tight",
    })


def main() -> None:
    setup_style()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    TAB_DIR.mkdir(parents=True, exist_ok=True)
    fig1_baseline_fM()
    fig2_overlay_fM()
    fig3_min_constraints()
    fig4_lower_bound_bracket()
    fig5_onset_search()
    tab1_lower_bound_regime()
    tab2_eval_comparison()
    print("done")


# Stubs — implemented in subsequent tasks.
def fig1_baseline_fM():
    truth = load_truth("baseline")
    m_star = truth["M_truth"]            # onset == argmax on this float-flat plateau
    f_star = truth["throughput_truth"]
    ms = [pt["m"] for pt in truth["f_curve"]]
    fs = [pt["throughput"] for pt in truth["f_curve"]]

    fig, ax = plt.subplots(figsize=(5.5, 3.2))
    ax.plot(ms, fs, color="C0")
    ax.axvline(m_star, color="gray", linestyle="--", linewidth=1)
    ax.annotate(f"$M^* = {m_star}$", xy=(m_star, f_star),
                xytext=(m_star + 20, f_star * 0.55), fontsize=10, color="gray",
                arrowprops=dict(arrowstyle="->", color="gray", lw=0.8))
    ax.text(m_star / 2, f_star * 0.40, "rising", ha="center", color="C0", alpha=0.7)
    ax.text((m_star + M_MAX) / 2, f_star * 1.04, "plateau", ha="center", color="C0", alpha=0.7)
    ax.set_xlabel("MaxBatchSize $M$")
    ax.set_ylabel("$f(M)$ — max RPS meeting SLOs")
    ax.set_xlim(0, M_MAX)
    ax.set_ylim(0, f_star * 1.15)
    fig.savefig(FIG_DIR / "fig1_baseline_fM.pdf")
    plt.close(fig)
def fig2_overlay_fM():
    fig, ax = plt.subplots(figsize=(5.8, 3.6))
    seen_regimes = set()
    for name in SCENARIOS:
        truth = load_truth(name)
        regime = truth["regime"]
        color = REGIME_COLOR.get(regime, "C4")
        ms = np.array([pt["m"] for pt in truth["f_curve"]])
        fs = np.array([pt["throughput"] for pt in truth["f_curve"]])
        f_star = truth["throughput_truth"]
        norm = fs / f_star if f_star > 0 else fs
        # One legend entry per regime; scenarios in a regime share color.
        label = regime if regime not in seen_regimes else None
        seen_regimes.add(regime)
        ax.plot(ms, norm, color=color, alpha=0.9, label=label)
        ax.axvline(truth["M_truth"], color=color, linestyle=":", linewidth=0.8, alpha=0.5)
    ax.axhline(1.0, color="gray", linewidth=0.6, alpha=0.5)
    ax.set_xlabel("MaxBatchSize $M$")
    ax.set_ylabel(r"$f(M)/f^*$ (normalized)")
    ax.set_xlim(0, M_MAX)
    ax.set_ylim(0, 1.1)
    ax.legend(loc="lower right", framealpha=0.9, title="regime")
    fig.savefig(FIG_DIR / "fig2_overlay_fM.pdf")
    plt.close(fig)
def fig3_min_constraints():
    sweep = load_baseline_sweep()
    rows = [r for r in sweep["rows"] if not r["infeasible"]]
    ms = np.array([r["m"] for r in rows])
    lam_ttft = np.array([r["RPSTargetTTFT"] for r in rows])
    lam_itl = np.array([r["RPSTargetITL"] for r in rows])
    f_min = np.minimum(lam_ttft, lam_itl)
    m_star = load_truth("baseline")["M_truth"]

    fig, ax = plt.subplots(figsize=(5.8, 3.6))
    ax.plot(ms, lam_ttft, color="C1", label=r"$\lambda^*_{\mathrm{TTFT}}(M)$")
    ax.plot(ms, lam_itl, color="C2", label=r"$\lambda^*_{\mathrm{ITL}}(M)$")
    ax.plot(ms, f_min, color="C0", linewidth=2.6, label=r"$f(M)=\min(\cdot)$")
    ax.axvspan(ms.min(), m_star, alpha=0.07, color="C1")
    ax.axvspan(m_star, ms.max(), alpha=0.07, color="C2")
    ax.axvline(m_star, color="gray", linestyle="--", linewidth=1)
    ax.text(m_star * 0.5, f_min.max() * 0.15, "TTFT binds", ha="center", color="C1", fontsize=9)
    ax.text((m_star + ms.max()) / 2, f_min.max() * 0.15, "ITL binds", ha="center", color="C2", fontsize=9)
    ax.set_xlabel("MaxBatchSize $M$")
    ax.set_ylabel("RPS")
    ax.set_xlim(ms.min(), ms.max())
    ax.set_ylim(bottom=0)
    ax.legend(loc="lower right", framealpha=0.9)
    fig.savefig(FIG_DIR / "fig3_min_constraints.pdf")
    plt.close(fig)
_BaselineFM = namedtuple("_BaselineFM", "f_of m_itl m_tpf m_star f_star")


def _baseline_fM_axes():
    """Shared setup for the baseline f(M) figures (fig4, fig5): load the truth
    curve and closed-form primitives, plot f(M), and configure the axes. Returns
    the figure, axes, and the values both figures annotate."""
    truth = load_truth("baseline")
    p = SCN_PARAMS["baseline"]
    ms = [pt["m"] for pt in truth["f_curve"]]
    fs = [pt["throughput"] for pt in truth["f_curve"]]
    ctx = _BaselineFM(
        f_of={pt["m"]: pt["throughput"] for pt in truth["f_curve"]},
        m_itl=P.m_itl(p, M_MAX), m_tpf=P.m_tpf(p, M_MAX),
        m_star=truth["M_truth"], f_star=truth["throughput_truth"],
    )
    fig, ax = plt.subplots(figsize=(5.8, 3.4))
    ax.plot(ms, fs, color="C0", zorder=2)
    ax.set_xlabel("MaxBatchSize $M$")
    ax.set_ylabel("$f(M)$ [RPS]")
    ax.set_xlim(0, M_MAX)
    ax.set_ylim(0, ctx.f_star * 1.15)
    return fig, ax, ctx
def fig4_lower_bound_bracket():
    fig, ax, c = _baseline_fM_axes()
    marks = [
        (c.m_itl, "C2", rf"$M_{{\mathrm{{ITL}}}}={c.m_itl}$"),
        (c.m_star, "gray", rf"$M^*={c.m_star}$"),
        (c.m_tpf, "C1", rf"$M_{{\mathrm{{TPF}}}}={c.m_tpf}$"),
    ]
    for x, color, _lab in marks:
        ax.axvline(x, color=color, linestyle="--", linewidth=1.2, zorder=1)
    # Shade the [M_ITL, M_TPF] bracket the search narrows.
    ax.axvspan(c.m_itl, c.m_tpf, alpha=0.08, color="C0", zorder=0)
    handles = [plt.Line2D([0], [0], color=color, linestyle="--", label=lab)
               for _x, color, lab in marks]
    ax.legend(handles=handles, loc="lower right", framealpha=0.9)
    fig.savefig(FIG_DIR / "fig4_lower_bound_bracket.pdf")
    plt.close(fig)
def fig5_onset_search():
    """Measured search trace: the actual probes formula_guided issues on the
    baseline scenario (replayed via eval_strategies.trace), over the true f(M)."""
    fig, ax, c = _baseline_fM_axes()
    tr = EV.trace("formula_guided", "baseline")
    seed, probes = tr["seed"], tr["probes"]
    f_anchor, threshold = tr["f_anchor"], tr["threshold"]
    lo = max(1, min(c.m_itl, c.m_tpf))
    U = max(c.m_itl, c.m_tpf)
    hi = min(seed, max(3 * U, lo + 1), M_MAX)

    # Search bracket the algorithm narrows.
    ax.axvspan(lo, hi, alpha=0.08, color="C0", zorder=0)
    # Anchor and threshold (horizontal references).
    ax.axhline(f_anchor, color="C3", linestyle="-.", linewidth=1.0, zorder=1)
    ax.axhline(threshold, color="C3", linestyle=":", linewidth=1.0, zorder=1)
    ax.text(M_MAX * 0.62, f_anchor * 1.01, r"anchor $f^*=f(m_{\max})$",
            color="C3", fontsize=8, va="bottom")
    ax.text(M_MAX * 0.62, threshold * 0.985, r"threshold $(1-\varepsilon/2)f^*$",
            color="C3", fontsize=8, va="top")
    # Closed-form markers and onset.
    for x, color in [(c.m_itl, "C2"), (c.m_star, "gray"), (c.m_tpf, "C1")]:
        ax.axvline(x, color=color, linestyle="--", linewidth=1.2, zorder=1)
    # Downward-search probes: markers at each probed M on the curve.
    for mid in probes:
        ax.plot([mid], [c.f_of[mid]], marker="v", color="C4", markersize=6, zorder=3)
    if probes:
        ax.annotate("downward search", xy=(probes[-1], c.f_of[probes[-1]]),
                    xytext=(lo + 6, c.f_star * 0.45), color="C4", fontsize=8,
                    arrowprops=dict(arrowstyle="->", color="C4", lw=0.8))
    handles = [
        plt.Line2D([0], [0], color="C2", linestyle="--", label=rf"$M_{{\mathrm{{ITL}}}}={c.m_itl}$ (lower bd)"),
        plt.Line2D([0], [0], color="C1", linestyle="--", label=rf"$M_{{\mathrm{{TPF}}}}={c.m_tpf}$ (TTFT upper bd)"),
        plt.Line2D([0], [0], color="gray", linestyle="--", label=rf"onset $M^*={c.m_star}$"),
        plt.Line2D([0], [0], color="C4", marker="v", linestyle="", label="search probes"),
    ]
    ax.legend(handles=handles, loc="lower right", framealpha=0.9, fontsize=8)
    fig.savefig(FIG_DIR / "fig5_onset_search.pdf")
    plt.close(fig)
def tab1_lower_bound_regime():
    rows_out = []
    for name in SCENARIOS:
        p = SCN_PARAMS[name]
        truth = load_truth(name)
        m_itl = P.m_itl(p, M_MAX)
        m_tpf = P.m_tpf(p, M_MAX)
        m_star = truth["M_truth"]          # onset == argmax on the dev plateaus
        f_star = truth["throughput_truth"]
        gap = m_star / m_itl if m_itl > 0 else float("nan")
        # gap_f at the lower bound: relative throughput shortfall if you stop at M_ITL.
        f_at_mitl = truth["f_curve"][min(m_itl, len(truth["f_curve"])) - 1]["throughput"]
        gap_f = (f_star - f_at_mitl) / f_star if f_star > 0 else 0.0
        rows_out.append({
            "name": name, "regime": truth["regime"],
            "m_itl": m_itl, "m_tpf": m_tpf, "m_star": m_star,
            "gap": gap, "gap_f": gap_f,
        })

    lines = [
        r"\begin{table}[t]",
        r"  \centering",
        r"  \caption{Closed-form lower bound, regime, and occupancy gap across the "
        r"six scenarios. $M_{\mathrm{ITL}}$ is exact under $nc=1$ (RP-1) and a lower "
        r"bound on the onset $M^*$ (RP-2); the gap $M^*/M_{\mathrm{ITL}}$ is bounded but "
        r"non-constant, motivating a warm-started search rather than direct prediction. "
        r"The $\mathrm{ttft\text{-}only}$ row has $M_{\mathrm{TPF}}<M_{\mathrm{ITL}}$ "
        r"(RP-7), the load-bearing classification signal.}",
        r"  \label{tab:lower-bound-regime}",
        r"  \begin{tabular}{llrrrrr}",
        r"    \toprule",
        r"    Scenario & regime & $M_{\mathrm{ITL}}$ & $M_{\mathrm{TPF}}$ & $M^*$ & "
        r"$M^*/M_{\mathrm{ITL}}$ & gap$_f$ (\%) \\",
        r"    \midrule",
    ]
    for r in rows_out:
        lines.append(
            f"    {r['name'].replace('-', '--')} & {r['regime']} & {r['m_itl']} & "
            f"{r['m_tpf']} & {r['m_star']} & {r['gap']:.2f} & {r['gap_f']*100:.1f} \\\\")
    lines += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}", ""]
    (TAB_DIR / "lower_bound_regime.tex").write_text("\n".join(lines))


def tab2_eval_comparison():
    """Strategy comparison over the 25 feasible benchmark scenarios.
    Reads paper/data/eval_results.json (run eval_strategies.py first)."""
    res = json.loads((DATA_DIR / "eval_results.json").read_text())
    agg = res["aggregates"]["benchmark"]
    eps = res["eps"]
    display = [("formula_guided", "Formula-guided"),
               ("naive_ternary", "Parameter-blind ternary"),
               ("naive_max", "Naive-max")]
    n = agg["n_scenarios"]
    lines = [
        r"\begin{table}[t]",
        r"  \centering",
        r"  \caption{Onset-search accuracy and cost over the " + str(n) +
        r" feasible benchmark scenarios (worst / mean). $\mathrm{gap}_{\mathrm{onset}}"
        r"=|\hat M - M^\ast|$ is measured against the $\varepsilon$-onset (the objective);"
        r" $\mathrm{gap}_{\mathrm{argmax}}$ against the strict throughput argmax (campaign"
        r" convention; its floor is structural, RP-10). $\mathrm{gap}_f$ is the relative"
        r" throughput shortfall; the SLO tolerance is $\varepsilon=" + f"{eps:.2f}" + r"$."
        r" Only Formula-guided is simultaneously cheap, SLO-feasible, and near-onset.}",
        r"  \label{tab:eval-comparison}",
        r"  \begin{tabular}{lrrrr}",
        r"    \toprule",
        r"    Strategy & calls & $\mathrm{gap}_{\mathrm{onset}}$ (worst/mean) & "
        r"$\mathrm{gap}_f$ (worst) & $\mathrm{gap}_{\mathrm{argmax}}$ (worst) \\",
        r"    \midrule",
    ]
    for key, label in display:
        a = agg[key]
        ok = r"\checkmark" if a["gap_f_worst"] <= eps else r"$\times$"
        lines.append(
            f"    {label} & {a['calls_worst']} & "
            f"{a['gap_onset_worst']}/{a['gap_onset_mean']:.1f} & "
            f"{a['gap_f_worst']:.4f}~{ok} & {a['gap_argmax_worst']} \\\\")
    lines += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}", ""]
    (TAB_DIR / "eval_comparison.tex").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
