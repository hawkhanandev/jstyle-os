"""Keyword rules that suggest what a client's reply means.

Only a suggestion: staff confirm or correct it before anything changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.replies.models import Intent

DECLINE = [
    r"decided to go (with|in) (another|a different)",
    r"went with (another|someone else|a different)",
    r"(found|booked|chose|hired) (someone|somebody) else",
    r"(found|booked|chose|hired) (another|a different) (artist|stylist|team|company|vendor)",
    r"no longer (need|require|looking)",
    r"(won't|will not|wont) be (needing|moving forward|booking)",
    r"not (be )?moving forward",
    r"(going to|will|we'll|i'll) pass",
    r"\bdeclin(e|ing)\b",
    r"out of (our|my) budget",
    r"wedding (is|has been) (cancelled|canceled|called off)",
]
CHANGE = [
    r"\b(add|adding|remove|removing|drop|swap)\b",
    r"\bone more\b",
    r"\b(another|extra|additional) (bridesmaid|attendant|person|people|mother|flower girl)",
    r"\b(fewer|less) (people|bridesmaids|attendants)",
    r"\binstead\b",
    r"\bchange (the|our|my)\b",
    r"\b(update|revise|adjust) (the )?(quote|price|estimate)",
    r"\b(different|new) (date|venue|time|location)",
    r"\bcan (we|you) (also|make|do|change)\b",
    r"\bcould (we|you) (also|make|do|change)\b",
    r"\bhair only\b|\bmakeup only\b",
    r"\b(no|skip the|without the) trial\b",
]
ACCEPT = [
    r"\b(we|i) accept\b",
    r"\baccept (the|your) (quote|offer|proposal|estimate)",
    r"\b(we'd|we would|i'd|i would) (love|like) to (book|go ahead|move forward|secure|reserve)",
    r"\b(ready|want|wanted) to (book|go ahead|move forward|secure)",
    r"\blet'?s (book|do it|go ahead|move forward)",
    r"\bgo ahead\b",
    r"\b(count us in|we're in|we are in|book us|book me)\b",
    r"\bsounds (perfect|great|good)[!.,]",
    r"\b(send|email) (me |us )?(over )?(the )?contract",
    r"\b(pay|send|make) (the )?deposit",
    r"\bhow (do|can) (i|we) pay\b",
    r"\b(secure|reserve|lock in) (the|our|my) date",
]

QUOTED = re.compile(r"^\s*>.*$", re.M)
WROTE = re.compile(r"\n\s*On .{5,200}wrote:\s*\n.*", re.S)
SIGNATURE = re.compile(r"\n--\s*\n.*", re.S)


def latest_text(body: str) -> str:
    """Drop quoted history and signatures so old quote text doesn't skew the match."""
    text = WROTE.sub("", body)
    text = SIGNATURE.sub("", text)
    text = QUOTED.sub("", text)
    return text.strip()


def _first(patterns: list[str], text: str) -> str | None:
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(0)
    return None


@dataclass(frozen=True)
class Classification:
    intent: Intent
    confidence: str
    matched: str | None


def classify(body: str) -> Classification:
    text = latest_text(body)
    decline = _first(DECLINE, text)
    change = _first(CHANGE, text)
    accept = _first(ACCEPT, text)
    if decline:
        return Classification(Intent.DECLINE, "medium" if accept else "high", decline)
    if change:
        # "We'd love to book, but can we add one more?" is a change request first.
        return Classification(Intent.CHANGE_REQUEST, "medium" if accept else "high", change)
    if accept:
        return Classification(Intent.ACCEPT, "high", accept)
    if "?" in text:
        return Classification(Intent.QUESTION, "medium", None)
    return Classification(Intent.OTHER, "low", None)
