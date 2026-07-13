"""The Quant — deterministic Bayesian posterior + heuristic parser.

These lock in the core math contract: given (prior, sentiment, confidence)
the posterior is a pure, reproducible number. LLMs never touch this.
"""
from __future__ import annotations

import math

import pytest

from app.modules.intelligence import _heuristic, bayesian_update


def test_bullish_posterior_known_value():
    # LR = 1 + 4*0.8 = 4.2 ; prior 0.5 -> posterior = 4.2 / 5.2
    post, lr = bayesian_update(0.5, "bullish", 0.8)
    assert lr == 4.2
    assert post == pytest.approx(4.2 / 5.2, abs=1e-4)
    assert post == 0.8077


def test_bearish_posterior_known_value():
    # LR = 1 / (1 + 4*0.8) = 1/4.2 ; posterior = (1/4.2) / (1 + 1/4.2)
    post, lr = bayesian_update(0.5, "bearish", 0.8)
    expected_lr = 1.0 / 4.2
    assert lr == pytest.approx(expected_lr, abs=1e-4)
    assert post == pytest.approx(expected_lr / (1 + expected_lr), abs=1e-4)
    assert post < 0.5


def test_neutral_is_identity():
    post, lr = bayesian_update(0.5, "neutral", 0.9)
    assert lr == 1.0
    assert post == 0.5


def test_bullish_monotonic_in_confidence():
    low, _ = bayesian_update(0.5, "bullish", 0.2)
    high, _ = bayesian_update(0.5, "bullish", 0.9)
    assert 0.5 < low < high


def test_market_price_as_prior_shifts_relatively():
    # A cheap market (1% YES) + strong bullish news stays cheap in absolute
    # terms — the mapping is intentionally conservative.
    post, lr = bayesian_update(0.01, "bullish", 0.8)
    assert lr == 4.2
    assert post > 0.01
    assert post < 0.10  # no runaway posterior


def test_prior_and_confidence_are_clamped():
    # prior 0 and 1 must not blow up (log/exp guards)
    p0, _ = bayesian_update(0.0, "bullish", 0.5)
    p1, _ = bayesian_update(1.0, "bearish", 0.5)
    assert 0.0 < p0 < 1.0
    assert 0.0 < p1 < 1.0
    # confidence above 1 is clamped to the max LR (5.0 for bullish)
    _, lr = bayesian_update(0.5, "bullish", 5.0)
    assert lr == 5.0


def test_log_odds_symmetry():
    # bullish and bearish at equal confidence are reciprocal in odds space.
    pb, _ = bayesian_update(0.5, "bullish", 0.6)
    pr, _ = bayesian_update(0.5, "bearish", 0.6)
    odds_b = pb / (1 - pb)
    odds_r = pr / (1 - pr)
    assert odds_b * odds_r == pytest.approx(1.0, abs=1e-3)


def test_heuristic_detects_bullish():
    e = _heuristic("SEC approves Bitcoin ETF", "a big bullish adoption milestone")
    assert e.sentiment == "bullish"
    assert e.provider == "heuristic"
    assert e.topic in {"SEC", "ETF", "BTC"}
    assert 0.5 < e.confidence <= 0.85


def test_heuristic_detects_bearish():
    e = _heuristic("Major exchange hacked, lawsuit filed", "fraud and exploit")
    assert e.sentiment == "bearish"
    assert e.confidence > 0.5


def test_heuristic_neutral_when_balanced():
    e = _heuristic("Market update", "no strong words here")
    assert e.sentiment == "neutral"
    assert e.confidence == 0.5
