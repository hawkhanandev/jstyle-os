from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session, utcnow
from app.main import app
from app.modules.auth.deps import CSRF_COOKIE
from app.modules.auth.google import GoogleIdentity
from app.modules.auth.models import UserSession
from app.modules.platform.models import AuditLog
from tests.integration.conftest import OWNER, FakeGoogle, sign_in


def test_allowed_account_signs_in_and_is_audited(client: TestClient, db: Session) -> None:
    assert sign_in(client) == "http://testserver/"
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == OWNER
    assert me.json()["device_label"] == "Chrome on Mac"
    actions = db.scalars(select(AuditLog.action)).all()
    assert "auth.login" in actions


def test_other_account_is_rejected(client: TestClient, google: FakeGoogle, db: Session) -> None:
    google.identity = GoogleIdentity(email="someone@gmail.com", email_verified=True)
    assert sign_in(client).endswith("/sign-in?error=not_allowed")
    assert client.get("/api/auth/me").status_code == 401
    assert "auth.login_rejected" in db.scalars(select(AuditLog.action)).all()


def test_unverified_email_is_rejected(client: TestClient, google: FakeGoogle) -> None:
    google.identity = GoogleIdentity(email=OWNER, email_verified=False)
    assert sign_in(client).endswith("error=not_allowed")


def test_state_mismatch_is_rejected(client: TestClient) -> None:
    client.get("/api/auth/google/start")
    res = client.get("/api/auth/google/callback", params={"code": "abc", "state": "forged"})
    assert res.headers["location"].endswith("error=expired")


def test_writes_need_csrf_token(client: TestClient) -> None:
    sign_in(client)
    assert client.post("/api/auth/logout").status_code == 403
    token = client.cookies.get(CSRF_COOKIE)
    assert client.post("/api/auth/logout", headers={"x-csrf-token": token}).status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_idle_session_expires(client: TestClient, db: Session) -> None:
    sign_in(client)
    row = db.scalars(select(UserSession)).one()
    row.last_seen_at = utcnow() - timedelta(hours=13)
    db.flush()
    assert client.get("/api/auth/me").status_code == 401


def test_sessions_list_and_logout_everywhere(client: TestClient, db: Session) -> None:
    sign_in(client)
    sessions = client.get("/api/auth/sessions").json()
    assert len(sessions) == 1 and sessions[0]["current"] is True
    token = client.cookies.get(CSRF_COOKIE)
    assert (
        client.post("/api/auth/logout-everywhere", headers={"x-csrf-token": token}).status_code
        == 204
    )
    assert all(r.revoked_at for r in db.scalars(select(UserSession)))


def test_dev_login_only_in_local(db: Session) -> None:
    app.dependency_overrides[get_session] = lambda: db
    try:
        for env, expected in (("production", 404), ("local", 303)):
            settings = Settings(env=env, allowed_email=OWNER, public_base_url="http://testserver")
            app.dependency_overrides[get_settings] = lambda s=settings: s
            with TestClient(app, follow_redirects=False) as c:
                assert c.get("/api/auth/config").json()["dev_login"] is (env == "local")
                assert c.post("/api/auth/dev-login").status_code == expected
    finally:
        app.dependency_overrides.clear()


def test_google_start_without_credentials_redirects_back(db: Session) -> None:
    settings = Settings(env="local", allowed_email=OWNER, public_base_url="http://testserver")
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app, follow_redirects=False) as c:
            assert c.get("/api/auth/config").json() == {"dev_login": True, "google": False}
            r = c.get("/api/auth/google/start")
            assert r.status_code == 302
            assert r.headers["location"] == "/sign-in?error=google_not_configured"
    finally:
        app.dependency_overrides.clear()
