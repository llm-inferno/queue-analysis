"""Analytic service-time primitives — vendored, parity-checked port of
nous/harness/formulas.py (itself a port of pkg/analyzer/queueanalyzer.go:275-327
and pkg/analyzer/utils.go:8-47). Self-contained so paper figures regenerate from
the paper venv alone. Verified against RP-1 by test_primitives.py.

`params` is a scenario dict with keys: alpha, beta, gamma, AvgInputTokens,
AvgOutputTokens, targetITL, targetTTFT, maxQueueSize.
"""
from __future__ import annotations

import math

MAX_NUM_TOKENS = 8192  # analyzer.DefaultMaxNumTokens


def _max_batch_for_iters(num_iters: int, n_in: float, m_out: float) -> int:
    m = float(num_iters)
    batch = (m + m_out) * (MAX_NUM_TOKENS - n_in / m) / (n_in + m_out)
    return int(math.floor(max(0.0, batch)))


def num_iterations_per_prefill(B: int, params: dict) -> int:
    n_in = float(params["AvgInputTokens"])
    m_out = float(params["AvgOutputTokens"])
    sizes, batch, k = [], 0, 1
    while batch < B:
        batch = _max_batch_for_iters(k, n_in, m_out)
        sizes.append(batch)
        k += 1
    for i, bs in enumerate(sizes):
        if bs >= B:
            return i + 1
    return len(sizes)


def _w_prefill(nc: int, params: dict) -> float:
    n = float(params["AvgInputTokens"])
    return (params["beta"] + params["gamma"] * (nc + 1) / 2.0) * n


def _w_decode(params: dict) -> float:
    n = float(params["AvgInputTokens"])
    m = float(params["AvgOutputTokens"])
    return params["beta"] * m + params["gamma"] * m * (n + (m + 1) / 2.0)


def delta(B: int, params: dict) -> float:
    nc = num_iterations_per_prefill(B, params)
    m = float(params["AvgOutputTokens"])
    return (_w_prefill(nc, params) + _w_decode(params)) / (nc + m)


def _bg(B: int, params: dict) -> float:
    return max(0.0, params["alpha"] + (B - 1) * delta(B, params))


def itl(B: int, params: dict) -> float:
    n = float(params["AvgInputTokens"])
    m = float(params["AvgOutputTokens"])
    return _bg(B, params) + params["beta"] + params["gamma"] * (n + (m + 1) / 2.0)


def ttft_prefill(B: int, params: dict) -> float:
    nc = num_iterations_per_prefill(B, params)
    return nc * _bg(B, params) + _w_prefill(nc, params)


def m_itl(params: dict, m_max: int) -> int:
    """Closed-form ITL-binding batch size (exact under nc=1; RP-1)."""
    d = delta(1, params)
    raw = math.floor(1 + (params["targetITL"] - itl(1, params)) / d)
    return max(1, min(m_max, raw))


def m_tpf(params: dict, m_max: int) -> int:
    """Largest B with ttft_prefill(B) <= targetTTFT (0 if none)."""
    feasible = [B for B in range(1, m_max + 1)
                if ttft_prefill(B, params) <= params["targetTTFT"]]
    return max(feasible) if feasible else 0


def regime_cell(params: dict, m_max: int) -> str:
    """Primitive-decidable 3-cell partition (RP-6, RP-7)."""
    itl_binds = itl(m_max, params) > params["targetITL"]
    ttft_binds = ttft_prefill(m_max, params) > params["targetTTFT"]
    if not itl_binds and not ttft_binds:
        return "unbounded"
    if m_tpf(params, m_max) < m_itl(params, m_max):
        return "ttft-only"
    return "itl-or-crossover"
