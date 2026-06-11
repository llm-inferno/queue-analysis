"""Parity + unit tests for the analyzer-primitive port in formulas.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nous.harness import formulas

GOLDEN = Path(__file__).parent / "golden_primitives.json"
REL_TOL = 1e-4  # float32 round-trip tolerance


def _params(rec: dict) -> dict:
    return {
        "alpha": rec["alpha"], "beta": rec["beta"], "gamma": rec["gamma"],
        "AvgInputTokens": rec["AvgInputTokens"],
        "AvgOutputTokens": rec["AvgOutputTokens"],
        "targetITL": 20.0, "targetTTFT": 60.0, "maxQueueSize": 128,
    }


@pytest.fixture(scope="module")
def golden() -> list[dict]:
    return json.loads(GOLDEN.read_text())


def test_nc_matches_go(golden):
    for rec in golden:
        got = formulas.num_iterations_per_prefill(rec["B"], _params(rec))
        assert got == rec["nc"], f"nc B={rec['B']}: py={got} go={rec['nc']}"


def test_itl_matches_go_at_nc1(golden):
    # Go shims (IterationTime/PrefillTime/DecodeTime) use nc=1; compare only
    # the tuples whose true nc is 1, where the formula reduces identically.
    for rec in golden:
        if rec["nc"] != 1:
            continue
        got = formulas.itl(rec["B"], _params(rec))
        assert got == pytest.approx(rec["itl"], rel=REL_TOL)


def test_decode_slope_is_affine_in_target():
    # n_ITL inversion in the predictor relies on itl(B) being affine in B: itl = a + b*B.
    p = {"alpha": 8.0, "beta": 0.033, "gamma": 0.000333,
         "AvgInputTokens": 256, "AvgOutputTokens": 1024,
         "targetITL": 20.0, "targetTTFT": 60.0, "maxQueueSize": 128}
    i10, i20, i30 = (formulas.itl(b, p) for b in (10, 20, 30))
    assert (i20 - i10) == pytest.approx(i30 - i20, rel=1e-6)


def test_tau_positive_and_monotone():
    p = {"alpha": 8.0, "beta": 0.033, "gamma": 0.000333,
         "AvgInputTokens": 256, "AvgOutputTokens": 1024,
         "targetITL": 20.0, "targetTTFT": 60.0, "maxQueueSize": 128}
    taus = [formulas.tau(b, p) for b in range(1, 64)]
    assert all(t > 0 for t in taus)
    assert taus == sorted(taus), "tau should increase in B"
