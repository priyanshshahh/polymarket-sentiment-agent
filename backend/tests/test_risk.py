"""The Overseer — hard risk gates."""
from __future__ import annotations

from app.config import settings
from app.modules.risk import TradePlan, evaluate, set_kill_switch


def _plan(edge=0.15, size=10.0) -> TradePlan:
    return TradePlan(
        condition_id="cond1",
        market_question="Q?",
        outcome="Yes",
        token_id="t1",
        side="BUY",
        price=0.40,
        model_probability=0.55,
        edge=edge,
        size_usdc=size,
        signal_id=1,
        snapshot_id=1,
        idem_key="cond1:Yes:1",
    )


def test_approves_good_plan():
    d = evaluate(_plan(edge=0.15))
    assert d.approved is True
    assert d.plan is not None


def test_rejects_when_kill_switch_active():
    set_kill_switch(True)
    try:
        d = evaluate(_plan())
        assert d.approved is False
        assert "KILL_SWITCH" in d.reason
    finally:
        set_kill_switch(False)


def test_rejects_edge_below_threshold():
    # default edge_threshold is 0.08
    d = evaluate(_plan(edge=0.01))
    assert d.approved is False
    assert "Edge" in d.reason


def test_rejects_non_positive_size():
    d = evaluate(_plan(size=0.0))
    assert d.approved is False
    assert "Non-positive" in d.reason


def test_resizes_oversized_plan_to_cap():
    over = settings.max_usdc_per_trade + 50.0
    d = evaluate(_plan(size=over))
    assert d.approved is True
    assert d.plan.size_usdc == settings.max_usdc_per_trade


def test_edge_threshold_boundary():
    # exactly at threshold is below the strict `<` comparison? abs(edge) < thr
    d = evaluate(_plan(edge=settings.edge_threshold))
    assert d.approved is True  # equal is NOT rejected
