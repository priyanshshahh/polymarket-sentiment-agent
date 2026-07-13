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
