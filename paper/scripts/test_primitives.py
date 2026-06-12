"""Parity gate: vendored primitives must reproduce the campaign's M_ITL/M_TPF
and the regime classification for all six scenarios (RP-1, RP-6, RP-7)."""
import json
from pathlib import Path

import primitives as P

REPO = Path(__file__).resolve().parents[2]
SCN = {s["name"]: s for s in
       json.loads((REPO / "nous" / "scenarios.json").read_text())["scenarios"]}

EXPECTED = {
    # name:        (M_ITL, M_TPF, regime)
    "baseline":   (40, 147, "crossover"),
    "itl-only":   (8, 256, "itl-or-crossover"),
    "ttft-only":  (95, 70, "ttft-only"),
    "unbounded":  (256, 256, "unbounded"),
    "alpha-low":  (107, 256, "crossover"),
    "alpha-high": (6, 45, "crossover"),
}


def test_m_itl_m_tpf_regime():
    for name, (m_itl, m_tpf, regime_family) in EXPECTED.items():
        p = SCN[name]
        assert P.m_itl(p, 256) == m_itl, f"{name}: M_ITL"
        assert P.m_tpf(p, 256) == m_tpf, f"{name}: M_TPF"
        cell = P.regime_cell(p, 256)
        # itl-only and crossover share the same primitive cell (RP-6)
        if regime_family in ("crossover", "itl-or-crossover"):
            assert cell == "itl-or-crossover", f"{name}: cell {cell}"
        else:
            assert cell == regime_family, f"{name}: cell {cell}"


def test_nc_is_one_on_dev_set():
    for name, p in SCN.items():
        assert P.num_iterations_per_prefill(256, p) == 1, f"{name}: nc(256)"
