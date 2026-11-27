"""External checks behind small interfaces: Cloudflare Turnstile and the email MX lookup."""

from __future__ import annotations

import socket
from typing import Protocol

import httpx

from app.core.config import get_settings

TURNSTILE_VERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class Turnstile(Protocol):
    def verify(self, token: str | None, ip: str | None) -> bool: ...


class CloudflareTurnstile:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def verify(self, token: str | None, ip: str | None) -> bool:
        if not token:
            return False
        try:
            res = httpx.post(
                TURNSTILE_VERIFY,
                timeout=5,
                data={"secret": self.secret, "response": token, "remoteip": ip or ""},
            )
            return bool(res.json().get("success"))
        except httpx.HTTPError:
            # Cloudflare unreachable: don't lose a real bride; other layers still apply.
            return True


class NoTurnstile:
    """Used when no Turnstile secret is configured (local development)."""

    def verify(self, token: str | None, ip: str | None) -> bool:
        return True


def get_turnstile() -> Turnstile:
    secret = get_settings().turnstile_secret_key
    return CloudflareTurnstile(secret) if secret else NoTurnstile()


class MailCheck(Protocol):
    def has_mail_server(self, domain: str) -> bool | None: ...


class DnsMailCheck:
    """Best effort: True/False when DNS answers, None when it can't tell."""

    def has_mail_server(self, domain: str) -> bool | None:
        try:
            socket.getaddrinfo(domain, 25, proto=socket.IPPROTO_TCP)
            return True
        except socket.gaierror as exc:
            if exc.errno in (socket.EAI_NONAME, getattr(socket, "EAI_NODATA", -5)):
                return False
            return None
        except OSError:
            return None


class SkipMailCheck:
    def has_mail_server(self, domain: str) -> bool | None:
        return None


def get_mail_check() -> MailCheck:
    return DnsMailCheck() if get_settings().env != "local" else SkipMailCheck()
