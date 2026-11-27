"""Integration tests run against a real Postgres.

Set JSTYLE_TEST_DATABASE_URL (CI provides a service container). Each test session migrates a
fresh schema with Alembic; each test runs inside a transaction that is rolled back.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.main import app
from app.modules.auth.deps import CSRF_COOKIE, get_google
from app.modules.auth.google import GoogleIdentity

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


OWNER = "jessica@jstyle.example"


class FakeGoogle:
    def __init__(self) -> None:
        self.identity = GoogleIdentity(email=OWNER, email_verified=True, name="Jessica")
        self.last_challenge = ""

    def authorization_url(self, *, state: str, code_challenge: str, redirect_uri: str) -> str:
        self.last_challenge = code_challenge
        return f"https://accounts.google.test/auth?state={state}"

    def fetch_identity(self, *, code: str, code_verifier: str, redirect_uri: str) -> GoogleIdentity:
        assert code_verifier
        return self.identity


@pytest.fixture
def google() -> FakeGoogle:
    return FakeGoogle()


@pytest.fixture
def client(db: Session, google: FakeGoogle) -> Iterator[TestClient]:
    settings = Settings(
        allowed_email=OWNER, public_base_url="http://testserver", secret_key="test-secret"
    )
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_google] = lambda: google
    with TestClient(app, follow_redirects=False) as c:
        yield c
    app.dependency_overrides.clear()


def sign_in(client: TestClient) -> str:
    start = client.get("/api/auth/google/start")
    assert start.status_code == 302
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    res = client.get(
        "/api/auth/google/callback",
        params={"code": "abc", "state": state},
        headers={"user-agent": "Mozilla/5.0 (Macintosh; Mac OS X) Chrome/130"},
    )
    return res.headers["location"]


@pytest.fixture
def authed(client: TestClient) -> TestClient:
    """A client signed in as the business account, with the CSRF header preset."""
    sign_in(client)
    client.headers["x-csrf-token"] = client.cookies.get(CSRF_COOKIE) or ""
    return client
