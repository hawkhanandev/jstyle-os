"""Google OAuth 2.0 with PKCE. Behind a small protocol so tests use a fake."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SIGN_IN_SCOPES = ["openid", "email", "profile"]


@dataclass(frozen=True)
class GoogleIdentity:
    email: str
    email_verified: bool
    name: str | None = None


class GoogleOAuth(Protocol):
    def authorization_url(self, *, state: str, code_challenge: str, redirect_uri: str) -> str: ...

    def fetch_identity(
        self, *, code: str, code_verifier: str, redirect_uri: str
    ) -> GoogleIdentity: ...


def new_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


class GoogleOAuthClient:
    def __init__(self, client_id: str, client_secret: str, timeout: float = 10.0) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

    def authorization_url(self, *, state: str, code_challenge: str, redirect_uri: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SIGN_IN_SCOPES),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def fetch_identity(self, *, code: str, code_verifier: str, redirect_uri: str) -> GoogleIdentity:
        with httpx.Client(timeout=self.timeout) as http:
            token = http.post(
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
            token.raise_for_status()
            access_token = token.json()["access_token"]
            info = http.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
            info.raise_for_status()
            data = info.json()
        return GoogleIdentity(
            email=str(data["email"]).lower(),
            email_verified=bool(data.get("email_verified")),
            name=data.get("name"),
        )
