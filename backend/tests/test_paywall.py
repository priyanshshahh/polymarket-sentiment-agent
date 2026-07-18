"""Paywall behavior: fail-hard pay-to validation + x402 gating.

This repo has no demo-teaser endpoint (see docs/PORT-PLAN.md — the demo
seeding layer was intentionally not ported), so the paid rationale
endpoint's own trust-model/provenance payload is exercised over in
test_track_record.py alongside the rest of the track-record work it
depends on.
"""
from __future__ import annotations

import pytest

from app.x402_setup import setup_x402, validate_pay_to

VALID_ADDR = "0x5190715b3aFd1076b1416F20e7E64F53B90e054e"
ZERO_ADDR = "0x" + "0" * 40


# ---------- validate_pay_to (fail-hard) ------------------------------------

def test_validate_rejects_empty():
    with pytest.raises(RuntimeError, match="X402_PAY_TO is not set"):
        validate_pay_to("")


def test_validate_rejects_zero_address():
    with pytest.raises(RuntimeError, match="zero address"):
        validate_pay_to(ZERO_ADDR)


def test_validate_rejects_malformed():
    for bad in ("0x1234", "not-an-address", "5190715b3aFd1076b1416F20e7E64F53B90e054e"):
        with pytest.raises(RuntimeError):
            validate_pay_to(bad)


def test_validate_accepts_real_address():
    assert validate_pay_to(VALID_ADDR) == VALID_ADDR


def test_setup_fails_hard_when_enabled_without_pay_to(monkeypatch):
    from fastapi import FastAPI
    from app import x402_setup

    monkeypatch.setattr(x402_setup.settings, "x402_enabled", True)
    monkeypatch.setattr(x402_setup.settings, "x402_pay_to", "")
    with pytest.raises(RuntimeError):
        setup_x402(FastAPI())


def test_setup_noop_when_disabled(monkeypatch):
    from fastapi import FastAPI
    from app import x402_setup

    monkeypatch.setattr(x402_setup.settings, "x402_enabled", False)
    app = FastAPI()
    before = len(app.user_middleware)
    setup_x402(app)
    assert len(app.user_middleware) == before


# ---------- x402 gating -----------------------------------------------------

def _paywalled_client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import x402_setup
    from app.api.routes import router

    monkeypatch.setattr(x402_setup.settings, "x402_enabled", True)
    monkeypatch.setattr(x402_setup.settings, "x402_pay_to", VALID_ADDR)
    app = FastAPI()
    setup_x402(app)
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_gated_route_returns_402_without_payment(monkeypatch, filled_trade):
    client = _paywalled_client(monkeypatch)
    r = client.get(f"/api/trade/{filled_trade}/rationale")
    assert r.status_code == 402


def test_non_gated_routes_stay_free_when_paywall_on(monkeypatch, filled_trade):
    client = _paywalled_client(monkeypatch)
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/public/ping").status_code == 200
