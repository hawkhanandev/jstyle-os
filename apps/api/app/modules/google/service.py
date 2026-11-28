"""The connected Google account: Gmail sync into the Inbox, sending as the account, and calendar."""

from __future__ import annotations

import email
import email.policy
import logging
import re
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, getaddresses, parseaddr, parsedate_to_datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import utcnow
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.email.mailer import Mailer, OutgoingMail, SentMail, to_mime
from app.modules.enquiries.models import Enquiry
from app.modules.google import crypto
from app.modules.google.client import (
    AccessRevoked,
    GoogleApi,
    GoogleSession,
    Grant,
    HistoryExpired,
    RawMessage,
)
from app.modules.google.models import CalendarEvent, GoogleConnection
from app.modules.inbox.service import InboundMail, ingest_inbound
from app.modules.operations.models import Trial, TrialStatus
from app.modules.platform.audit import Actor, write_audit

log = logging.getLogger("jstyle.google")

BACKFILL_DAYS = 7
SYNC_EVERY = timedelta(seconds=60)


class NotConnected(Exception):
    pass


# --- connection ------------------------------------------------------------------------------


def current(db: Session) -> GoogleConnection | None:
    return db.scalar(select(GoogleConnection).order_by(GoogleConnection.created_at.desc()).limit(1))


def save_grant(db: Session, settings: Settings, grant: Grant, actor: Actor) -> GoogleConnection:
    """Store a new grant, replacing any earlier connection."""
    old = current(db)
    if old is not None:
        db.delete(old)
        db.flush()
    conn = GoogleConnection(
        email=grant.email,
        refresh_token_enc=crypto.encrypt(settings.secret_key, grant.refresh_token),
        scopes=" ".join(grant.scopes),
        connected_by=actor.account_email or "system",
        send_enabled=False,
        calendar_enabled=False,
    )
    db.add(conn)
    db.flush()
    write_audit(
        db,
        actor,
        "google.connect",
        entity_type="google_connection",
        entity_id=conn.id,
        after={"email": grant.email, "scopes": grant.scopes},
    )
    return conn


def session_for(api: GoogleApi, settings: Settings, conn: GoogleConnection) -> GoogleSession:
    token = crypto.decrypt(settings.secret_key, conn.refresh_token_enc)
    if token is None:
        raise AccessRevoked("The stored Google token can't be read; connect the account again.")
    return api.session(token)


def disconnect(db: Session, api: GoogleApi, settings: Settings, actor: Actor) -> None:
    conn = current(db)
    if conn is None:
        return
    token = crypto.decrypt(settings.secret_key, conn.refresh_token_enc)
    if token:
        try:
            api.revoke(token)
        except Exception:  # noqa: BLE001 - disconnecting locally matters more than the revoke call
            log.warning("google revoke failed", exc_info=True)
    write_audit(
        db,
        actor,
        "google.disconnect",
        entity_type="google_connection",
        entity_id=conn.id,
        before={"email": conn.email},
    )
    db.delete(conn)
    db.flush()


def set_options(
    db: Session, conn: GoogleConnection, actor: Actor, *, send: bool | None, calendar: bool | None
) -> None:
    before = {"send_enabled": conn.send_enabled, "calendar_enabled": conn.calendar_enabled}
    if send is not None:
        conn.send_enabled = send
    if calendar is not None:
        conn.calendar_enabled = calendar
    write_audit(
        db,
        actor,
        "google.options",
        entity_type="google_connection",
        entity_id=conn.id,
        before=before,
        after={"send_enabled": conn.send_enabled, "calendar_enabled": conn.calendar_enabled},
    )


def to_dict(conn: GoogleConnection | None, configured: bool) -> dict[str, Any]:
    if conn is None:
        return {"configured": configured, "connected": False}
    return {
        "configured": configured,
        "connected": True,
        "email": conn.email,
        "scopes": conn.scopes.split(),
        "send_enabled": conn.send_enabled,
        "calendar_enabled": conn.calendar_enabled,
        "connected_at": conn.created_at,
        "connected_by": conn.connected_by,
        "last_sync_at": conn.last_sync_at,
        "last_error": conn.last_error,
    }


# --- reading mail ----------------------------------------------------------------------------


def _addresses(values: list[str]) -> list[str]:
    return [a for _, a in getaddresses(values) if a]


