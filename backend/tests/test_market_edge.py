"""Market-edge comparison + signal->market matching in the orchestrator.

Edge = re-run the Bayesian update using the *market price* as the prior,
then subtract the market price. Positive edge => model thinks YES is
underpriced.
"""
from __future__ import annotations

from app.models import MarketSnapshot, Signal
from app.orchestrator import (
    _decide_side_and_target_prob,
    _match_market_for_signal,
    _topic_to_keywords,
)


def _sig(topic="BTC", sentiment="bullish", confidence=0.8) -> Signal:
    return Signal(topic=topic, sentiment=sentiment, confidence=confidence)


def _snap(question, outcome="Yes", price=0.5, cid="c1", slug="") -> MarketSnapshot:
    return MarketSnapshot(
        condition_id=cid,
        slug=slug or question.lower().replace(" ", "-"),
        question=question,
        outcome=outcome,
        token_id="t1",
        price=price,
    )


def test_topic_keywords_mapping():
    assert "bitcoin" in _topic_to_keywords("BTC")
    assert "fed" in _topic_to_keywords("FED")
    assert _topic_to_keywords("UNKNOWN") == []


def test_bullish_signal_yields_positive_edge():
    sig = _sig(sentiment="bullish", confidence=0.8)
    side, target = _decide_side_and_target_prob(sig, snap_price=0.30)
    assert side == "BUY"
    edge = target - 0.30
    assert edge > 0  # bullish news pushes posterior above market price


def test_bearish_signal_yields_negative_edge():
    sig = _sig(sentiment="bearish", confidence=0.8)
    _, target = _decide_side_and_target_prob(sig, snap_price=0.30)
    edge = target - 0.30
    assert edge < 0  # bearish news pushes posterior below market price


def test_neutral_signal_zero_edge():
    sig = _sig(sentiment="neutral", confidence=0.9)
    _, target = _decide_side_and_target_prob(sig, snap_price=0.42)
    assert abs(target - 0.42) < 1e-6


def test_match_prefers_yes_side_with_topic_overlap():
    sig = _sig(topic="BTC")
    snaps = [
        _snap("Will Ethereum flip Bitcoin?", outcome="No", cid="a"),
        _snap("Will Bitcoin hit 100k?", outcome="Yes", cid="b"),
        _snap("Will the Fed cut rates?", outcome="Yes", cid="c"),
    ]
    match = _match_market_for_signal(sig, snaps)
    assert match is not None
    assert match.condition_id == "b"
    assert match.outcome.lower() in {"yes", "true"}


def test_match_skips_non_yes_outcomes():
    sig = _sig(topic="BTC")
    snaps = [_snap("Will Bitcoin hit 100k?", outcome="No", cid="b")]
    assert _match_market_for_signal(sig, snaps) is None


def test_match_returns_none_when_empty():
    assert _match_market_for_signal(_sig(), []) is None
