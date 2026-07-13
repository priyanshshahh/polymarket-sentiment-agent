"""FastAPI route smoke tests via TestClient (no network, no lifespan)."""
from __future__ import annotations

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


def test_kill_switch_toggle(client):
    r = client.post("/api/kill-switch", json={"enabled": True})
    assert r.status_code == 200
    assert r.json()["kill_switch"] is True
    # reflected in status
    assert client.get("/api/status").json()["kill_switch"] is True
    client.post("/api/kill-switch", json={"enabled": False})


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
