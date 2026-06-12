"""Determinism + manifold tests for the benchmark generator."""
from __future__ import annotations

import json

from nous.harness.scenarios import ALLOWED_FIELDS
from nous.harness.scenarios_benchmark import generate


def test_deterministic_for_seed():
    a = generate(n=30, seed=42)
    b = generate(n=30, seed=42)
    assert a == b


def test_count_and_indexing():
    recs = generate(n=30, seed=42)
    assert len(recs) == 30
    assert recs[0]["name"] == "bench-000"
    assert recs[29]["name"] == "bench-029"
    assert all(r["regime"] == "bench" for r in recs)


def test_only_allowed_fields():
    for r in generate(n=5, seed=42):
        assert set(r) <= ALLOWED_FIELDS


def test_ratio_manifold_preserved():
    # beta = alpha * (beta/alpha-sample); ratios must stay in the spec envelope.
    for r in generate(n=30, seed=42):
        assert 1 / 500 <= r["beta"] / r["alpha"] <= 1 / 100
        assert 1 / 50000 <= r["gamma"] / r["alpha"] <= 1 / 10000
