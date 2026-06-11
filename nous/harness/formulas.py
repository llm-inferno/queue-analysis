"""Analytic service-time primitives for the queue-analysis model.

A faithful Python port of the unexported primitives in
pkg/analyzer/queueanalyzer.go:275-327 and the chunk-count logic in
pkg/analyzer/utils.go:8-47. This module is the single source of truth for the
formulas NOUS reasons about; it is parity-checked against the Go source by
tests/test_formulas.py (golden_primitives.json).

All functions take a batch size B (int) and a params dict with keys:
    alpha, beta, gamma, AvgInputTokens, AvgOutputTokens,
    targetITL, targetTTFT, maxQueueSize

The chunk budget MaxNumTokens is fixed at 8192 (analyzer DefaultMaxNumTokens);
it is NOT a params key because the /target requests never override it.
"""
from __future__ import annotations

import math

MAX_NUM_TOKENS = 8192  # matches analyzer.DefaultMaxNumTokens


# --- chunk count (port of utils.go) ---------------------------------------

def _max_batch_for_iters(num_iters: int, n_in: float, m_out: float) -> int:
    """Port of CalculateMaxBatchSizeForNumIterationsPerPrefill (utils.go:8)."""
    m = float(num_iters)
    batch = (m + m_out) * (MAX_NUM_TOKENS - n_in / m) / (n_in + m_out)
    return int(math.floor(max(0.0, batch)))


def _batch_sizes(max_batch: int, n_in: float, m_out: float) -> list[int]:
    """Port of CalculateBatchSizes (utils.go:19)."""
    sizes: list[int] = []
    batch = 0
    num_iters = 1
    while batch < max_batch:
        batch = _max_batch_for_iters(num_iters, n_in, m_out)
        sizes.append(batch)
        num_iters += 1
    return sizes


def num_iterations_per_prefill(B: int, params: dict) -> int:
    """nc at batch size B (treating maxBatchSize = B, per spec B=M).

    Port of NumIterationsPerPrefillForBatchSize over CalculateBatchSizes
    (utils.go:31-47).
    """
    n_in = float(params["AvgInputTokens"])
    m_out = float(params["AvgOutputTokens"])
    sizes = _batch_sizes(B, n_in, m_out)
    for i, bs in enumerate(sizes):
        if bs >= B:
            return i + 1
    return len(sizes)


# --- service-time primitives (port of queueanalyzer.go) -------------------

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
    w_total = _w_prefill(nc, params) + _w_decode(params)
    return w_total / (nc + m)


def _t_iter(B: int, params: dict) -> float:
    return params["alpha"] + B * delta(B, params)


def tau(B: int, params: dict) -> float:
    nc = num_iterations_per_prefill(B, params)
    m = float(params["AvgOutputTokens"])
    return (nc + m) * _t_iter(B, params)


def _bg(B: int, params: dict) -> float:
    return max(0.0, params["alpha"] + (B - 1) * delta(B, params))


def ttft_prefill(B: int, params: dict) -> float:
    """Prefill component of TTFT (queue wait excluded; the M/M/1 solver adds it)."""
    nc = num_iterations_per_prefill(B, params)
    return nc * _bg(B, params) + _w_prefill(nc, params)


def itl(B: int, params: dict) -> float:
    n = float(params["AvgInputTokens"])
    m = float(params["AvgOutputTokens"])
    return _bg(B, params) + params["beta"] + params["gamma"] * (n + (m + 1) / 2.0)
