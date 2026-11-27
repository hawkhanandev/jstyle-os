from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.modules.auth.deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    Account,
    client_ip,
    get_google,
)
from app.modules.auth.google import GoogleIdentity, GoogleOAuth, new_pkce_pair
from app.modules.auth.models import UserSession
from app.modules.auth.service import (
    SignInRejected,
    complete_sign_in,
    read_state,
    revoke,
    revoke_all,
    sign_state,
)

router = APIRouter(prefix="/auth", tags=["auth"])
STATE_COOKIE = "jstyle_oauth"

DB = Annotated[Session, Depends(get_session)]
Cfg = Annotated[Settings, Depends(get_settings)]
Google = Annotated[GoogleOAuth, Depends(get_google)]


def _redirect_uri(settings: Settings) -> str:
    return f"{settings.public_base_url.rstrip('/')}/api/auth/google/callback"


@router.get("/google/start")
def google_start(settings: Cfg, google: Google) -> RedirectResponse:
    if not settings.google_configured:
        # Locally Google is optional: send the person back with a clear message
        # instead of handing them to Google with an empty client id.
        return RedirectResponse("/sign-in?error=google_not_configured", status_code=302)
    state = secrets.token_urlsafe(24)
    verifier, challenge = new_pkce_pair()
    url = google.authorization_url(
        state=state, code_challenge=challenge, redirect_uri=_redirect_uri(settings)
    )
    res = RedirectResponse(url, status_code=302)
    res.set_cookie(
        STATE_COOKIE,
        sign_state(settings.secret_key, {"state": state, "verifier": verifier}),
        max_age=600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/api/auth",
    )
    return res


@router.get("/google/callback")
def google_callback(
    request: Request, db: DB, settings: Cfg, google: Google, code: str = "", state: str = ""
) -> RedirectResponse:
    base = settings.public_base_url.rstrip("/")
    saved = read_state(settings.secret_key, request.cookies.get(STATE_COOKIE))
    if not saved or not code or not secrets.compare_digest(saved["state"], state):
        return RedirectResponse(f"{base}/sign-in?error=expired", status_code=302)

    identity = google.fetch_identity(
        code=code, code_verifier=saved["verifier"], redirect_uri=_redirect_uri(settings)
    )
    try:
        new = complete_sign_in(
            db,
            settings,
            identity,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except SignInRejected:
        res = RedirectResponse(f"{base}/sign-in?error=not_allowed", status_code=302)
        res.delete_cookie(STATE_COOKIE, path="/api/auth")
        return res

    res = RedirectResponse(f"{base}/", status_code=302)
    res.delete_cookie(STATE_COOKIE, path="/api/auth")
    _set_session_cookies(res, settings, new.token, new.csrf_token)
    return res


def _set_session_cookies(res: Response, settings: Settings, token: str, csrf: str) -> None:
    max_age = settings.session_absolute_days * 86400
    res.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    # Readable by the web app, which echoes it in the X-CSRF-Token header.
    res.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def _dev_login_enabled(settings: Settings) -> bool:
    return settings.env == "local" and bool(settings.allowed_email)


@router.get("/config")
def auth_config(settings: Cfg) -> dict[str, bool]:
    return {"dev_login": _dev_login_enabled(settings), "google": settings.google_configured}


@router.post("/dev-login")
def dev_login(request: Request, db: DB, settings: Cfg) -> RedirectResponse:
    """Local development only: sign in as the allowed account without Google.

    Refused unless JSTYLE_ENV=local. Staging and production never enable it.
    """
    if not _dev_login_enabled(settings):
        raise HTTPException(404)
    identity = GoogleIdentity(
        email=settings.allowed_email.strip().lower(), email_verified=True, name="Local development"
    )
    new = complete_sign_in(
        db, settings, identity, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    res = RedirectResponse(f"{settings.public_base_url.rstrip('/')}/", status_code=303)
    _set_session_cookies(res, settings, new.token, new.csrf_token)
    return res


class Me(BaseModel):
    email: str
    display_name: str | None
    session_id: uuid.UUID
    device_label: str | None


@router.get("/me")
def me(account: Account) -> Me:
    return Me(
        email=account.user.email,
        display_name=account.user.display_name,
        session_id=account.session.id,
        device_label=account.session.device_label,
    )


@router.post("/logout", status_code=204)
def logout(account: Account, db: DB) -> Response:
    revoke(db, account.session.id, account.actor)
    res = Response(status_code=204)
    res.delete_cookie(SESSION_COOKIE, path="/")
    res.delete_cookie(CSRF_COOKIE, path="/")
    return res


class SessionOut(BaseModel):
    id: uuid.UUID
    device_label: str | None
    ip: str | None
    created_at: datetime
    last_seen_at: datetime
    current: bool


@router.get("/sessions")
def list_sessions(account: Account, db: DB) -> list[SessionOut]:
    rows = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == account.user.id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.last_seen_at.desc())
    )
    return [
        SessionOut(
            id=r.id,
            device_label=r.device_label,
            ip=str(r.ip) if r.ip else None,
            created_at=r.created_at,
            last_seen_at=r.last_seen_at,
            current=r.id == account.session.id,
        )
        for r in rows
    ]


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: uuid.UUID, account: Account, db: DB) -> Response:
    row = db.get(UserSession, session_id)
    if row is None or row.user_id != account.user.id:
        raise HTTPException(404, detail={"code": "not_found", "message": "Session not found."})
    revoke(db, session_id, account.actor, action="auth.session_revoked")
    return Response(status_code=204)


@router.post("/logout-everywhere", status_code=204)
def logout_everywhere(account: Account, db: DB) -> Response:
    revoke_all(db, account.user.id, account.actor)
    res = Response(status_code=204)
    res.delete_cookie(SESSION_COOKIE, path="/")
    res.delete_cookie(CSRF_COOKIE, path="/")
    return res
