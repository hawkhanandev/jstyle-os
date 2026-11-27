from __future__ import annotations

import hmac
import ipaddress
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.modules.auth.google import GoogleOAuth, GoogleOAuthClient
from app.modules.auth.models import User, UserSession
from app.modules.auth.service import resolve_session
from app.modules.platform.audit import Actor

SESSION_COOKIE = "jstyle_session"
CSRF_COOKIE = "jstyle_csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_google() -> GoogleOAuth:
    s = get_settings()
    return GoogleOAuthClient(s.google_client_id, s.google_client_secret)


def client_ip(request: Request) -> str | None:
    # Caddy sets X-Forwarded-For; the API is only reachable through Caddy.
    fwd = request.headers.get("x-forwarded-for")
    raw = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


@dataclass(frozen=True)
class CurrentAccount:
    user: User
    session: UserSession
    actor: Actor


def current_account(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentAccount:
    found = resolve_session(db, settings, request.cookies.get(SESSION_COOKIE))
    if found is None:
        raise HTTPException(401, detail={"code": "not_signed_in", "message": "Please sign in."})
    sess, user = found
    if request.method not in SAFE_METHODS:
        header = request.headers.get(CSRF_HEADER, "")
        if not header or not hmac.compare_digest(header, sess.csrf_token):
            raise HTTPException(403, detail={"code": "csrf_failed", "message": "Reload the page."})
    actor = Actor(
        account_email=user.email,
        session_id=sess.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        device_label=sess.device_label,
    )
    return CurrentAccount(user=user, session=sess, actor=actor)


Account = Annotated[CurrentAccount, Depends(current_account)]
