"""FastAPI route smoke tests via TestClient (no network, no lifespan)."""
from __future__ import annotations

import pytest

from app.config import settings
from app.main import app


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["mode"] in {"PAPER", "LIVE"}


def test_public_ping(client):
    r = client.get("/api/public/ping")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "poly-agent"
    assert body["trade_count"] == 0
    assert body["signal_count"] == 0


def test_status(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == settings.trading_mode
    assert body["llm_provider"] in {"groq", "openai", "anthropic", "heuristic"}


def test_empty_list_endpoints(client):
    for path in ("/api/news", "/api/signals", "/api/trades", "/api/markets",
                 "/api/logs", "/api/equity-curve"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.json() == [], path


def test_portfolio_empty(client):
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    body = r.json()
    assert body["realized_pnl_usdc"] == 0.0
    assert body["open_positions"] == []


def test_portfolio_with_filled_trade_does_not_500(client, filled_trade):
    # Regression: Trade.created_at round-trips tz-naive from SQLite, but the
    # 24h cutoff used to be tz-aware, so this used to raise
    # "can't compare offset-naive and offset-aware datetimes".
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    body = r.json()
    assert len(body["open_positions"]) == 1
    assert body["open_positions"][0]["id"] == filled_trade
    assert body["open_positions_usdc"] == pytest.approx(10.0)
    assert body["daily_pnl_usdc"] == pytest.approx(0.0)


def test_kill_switch_toggle(client, monkeypatch):
    # /api/kill-switch is admin-gated (see test_admin_auth.py for the full
    # 503/401/200 auth-behavior spec) — authenticate here to exercise the
    # underlying toggle behavior.
    monkeypatch.setattr(settings, "admin_token", "s3cret")
    headers = {"Authorization": "Bearer s3cret"}
    r = client.post("/api/kill-switch", json={"enabled": True}, headers=headers)
    assert r.status_code == 200
    assert r.json()["kill_switch"] is True
    # reflected in status
    assert client.get("/api/status").json()["kill_switch"] is True
    client.post("/api/kill-switch", json={"enabled": False}, headers=headers)


def test_rationale_not_found(client):
    r = client.get("/api/trade/99999/rationale")
    assert r.status_code == 200
    assert r.json() == {"error": "not found"}


def test_cors_is_not_wildcard():
    # Regression guard: this payment-handling API must never allow "*".
    from starlette.middleware.cors import CORSMiddleware

    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert cors, "CORS middleware missing"
    origins = cors[0].kwargs["allow_origins"]
    assert "*" not in origins
    assert "http://localhost:5173" in origins
