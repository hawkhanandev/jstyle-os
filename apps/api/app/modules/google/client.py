"""Google OAuth, Gmail and Calendar over plain HTTPS. Behind a protocol so tests use a fake."""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR = "https://www.googleapis.com/calendar/v3/calendars"

# Read mail, send mail, and manage events. Nothing else: no delete, no settings, no contacts.
SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
]


class GoogleError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Google API {status}: {message}")
        self.status = status


class HistoryExpired(Exception):
    """Gmail no longer has history that old; start again from the current point."""


class AccessRevoked(Exception):
    """The refresh token was revoked or expired; the account must be connected again."""


@dataclass(frozen=True)
class Grant:
    email: str
    refresh_token: str
    scopes: list[str]


@dataclass(frozen=True)
class RawMessage:
    id: str
    thread_id: str
    label_ids: list[str]
    raw: bytes


@dataclass
class HistoryPage:
    message_ids: list[str] = field(default_factory=list)
    history_id: str = ""


class GoogleSession(Protocol):
    def profile(self) -> tuple[str, str]: ...  # (email, history_id)

    def history(self, start_history_id: str) -> HistoryPage: ...

    def recent_inbox_ids(self, newer_than_days: int) -> list[str]: ...

    def get_raw(self, message_id: str) -> RawMessage: ...

    def send_raw(self, raw: bytes, thread_id: str | None) -> tuple[str, str]: ...

    def put_event(self, calendar_id: str, event_id: str, body: dict[str, Any]) -> None: ...

    def delete_event(self, calendar_id: str, event_id: str) -> None: ...


class GoogleApi(Protocol):
    def authorization_url(
        self, *, state: str, code_challenge: str, redirect_uri: str, login_hint: str | None
    ) -> str: ...

    def exchange(self, *, code: str, code_verifier: str, redirect_uri: str) -> Grant: ...

    def session(self, refresh_token: str) -> GoogleSession: ...

    def revoke(self, refresh_token: str) -> None: ...


def _check(res: httpx.Response) -> httpx.Response:
    if res.status_code >= 400:
        try:
            msg = res.json().get("error", {})
            msg = msg.get("message") if isinstance(msg, dict) else str(msg)
        except ValueError:
            msg = res.text[:200]
        raise GoogleError(res.status_code, str(msg))
    return res


class HttpGoogleApi:
    def __init__(self, client_id: str, client_secret: str, timeout: float = 20.0) -> None:
        self.client_id, self.client_secret, self.timeout = client_id, client_secret, timeout

    def authorization_url(
        self, *, state: str, code_challenge: str, redirect_uri: str, login_hint: str | None
    ) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
        if login_hint:
            params["login_hint"] = login_hint
        return f"{AUTH_URL}?{urlencode(params)}"

    def exchange(self, *, code: str, code_verifier: str, redirect_uri: str) -> Grant:
        with httpx.Client(timeout=self.timeout) as http:
            tok = _check(
                http.post(
                    TOKEN_URL,
                    data={
                        "code": code,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                        "code_verifier": code_verifier,
                    },
                )
            ).json()
            info = _check(
                http.get(USERINFO_URL, headers={"Authorization": f"Bearer {tok['access_token']}"})
            ).json()
        if "refresh_token" not in tok:
            raise GoogleError(400, "Google did not return a refresh token")
        return Grant(
            email=str(info["email"]).lower(),
            refresh_token=tok["refresh_token"],
            scopes=str(tok.get("scope", "")).split(),
        )

    def session(self, refresh_token: str) -> GoogleSession:
        return HttpGoogleSession(self, refresh_token)

    def revoke(self, refresh_token: str) -> None:
        with httpx.Client(timeout=self.timeout) as http:
            http.post(REVOKE_URL, data={"token": refresh_token})


class HttpGoogleSession:
    def __init__(self, api: HttpGoogleApi, refresh_token: str) -> None:
        self.api = api
        self.refresh_token = refresh_token
        self._token: str | None = None
        self._expires = 0.0
        self.http = httpx.Client(timeout=api.timeout)

    def _auth(self) -> dict[str, str]:
        if self._token is None or time.monotonic() > self._expires:
            res = self.http.post(
                TOKEN_URL,
                data={
                    "client_id": self.api.client_id,
                    "client_secret": self.api.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            if res.status_code == 400 and "invalid_grant" in res.text:
                raise AccessRevoked("Google access was revoked or expired")
            data = _check(res).json()
            self._token = data["access_token"]
            self._expires = time.monotonic() + int(data.get("expires_in", 3600)) - 60
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, url: str, **params: Any) -> dict[str, Any]:
        result: dict[str, Any] = _check(
            self.http.get(url, params=params, headers=self._auth())
        ).json()
        return result

    def profile(self) -> tuple[str, str]:
        p = self._get(f"{GMAIL}/profile")
        return str(p["emailAddress"]).lower(), str(p["historyId"])

    def history(self, start_history_id: str) -> HistoryPage:
        page = HistoryPage(history_id=start_history_id)
        token: str | None = None
        while True:
            params: dict[str, Any] = {
                "startHistoryId": start_history_id,
                "historyTypes": "messageAdded",
                "labelId": "INBOX",
            }
            if token:
                params["pageToken"] = token
            try:
                data = self._get(f"{GMAIL}/history", **params)
            except GoogleError as exc:
                if exc.status == 404:
                    raise HistoryExpired() from exc
                raise
            for h in data.get("history", []):
                for added in h.get("messagesAdded", []):
                    mid = added["message"]["id"]
                    if mid not in page.message_ids:
                        page.message_ids.append(mid)
            page.history_id = str(data.get("historyId", page.history_id))
            token = data.get("nextPageToken")
            if not token:
                return page

    def recent_inbox_ids(self, newer_than_days: int) -> list[str]:
        data = self._get(
            f"{GMAIL}/messages", q=f"in:inbox newer_than:{newer_than_days}d", maxResults=200
        )
        return [m["id"] for m in data.get("messages", [])]

    def get_raw(self, message_id: str) -> RawMessage:
        m = self._get(f"{GMAIL}/messages/{message_id}", format="raw")
        return RawMessage(
            id=m["id"],
            thread_id=m["threadId"],
            label_ids=list(m.get("labelIds", [])),
            raw=base64.urlsafe_b64decode(m["raw"] + "=" * (-len(m["raw"]) % 4)),
        )

    def send_raw(self, raw: bytes, thread_id: str | None) -> tuple[str, str]:
        body: dict[str, Any] = {"raw": base64.urlsafe_b64encode(raw).decode()}
        if thread_id:
            body["threadId"] = thread_id
        res = _check(
            self.http.post(f"{GMAIL}/messages/send", json=body, headers=self._auth())
        ).json()
        return res["id"], res["threadId"]

    def put_event(self, calendar_id: str, event_id: str, body: dict[str, Any]) -> None:
        base = f"{CALENDAR}/{calendar_id}/events"
        res = self.http.put(f"{base}/{event_id}", json=body, headers=self._auth())
        if res.status_code == 404:
            _check(self.http.post(base, json={**body, "id": event_id}, headers=self._auth()))
        else:
            _check(res)

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        res = self.http.delete(f"{CALENDAR}/{calendar_id}/events/{event_id}", headers=self._auth())
        if res.status_code not in (404, 410):
            _check(res)
