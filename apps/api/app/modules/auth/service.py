from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import utcnow
from app.modules.auth.google import GoogleIdentity
from app.modules.auth.models import User, UserSession
from app.modules.platform.audit import Actor, write_audit

STATE_TTL_SECONDS = 600


class SignInRejected(Exception):
    """The Google account is not the allowed business account."""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def device_label(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    os_name = next(
        (
            n
            for k, n in [
                ("iphone", "iPhone"),
                ("ipad", "iPad"),
                ("android", "Android"),
                ("mac os", "Mac"),
                ("windows", "Windows"),
                ("linux", "Linux"),
            ]
            if k in ua
        ),
        "Unknown device",
    )
    browser = next(
        (
            n
            for k, n in [
                ("edg/", "Edge"),
                ("chrome/", "Chrome"),
                ("firefox/", "Firefox"),
                ("safari/", "Safari"),
            ]
            if k in ua
        ),
        None,
    )
    return f"{browser} on {os_name}" if browser else os_name


# --- OAuth state cookie: signed, short-lived, carries the PKCE verifier -----------------------


def sign_state(secret: str, payload: dict[str, str]) -> str:
    body = urlsafe_b64encode(json.dumps({**payload, "ts": int(time.time())}).encode()).decode()
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def read_state(secret: str, cookie: str | None) -> dict[str, str] | None:
    if not cookie or "." not in cookie:
        return None
    body, sig = cookie.rsplit(".", 1)
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    data = json.loads(urlsafe_b64decode(body.encode()))
    if int(time.time()) - int(data.get("ts", 0)) > STATE_TTL_SECONDS:
        return None
    return {k: str(v) for k, v in data.items()}


# --- Sessions ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class NewSession:
    token: str
    csrf_token: str
    session: UserSession


def complete_sign_in(
    db: Session,
    settings: Settings,
    identity: GoogleIdentity,
    *,
    ip: str | None,
    user_agent: str | None,
) -> NewSession:
    allowed = settings.allowed_email.strip().lower()
    actor = Actor(
        account_email=identity.email,
        ip=ip,
        user_agent=user_agent,
        device_label=device_label(user_agent),
    )
    if not allowed or identity.email.lower() != allowed or not identity.email_verified:
        write_audit(db, actor, "auth.login_rejected", after={"email": identity.email})
        db.commit()
        raise SignInRejected(identity.email)

    now = utcnow()
    user = db.scalar(select(User).where(User.email == allowed))
    if user is None:
        user = User(email=allowed, display_name=identity.name)
        db.add(user)
    user.last_login_at = now
    db.flush()

    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    row = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=csrf,
        last_seen_at=now,
        expires_at=now + timedelta(days=settings.session_absolute_days),
        ip=ip,
        user_agent=user_agent,
        device_label=actor.device_label,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        Actor(**{**actor.__dict__, "session_id": row.id}),
        "auth.login",
        entity_type="session",
        entity_id=row.id,
    )
    db.commit()
    return NewSession(token=token, csrf_token=csrf, session=row)


def resolve_session(
    db: Session, settings: Settings, token: str | None, now: datetime | None = None
) -> tuple[UserSession, User] | None:
    if not token:
        return None
    now = now or utcnow()
    row = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        return None
    if now - row.last_seen_at > timedelta(hours=settings.session_idle_hours):
        return None
    user = db.get(User, row.user_id)
    if user is None or user.email != settings.allowed_email.strip().lower():
        return None
    # Touch at most once a minute to avoid a write per request.
    if now - row.last_seen_at > timedelta(minutes=1):
        row.last_seen_at = now
        db.commit()
    return row, user


def revoke(db: Session, session_id: uuid.UUID, actor: Actor, action: str = "auth.logout") -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.id == session_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    write_audit(db, actor, action, entity_type="session", entity_id=session_id)
    db.commit()


def revoke_all(db: Session, user_id: uuid.UUID, actor: Actor) -> int:
    result = db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    write_audit(db, actor, "auth.logout_everywhere", entity_type="user", entity_id=user_id)
    db.commit()
    return int(getattr(result, "rowcount", 0) or 0)
