from __future__ import annotations

import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.modules.auth.deps import Account
from app.modules.auth.google import new_pkce_pair
from app.modules.auth.service import read_state, sign_state
from app.modules.google import service
from app.modules.google.client import SCOPES, AccessRevoked, GoogleApi, GoogleError, HttpGoogleApi

router = APIRouter(prefix="/integrations/google", tags=["google"])
STATE_COOKIE = "jstyle_google_connect"
COOKIE_PATH = "/api/integrations/google"
NOT_CONNECTED = {"code": "not_connected", "message": "Connect Google first."}


def get_google_api() -> GoogleApi:
    s = get_settings()
    return HttpGoogleApi(s.google_client_id, s.google_client_secret)


DB = Annotated[Session, Depends(get_session)]
Cfg = Annotated[Settings, Depends(get_settings)]
Api = Annotated[GoogleApi, Depends(get_google_api)]


def _redirect_uri(settings: Settings) -> str:
    return f"{settings.public_base_url.rstrip('/')}{COOKIE_PATH}/callback"


def _back(settings: Settings, outcome: str) -> RedirectResponse:
    base = settings.public_base_url.rstrip("/")
    res = RedirectResponse(f"{base}/settings?google={outcome}#google", status_code=302)
    res.delete_cookie(STATE_COOKIE, path=COOKIE_PATH)
    return res


@router.get("")
def status(account: Account, db: DB, settings: Cfg) -> dict[str, Any]:
    return service.to_dict(service.current(db), settings.google_configured)


@router.get("/start")
def start(account: Account, settings: Cfg, api: Api, login_hint: str = "") -> RedirectResponse:
    if not settings.google_configured:
        return _back(settings, "not_configured")
    state = secrets.token_urlsafe(24)
    verifier, challenge = new_pkce_pair()
    url = api.authorization_url(
        state=state,
        code_challenge=challenge,
        redirect_uri=_redirect_uri(settings),
        login_hint=login_hint or None,
    )
    res = RedirectResponse(url, status_code=302)
    res.set_cookie(
        STATE_COOKIE,
        sign_state(settings.secret_key, {"state": state, "verifier": verifier}),
        max_age=600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path=COOKIE_PATH,
    )
    return res


@router.get("/callback")
def callback(
    request: Request,
    account: Account,
    db: DB,
    settings: Cfg,
    api: Api,
    code: str = "",
    state: str = "",
    error: str = "",
) -> RedirectResponse:
    if error:
        return _back(settings, "denied")
    saved = read_state(settings.secret_key, request.cookies.get(STATE_COOKIE))
    if not saved or not code or not secrets.compare_digest(saved["state"], state):
        return _back(settings, "expired")
    try:
        grant = api.exchange(
            code=code, code_verifier=saved["verifier"], redirect_uri=_redirect_uri(settings)
        )
    except GoogleError:
        return _back(settings, "failed")
    missing = [s for s in SCOPES if s.startswith("https://") and s not in grant.scopes]
    if missing:
        api.revoke(grant.refresh_token)
        return _back(settings, "missing_permissions")
    service.save_grant(db, settings, grant, account.actor)
    db.commit()
    return _back(settings, "connected")


class Options(BaseModel):
    send_enabled: bool | None = None
    calendar_enabled: bool | None = None


@router.put("/options")
def options(body: Options, account: Account, db: DB, settings: Cfg) -> dict[str, Any]:
    conn = service.current(db)
    if conn is None:
        raise HTTPException(
            404, detail={"code": "not_connected", "message": "Connect Google first."}
        )
    turning_on_calendar = body.calendar_enabled and not conn.calendar_enabled
    service.set_options(
        db, conn, account.actor, send=body.send_enabled, calendar=body.calendar_enabled
    )
    if turning_on_calendar:
        service.resync_all_calendar(db)
    db.commit()
    return service.to_dict(conn, settings.google_configured)


@router.post("/sync")
def sync_now(account: Account, db: DB, settings: Cfg, api: Api) -> dict[str, Any]:
    try:
        attached = service.sync_inbox(db, api, settings)
    except service.NotConnected as exc:
        raise HTTPException(404, detail=NOT_CONNECTED) from exc
    except (AccessRevoked, GoogleError) as exc:
        db.commit()  # keep last_error
        raise HTTPException(
            502, detail={"code": "google_error", "message": f"Gmail sync failed: {exc}"}
        ) from exc
    db.commit()
    return {"attached": attached, **service.to_dict(service.current(db), True)}


@router.post("/disconnect")
def disconnect(account: Account, db: DB, settings: Cfg, api: Api) -> dict[str, Any]:
    service.disconnect(db, api, settings, account.actor)
    db.commit()
    return service.to_dict(None, settings.google_configured)
