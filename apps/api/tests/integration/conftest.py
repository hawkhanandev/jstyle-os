"""Integration tests run against a real Postgres.

Set JSTYLE_TEST_DATABASE_URL (CI provides a service container). Each test session migrates a
fresh schema with Alembic; each test runs inside a transaction that is rolled back.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

URL = os.environ.get("JSTYLE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="JSTYLE_TEST_DATABASE_URL not set")


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    if not URL:
        pytest.skip("JSTYLE_TEST_DATABASE_URL not set")
    eng = create_engine(URL)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "..", "migrations")
    )
    cfg.set_main_option("sqlalchemy.url", URL)
    command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    trans.rollback()
    conn.close()