def parse_raw(m: RawMessage) -> InboundMail:
    msg = email.message_from_bytes(m.raw, policy=email.policy.default)
    assert isinstance(msg, MimeMessage)
    text_part = msg.get_body(preferencelist=("plain",))
    html_part = msg.get_body(preferencelist=("html",))
    body_text = text_part.get_content() if text_part is not None else ""
    body_html = html_part.get_content() if html_part is not None else None
    sent_at: datetime | None = None
    if msg["Date"]:
        try:
            sent_at = parsedate_to_datetime(str(msg["Date"]))
            if sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            sent_at = None
    refs = str(msg.get("References", "")).split()
    return InboundMail(
        rfc_message_id=str(msg.get("Message-ID") or f"<gmail-{m.id}@mail.gmail.com>").strip(),
        from_addr=str(msg.get("From", "")),
        to_addrs=_addresses([str(v) for v in msg.get_all("To", [])]),
        subject=str(msg.get("Subject", "(no subject)")),
        body_text=body_text or _strip_html(body_html or ""),
        body_html=body_html,
        in_reply_to=str(msg["In-Reply-To"]).strip() if msg["In-Reply-To"] else None,
        references=refs,
        sent_at=sent_at,
        provider_message_id=m.id,
        provider_thread_id=m.thread_id,
    )


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>|</p>", "\n", text)
    return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "", text)).strip()


def _ingest_ids(db: Session, gs: GoogleSession, conn: GoogleConnection, ids: list[str]) -> int:
    attached = 0
    for mid in ids:
        raw = gs.get_raw(mid)
        if "INBOX" not in raw.label_ids or "SENT" in raw.label_ids:
            continue
        mail = parse_raw(raw)
        if parseaddr(mail.from_addr)[1].lower() == conn.email:
            continue  # our own message, e.g. a copy sent to ourselves
        with db.begin_nested():
            if ingest_inbound(db, mail).status == "attached":
                attached += 1
    return attached


def sync_inbox(db: Session, api: GoogleApi, settings: Settings) -> int:
    """Pull new inbox messages. Only mail from known clients is kept; the rest is ignored."""
    conn = current(db)
    if conn is None:
        raise NotConnected()
    try:
        gs = session_for(api, settings, conn)
        if conn.gmail_history_id is None:
            _, history_id = gs.profile()
            attached = _ingest_ids(db, gs, conn, gs.recent_inbox_ids(BACKFILL_DAYS))
        else:
            try:
                page = gs.history(conn.gmail_history_id)
                history_id = page.history_id
                attached = _ingest_ids(db, gs, conn, page.message_ids)
            except HistoryExpired:
                _, history_id = gs.profile()
                attached = _ingest_ids(db, gs, conn, gs.recent_inbox_ids(BACKFILL_DAYS))
    except AccessRevoked as exc:
        conn.last_error = str(exc)
        raise
    conn.gmail_history_id = history_id
    conn.last_sync_at = utcnow()
    conn.last_error = None
    return attached


_last_sync: list[datetime] = []


def maybe_sync(factory: sessionmaker[Session], api: GoogleApi, settings: Settings) -> None:
    """Called from the worker tick; syncs at most once a minute."""
    now = utcnow()
    if _last_sync and now - _last_sync[-1] < SYNC_EVERY:
        return
    _last_sync[:] = [now]
    with factory() as db:
        if current(db) is None:
            return
        try:
            n = sync_inbox(db, api, settings)
            if n:
                log.info("gmail sync attached %s message(s)", n)
        except Exception as exc:  # noqa: BLE001 - recorded on the connection, retried next minute
            db.rollback()
            conn = current(db)
            if conn is not None:
                conn.last_error = str(exc)[:500]
            log.warning("gmail sync failed: %s", exc)
        db.commit()


# --- sending ---------------------------------------------------------------------------------


class GmailMailer:
    def __init__(self, gs: GoogleSession, account_email: str) -> None:
        self.gs, self.account_email = gs, account_email

    def send(self, mail: OutgoingMail) -> SentMail:
        name = parseaddr(mail.from_addr)[0]
        mail = replace(mail, from_addr=formataddr((name, self.account_email)))
        mid, tid = self.gs.send_raw(to_mime(mail).as_bytes(), mail.provider_thread_id)
        return SentMail(provider_message_id=mid, provider_thread_id=tid)


