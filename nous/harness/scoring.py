"""Pareto-axis computations: gap_throughput_rel and gap_M."""

from __future__ import annotations
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ScenarioResult:
    scenario: str
    strategy: str
    M_chosen: int
    calls: int
    throughput_chosen: float
    M_truth: int
    throughput_truth: float
    gap_throughput_rel: float
    gap_M: int
    wall_clock_seconds: float
    internal_solve_calls: int

    def to_dict(self) -> dict:
        return asdict(self)


def compute_gap(*, m_chosen: int, throughput_chosen: float,
                m_truth: int, throughput_truth: float) -> dict:
    # Negative raw gap means throughput_chosen > throughput_truth, which can
    # happen on the plateau (any M >= M* yields f* within float noise; M_chosen
    # may sit above M_truth). We report 0 in that case rather than a negative
    # gap so "0 gap = on the plateau" stays a clean invariant.
    if throughput_truth <= 0.0:
        rel = 0.0
    else:
        raw = (throughput_truth - throughput_chosen) / throughput_truth
        rel = max(raw, 0.0)
    return {
        "gap_throughput_rel": rel,
        "gap_M": abs(m_chosen - m_truth),
    }
