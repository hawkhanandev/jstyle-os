"""Spam checks for the public forms (design doc: Website forms and spam protection).

Pure scoring lives in score_content(); I/O checks (Turnstile, MX lookup, rate limits) are
behind small functions so tests can replace them.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

DISPOSABLE_DOMAINS = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "10minutemail.com",
        "tempmail.com",
        "temp-mail.org",
        "yopmail.com",
        "trashmail.com",
        "sharklasers.com",
        "getnada.com",
        "dispostable.com",
        "maildrop.cc",
        "throwawaymail.com",
        "fakeinbox.com",
        "mailnesia.com",
        "mintemail.com",
    }
)
SPAM_WORDS = (
    "seo",
    "backlink",
    "crypto",
    "bitcoin",
    "casino",
    "viagra",
    "loan",
    "forex",
    "web design services",
    "rank your website",
    "marketing services",
    "guest post",
)
URL = re.compile(r"https?://|www\.", re.I)
PHONE_DIGITS = re.compile(r"\d")

HOLD_THRESHOLD = 50
MIN_FILL_SECONDS = 4
MAX_FILL_SECONDS = 24 * 3600


@dataclass
class Verdict:
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    hard_reject: str | None = None  # "turnstile" or "rate_limited"
    hold: bool = False

    def add(self, points: int, reason: str) -> None:
        self.score += points
        self.reasons.append(reason)


# --- Form timing token: signed issue time, so bots can't fake how long they took -------------


def issue_form_token(secret: str, now: float | None = None) -> str:
    ts = str(int(now if now is not None else time.time()))
    sig = hmac.new(secret.encode(), f"form:{ts}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{ts}.{sig}"


def fill_seconds(secret: str, token: str | None, now: float | None = None) -> float | None:
    """Seconds since the token was issued, or None if the token is missing or forged."""
    if not token or "." not in token:
        return None
    ts, sig = token.split(".", 1)
    expected = hmac.new(secret.encode(), f"form:{ts}".encode(), hashlib.sha256).hexdigest()[:32]
    if not ts.isdigit() or not hmac.compare_digest(sig, expected):
        return None
    return (now if now is not None else time.time()) - int(ts)


def hash_ip(secret: str, ip: str | None) -> str | None:
    if not ip:
        return None
    return hmac.new(secret.encode(), f"ip:{ip}".encode(), hashlib.sha256).hexdigest()


# --- Content scoring (pure) -------------------------------------------------------------------


def score_content(
    *,
    email: str,
    phone: str | None,
    wedding_date: date | None,
    region_known: bool,
    free_text: list[str | None],
    today: date,
    has_mail_server: bool | None,
) -> Verdict:
    v = Verdict()
    domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
    if domain in DISPOSABLE_DOMAINS:
        v.add(60, "disposable_email")
    if has_mail_server is False:
        v.add(60, "email_domain_not_found")
    if phone and not 7 <= len(PHONE_DIGITS.findall(phone)) <= 15:
        v.add(20, "phone_format")
    if wedding_date is None:
        v.add(10, "no_wedding_date")
    elif wedding_date < today:
        v.add(40, "date_in_past")
    elif wedding_date > today + timedelta(days=3 * 365):
        v.add(30, "date_over_3_years")
    if not region_known:
        v.add(15, "region_unknown")
    text = " ".join(t for t in free_text if t).lower()
    links = len(URL.findall(text))
    if links > 1:
        v.add(30 + 10 * (links - 2), "too_many_links")
    hits = [w for w in SPAM_WORDS if w in text]
    if hits:
        v.add(25 * len(hits), "spam_words")
    return v
