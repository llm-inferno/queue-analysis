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
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import primitives as P

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
    tab1_lower_bound_regime()
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
def fig4_lower_bound_bracket(): pass
def tab1_lower_bound_regime(): pass


if __name__ == "__main__":
    main()