class RoutingMailer:
    """Sends through Gmail when an account is connected with sending switched on, else fallback."""

    def __init__(
        self,
        factory: sessionmaker[Session],
        api: GoogleApi,
        settings: Settings,
        fallback: Mailer | None,
    ) -> None:
        self.factory, self.api, self.settings, self.fallback = factory, api, settings, fallback

    def send(self, mail: OutgoingMail) -> SentMail:
        with self.factory() as db:
            conn = current(db)
            gmail = (
                GmailMailer(session_for(self.api, self.settings, conn), conn.email)
                if conn is not None and conn.send_enabled
                else None
            )
        if gmail is not None:
            return gmail.send(mail)
        if self.fallback is None:
            raise RuntimeError("No way to send: connect Gmail and switch sending on.")
        return self.fallback.send(mail)


# --- calendar --------------------------------------------------------------------------------


def _event_id(kind: str, ref: uuid.UUID) -> str:
    # Google event ids allow a-v and 0-9; uuid hex fits.
    return f"js{kind[0]}{ref.hex}"


def _wedding_body(e: Enquiry, b: Booking) -> dict[str, Any]:
    assert e.wedding_date is not None
    place = ", ".join(p for p in [e.venue_name, e.venue_address] if p)
    lines = [
        f"Client: {e.client_name} ({e.email})",
        f"Stylists: {b.stylists_required or 'not set'}",
        f"CRM: enquiry {e.id}",
    ]
    return {
        "summary": f"Wedding: {e.client_name}",
        "location": place or None,
        "description": "\n".join(lines),
        "start": {"date": e.wedding_date.isoformat()},
        "end": {"date": (e.wedding_date + timedelta(days=1)).isoformat()},
        "status": "confirmed",
        "transparency": "opaque",
    }


def _trial_body(e: Enquiry, t: Trial) -> dict[str, Any]:
    tz = e.timezone or "Pacific/Honolulu"
    return {
        "summary": f"Trial: {e.client_name}",
        "location": t.location or None,
        "description": f"Client: {e.client_name} ({e.email})\nCRM: enquiry {e.id}",
        "start": {"dateTime": t.starts_at.isoformat(), "timeZone": tz},
        "end": {"dateTime": (t.starts_at + timedelta(hours=2)).isoformat(), "timeZone": tz},
        "status": "confirmed",
    }


def _record(db: Session, e: Enquiry, kind: str, ref: uuid.UUID | None, gid: str) -> CalendarEvent:
    row = db.scalar(select(CalendarEvent).where(CalendarEvent.google_event_id == gid))
    if row is None:
        row = CalendarEvent(enquiry_id=e.id, kind=kind, ref_id=ref, google_event_id=gid)
        db.add(row)
    return row


def sync_calendar(db: Session, api: GoogleApi, settings: Settings, enquiry_id: uuid.UUID) -> int:
    """Make the calendar match the CRM for one enquiry. Returns the number of calls made."""
    conn = current(db)
    if conn is None or not conn.calendar_enabled:
        return 0
    e = db.get(Enquiry, enquiry_id)
    if e is None:
        return 0
    gs = session_for(api, settings, conn)
    b = db.scalar(select(Booking).where(Booking.enquiry_id == e.id))
    calls = 0
    wanted: dict[str, dict[str, Any]] = {}
    if b is not None and b.status == BookingStatus.BOOKED and e.wedding_date is not None:
        wanted[_event_id("wedding", b.id)] = _wedding_body(e, b)
        for t in db.scalars(select(Trial).where(Trial.booking_id == b.id)):
            if t.status != TrialStatus.CANCELLED:
                wanted[_event_id("trial", t.id)] = _trial_body(e, t)
                _record(db, e, "trial", t.id, _event_id("trial", t.id))
        _record(db, e, "wedding", b.id, _event_id("wedding", b.id))
    db.flush()
    for row in db.scalars(select(CalendarEvent).where(CalendarEvent.enquiry_id == e.id)):
        if row.google_event_id in wanted:
            gs.put_event(conn.calendar_id, row.google_event_id, wanted[row.google_event_id])
            row.deleted = False
            calls += 1
        elif not row.deleted:
            gs.delete_event(conn.calendar_id, row.google_event_id)
            row.deleted = True
            calls += 1
    return calls


def resync_all_calendar(db: Session) -> int:
    """Queue a calendar update for every booked wedding, e.g. when calendar sync is switched on."""
    from app.modules.google.events import calendar_changed

    n = 0
    for enquiry_id in db.scalars(
        select(Booking.enquiry_id).where(Booking.status == BookingStatus.BOOKED)
    ):
        calendar_changed(db, enquiry_id)
        n += 1
    return n
