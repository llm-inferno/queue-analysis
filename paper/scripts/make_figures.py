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
def fig1_baseline_fM(): pass
def fig2_overlay_fM(): pass
def fig3_min_constraints(): pass
def fig4_lower_bound_bracket(): pass
def tab1_lower_bound_regime(): pass


if __name__ == "__main__":
    main()
