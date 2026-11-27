"""Outgoing mail behind one interface. Local: SMTP to Mailpit. Production: Gmail (Phase 3.1)."""

from __future__ import annotations

import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from email.utils import formatdate
from typing import Protocol


@dataclass(frozen=True)
class OutgoingMail:
    from_addr: str
    to: list[str]
    subject: str
    html: str
    text: str
    message_id: str  # deterministic: <outbox-{event_id}@jstyle-os>
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    provider_thread_id: str | None = None


@dataclass(frozen=True)
class SentMail:
    provider_message_id: str | None
    provider_thread_id: str | None


class Mailer(Protocol):
    def send(self, mail: OutgoingMail) -> SentMail: ...


def to_mime(mail: OutgoingMail) -> MimeMessage:
    msg = MimeMessage()
    msg["From"] = mail.from_addr
    msg["To"] = ", ".join(mail.to)
    msg["Subject"] = mail.subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = mail.message_id
    if mail.in_reply_to:
        msg["In-Reply-To"] = mail.in_reply_to
    if mail.references:
        msg["References"] = " ".join(mail.references)
    msg.set_content(mail.text)
    msg.add_alternative(mail.html, subtype="html")
    return msg


class SmtpMailer:
    def __init__(self, host: str, port: int) -> None:
        self.host, self.port = host, port

    def send(self, mail: OutgoingMail) -> SentMail:
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            smtp.send_message(to_mime(mail))
        return SentMail(provider_message_id=None, provider_thread_id=None)


class RecordingMailer:
    """Test double: keeps every message in memory."""

    def __init__(self) -> None:
        self.sent: list[OutgoingMail] = []

    def send(self, mail: OutgoingMail) -> SentMail:
        self.sent.append(mail)
        return SentMail(provider_message_id=None, provider_thread_id=None)
