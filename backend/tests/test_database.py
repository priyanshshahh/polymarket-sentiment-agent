"""normalize_db_url: provider-style Postgres URLs -> the psycopg2 dialect."""
from __future__ import annotations

from app.database import normalize_db_url


def test_normalizes_postgres_scheme():
    assert normalize_db_url("postgres://u:p@host/db") == "postgresql+psycopg2://u:p@host/db"


def test_normalizes_postgresql_scheme():
    assert normalize_db_url("postgresql://u:p@host/db") == "postgresql+psycopg2://u:p@host/db"


def test_leaves_already_dialected_url_alone():
    url = "postgresql+psycopg2://u:p@host/db"
    assert normalize_db_url(url) == url


def test_leaves_sqlite_url_alone():
    assert normalize_db_url("sqlite:///./doa.db") == "sqlite:///./doa.db"
