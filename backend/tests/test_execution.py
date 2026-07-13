"""The Trader — paper fills, idempotency, and the LIVE safety contract."""
from __future__ import annotations

import pytest

from app.config import settings
from app.modules import execution
from app.modules.execution import _execute_live, _execute_paper, execute, make_idem_key
from app.modules.risk import TradePlan


def _plan(idem="cond1:Yes:1", size=10.0, price=0.40) -> TradePlan:
    return TradePlan(
        condition_id="cond1",
        market_question="Will BTC hit 100k?",
        outcome="Yes",
        token_id="t1",
        side="BUY",
        price=price,
        model_probability=0.55,
        edge=0.15,
        size_usdc=size,
        signal_id=1,
        snapshot_id=1,
        idem_key=idem,
    )


def test_idem_key_is_deterministic():
    assert make_idem_key("c", "Yes", 7) == "c:Yes:7"
    assert make_idem_key("c", "Yes", None) == "c:Yes:none"


def test_paper_fill_math():
    trade = _execute_paper(_plan(size=10.0, price=0.40))
    assert trade.mode == "PAPER"
    assert trade.status == "FILLED"
    assert trade.price == 0.40
    assert trade.shares == pytest.approx(10.0 / 0.40)  # 25 shares
    assert trade.fees_usdc == 0.0


def test_paper_fill_price_is_clamped():
    # price outside (0.01, 0.99) is clamped
    hi = _execute_paper(_plan(price=1.5))
    lo = _execute_paper(_plan(price=-0.2))
    assert hi.price == 0.99
    assert lo.price == 0.01


def test_execute_paper_persists_and_is_idempotent(monkeypatch):
    monkeypatch.setattr(settings, "trading_mode", "PAPER")
    first = execute(_plan(idem="dup:Yes:1"))
    assert first is not None
    assert first.id is not None
    # same idem_key -> unique constraint -> no-op (None)
    second = execute(_plan(idem="dup:Yes:1"))
    assert second is None


def test_live_execution_raises_not_implemented():
    # The honest safety contract: LIVE must never silently execute.
    with pytest.raises(NotImplementedError):
        _execute_live(_plan())


def test_execute_dispatches_to_live_and_raises(monkeypatch):
    monkeypatch.setattr(settings, "trading_mode", "LIVE")
    with pytest.raises(NotImplementedError):
        execute(_plan(idem="live:Yes:1"))


def test_mark_to_market_updates_open_pnl(monkeypatch):
    monkeypatch.setattr(settings, "trading_mode", "PAPER")
    trade = execute(_plan(idem="mtm:Yes:1", price=0.40))
    assert trade is not None

    # price rose to 0.60 -> unrealized profit on the open position
    execution.mark_to_market(lambda cid, outcome: 0.60)

    from app.database import session_scope
    from app.models import Trade

    with session_scope() as s:
        row = s.query(Trade).filter(Trade.idem_key == "mtm:Yes:1").one()
        assert row.exit_price == 0.60
        assert row.pnl_usdc == pytest.approx((0.60 - 0.40) * row.shares)
        assert row.pnl_usdc > 0
