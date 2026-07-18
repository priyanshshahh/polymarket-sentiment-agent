"""Shared pytest fixtures.

The app binds its SQLAlchemy engine to ``settings.database_url`` at import
time, so we must point it at an isolated temp SQLite file BEFORE any app
module is imported. That happens at the very top of this file, which pytest
loads before collecting any test module.
"""
from __future__ import annotations

import os
import tempfile

# --- isolate the DB before importing anything from `app` --------------------
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="polyagent-test-"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
# Keep the paywall off so route smoke tests don't require x402/EVM wiring.
os.environ.pop("X402_PAY_TO", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """Drop + recreate all tables before every test for full isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    """FastAPI TestClient.

    Constructed WITHOUT the ``with`` context manager on purpose: that keeps
    the lifespan (which would spin up the live network agent loop) from
    running, so route smoke tests stay hermetic and fast.
    """
    return TestClient(app)


@pytest.fixture()
def filled_trade():
    """Insert a full causal chain (NewsItem -> Signal -> MarketSnapshot ->
    FILLED Trade) and return the trade id.

    Several endpoints (portfolio, trade rationale, x402 gating) only exercise
    their real code path once at least one real, filled trade exists — the
    empty-DB smoke tests never touch that path.
    """
    from app.database import session_scope
    from app.models import MarketSnapshot, NewsItem, Signal, Trade

    with session_scope() as s:
        news = NewsItem(
            source="test",
            url="https://example.com/test-headline",
            title="SEC approves Bitcoin ETF",
            summary="A big bullish adoption milestone.",
        )
        s.add(news)
        s.flush()

        sig = Signal(
            news_item_id=news.id,
            sentiment="bullish",
            confidence=0.8,
            topic="BTC",
            entities="[]",
            rationale="Bullish: ETF approval headline.",
            llm_provider="heuristic",
            prior=0.5,
            posterior=0.8077,
            likelihood_ratio=4.2,
        )
        s.add(sig)
        s.flush()

        snap = MarketSnapshot(
            condition_id="0xcondition",
            slug="will-btc-hit-100k",
            question="Will Bitcoin hit $100k?",
            outcome="Yes",
            token_id="t1",
            price=0.4,
        )
        s.add(snap)
        s.flush()

        trade = Trade(
            idem_key="test-idem-key-1",
            status="FILLED",
            condition_id=snap.condition_id,
            market_question=snap.question,
            outcome=snap.outcome,
            side="BUY",
            price=snap.price,
            size_usdc=10.0,
            shares=25.0,
            model_probability=0.8077,
            edge=0.4077,
            signal_id=sig.id,
            snapshot_id=snap.id,
        )
        s.add(trade)
        s.flush()
        return trade.id
