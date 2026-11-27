"""Quote lifecycle: draft -> awaiting_approval -> sending -> sent (-> accepted | superseded).

Every quote and revision needs an explicit approval. The pipeline moves to QUOTE_SENT only
when the worker reports that the email was actually sent.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.email import templates
from app.modules.email.send import base_context
from app.modules.enquiries.models import Enquiry, Pipeline
from app.modules.enquiries.pipeline import transition
from app.modules.platform import outbox
from app.modules.platform.audit import Actor, write_audit
from app.modules.platform.models import OutboxEvent
from app.modules.pricing.engine import price
from app.modules.pricing.models import RateCardRow
from app.modules.pricing.rate_cards import RateCard
from app.modules.pricing.service import active_card
from app.modules.pricing.types import (
    BridalPackage,
    CustomLine,
    PriceInputs,
    PriceResult,
    Region,
    TravelZone,
)
from app.modules.quotes.models import Quote, QuoteLineItem, QuoteStatus

# Flags that also live on the enquiry and must be acknowledged before submitting.
ENQUIRY_FLAGS_TO_ACK = {"date_in_past", "date_under_14_days"}


class QuoteError(Exception):
    def __init__(self, code: str, message: str, details: list[str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or []


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}".replace(".00", "")


def inputs_from_enquiry(e: Enquiry, overrides: dict[str, Any]) -> dict[str, Any]:
    base: dict[str, Any] = {
        "attendant_hair": e.attendant_hair_count,
        "attendant_makeup": e.attendant_makeup_count,
        "trial": e.trial_requested,
        "bridal_package": e.bridal_package or BridalPackage.FULL.value,
        "travel_zone": e.travel_zone or TravelZone.UNKNOWN.value,
        "stylists_required": e.stylists_required,
        "travel_fee_cents": None,
        "custom_lines": [],
    }
    base.update({k: v for k, v in overrides.items() if v is not None or k == "travel_fee_cents"})
    return base


def _price(region: Region, inputs: dict[str, Any], card: RateCard) -> PriceResult:
    return price(
        PriceInputs(
            region=region,
            attendant_hair=int(inputs["attendant_hair"]),
            attendant_makeup=int(inputs["attendant_makeup"]),
            trial=bool(inputs["trial"]),
            bridal_package=BridalPackage(inputs["bridal_package"]),
            travel_zone=TravelZone(inputs["travel_zone"]),
            stylists_required=inputs.get("stylists_required"),
            travel_fee_cents=inputs.get("travel_fee_cents"),
            custom_lines=tuple(CustomLine(**c) for c in inputs.get("custom_lines", [])),
        ),
        card,
    )


def _apply(db: Session, q: Quote, result: PriceResult) -> None:
    q.price_snapshot = result.to_snapshot()
    q.subtotal_cents = result.subtotal_cents
    q.minimum_adjustment_cents = result.minimum_adjustment_cents
    q.total_cents = result.total_cents
    q.deposit_cents = result.deposit_cents
    q.balance_cents = result.balance_cents
    q.review_flags = [f.value for f in result.flags]
    q.stylists_required = q.inputs.get("stylists_required")
    for old in db.scalars(select(QuoteLineItem).where(QuoteLineItem.quote_id == q.id)):
        db.delete(old)
    db.flush()
    for i, li in enumerate(result.line_items):
        db.add(
            QuoteLineItem(
                quote_id=q.id,
                kind=li.kind.value,
                description=li.description,
                quantity=li.quantity,
                unit_cents=li.unit_cents,
                amount_cents=li.amount_cents,
                sort=i,
            )
        )


def lines(db: Session, q: Quote) -> list[QuoteLineItem]:
    return list(
        db.scalars(
            select(QuoteLineItem).where(QuoteLineItem.quote_id == q.id).order_by(QuoteLineItem.sort)
        )
    )


def current_sent(db: Session, enquiry_id: uuid.UUID) -> Quote | None:
    return db.scalar(
        select(Quote)
        .where(Quote.enquiry_id == enquiry_id, Quote.status == QuoteStatus.SENT)
        .order_by(Quote.version.desc())
        .limit(1)
    )


def open_quote(db: Session, enquiry_id: uuid.UUID) -> Quote | None:
    return db.scalar(
        select(Quote).where(
            Quote.enquiry_id == enquiry_id,
            Quote.status.in_(
                [
                    QuoteStatus.DRAFT,
                    QuoteStatus.AWAITING_APPROVAL,
                    QuoteStatus.SENDING,
                    QuoteStatus.SEND_FAILED,
                ]
            ),
        )
    )


def create_draft(db: Session, e: Enquiry, actor: Actor, overrides: dict[str, Any]) -> Quote:
    status = Pipeline(e.pipeline_status)
    allowed = {
        Pipeline.UNDER_REVIEW,
        Pipeline.NEEDS_INFORMATION,
        Pipeline.QUOTE_DRAFT,
        Pipeline.DISCUSSION_REVISION,
        Pipeline.QUOTE_SENT,
    }
    if status not in allowed:
        raise QuoteError("wrong_stage", f"Can't start a quote while the enquiry is {status}.")
    if e.region is None:
        raise QuoteError("region_unknown", "Set the region before quoting.")
    if open_quote(db, e.id) is not None:
        raise QuoteError("open_quote_exists", "Finish or withdraw the open quote first.")
    region = Region(e.region)
    row, card = active_card(db, region)
    version = (db.scalar(select(func.max(Quote.version)).where(Quote.enquiry_id == e.id)) or 0) + 1
    previous = current_sent(db, e.id)
    inputs = inputs_from_enquiry(e, overrides)
    inputs.pop("note_to_client", None)
    result = _price(region, inputs, card)
    q = Quote(
        enquiry_id=e.id,
        version=version,
        status=QuoteStatus.DRAFT,
        supersedes_quote_id=previous.id if previous else None,
        rate_card_id=row.id,
        rate_snapshot=card.to_dict(),
        inputs=inputs,
        acknowledged_flags=[],
        note_to_client=overrides.get("note_to_client"),
        price_snapshot=result.to_snapshot(),
        subtotal_cents=result.subtotal_cents,
        minimum_adjustment_cents=result.minimum_adjustment_cents,
        total_cents=result.total_cents,
        deposit_cents=result.deposit_cents,
        balance_cents=result.balance_cents,
        review_flags=[f.value for f in result.flags],
    )
    db.add(q)
    db.flush()
    _apply(db, q, result)
    if status in (Pipeline.UNDER_REVIEW, Pipeline.NEEDS_INFORMATION):
        transition(db, e, Pipeline.QUOTE_DRAFT, actor)
    elif status == Pipeline.QUOTE_SENT:
        # A revision started without a classified reply (e.g. a phone call).
        transition(db, e, Pipeline.DISCUSSION_REVISION, actor)
    write_audit(
        db,
        actor,
        "quote.create",
        entity_type="quote",
        entity_id=q.id,
        after={"version": version, "total_cents": q.total_cents},
    )
    return q


def update_draft(
    db: Session, q: Quote, e: Enquiry, actor: Actor, overrides: dict[str, Any]
) -> Quote:
    if q.status != QuoteStatus.DRAFT:
        raise QuoteError("not_draft", "Only drafts can be edited.")
    q.inputs = {**q.inputs, **overrides}
    if "note_to_client" in overrides:
        q.note_to_client = overrides["note_to_client"]
    q.inputs.pop("note_to_client", None)
    # Re-priced on the rate card the draft started with, never silently on a newer one.
    _apply(db, q, _price(Region(e.region or ""), q.inputs, RateCard.from_dict(q.rate_snapshot)))
    q.acknowledged_flags = [f for f in q.acknowledged_flags if f in q.review_flags]
    write_audit(
        db,
        actor,
        "quote.update",
        entity_type="quote",
        entity_id=q.id,
        after={"total_cents": q.total_cents, "inputs": q.inputs},
    )
    return q


def reprice_on_active_card(db: Session, q: Quote, e: Enquiry, actor: Actor) -> Quote:
    if q.status != QuoteStatus.DRAFT:
        raise QuoteError("not_draft", "Only drafts can be re-priced.")
    row, card = active_card(db, Region(e.region or ""))
    before = q.total_cents
    q.rate_card_id, q.rate_snapshot = row.id, card.to_dict()
    _apply(db, q, _price(Region(e.region or ""), q.inputs, card))
    write_audit(
        db,
        actor,
        "quote.reprice",
        entity_type="quote",
        entity_id=q.id,
        before={"total_cents": before},
        after={"total_cents": q.total_cents, "rate_card_version": card.version},
    )
    return q


def quote_context(db: Session, q: Quote, e: Enquiry) -> dict[str, Any]:
    return base_context(db, e) | {
        "quote": {
            "lines": [
                {
                    "description": li.description,
                    "quantity": li.quantity,
                    "amount": money(li.amount_cents),
                }
                for li in lines(db, q)
            ],
            "total": money(q.total_cents),
            "deposit": money(q.deposit_cents),
            "balance": money(q.balance_cents),
            "version": q.version,
            "note": q.note_to_client or "",
        },
    }


def render_email(db: Session, q: Quote, e: Enquiry) -> templates.Rendered:
    key = "quote_revision" if q.supersedes_quote_id else "quote"
    return templates.render(db, key, quote_context(db, q, e))


def submit(db: Session, q: Quote, e: Enquiry, actor: Actor, acknowledged: list[str]) -> Quote:
    if q.status != QuoteStatus.DRAFT:
        raise QuoteError("not_draft", "Only drafts can be submitted.")
    needed = set(q.review_flags) | (set(e.needs_review_flags) & ENQUIRY_FLAGS_TO_ACK)
    if "travel_unconfirmed" in q.review_flags:
        raise QuoteError(
            "travel_unconfirmed",
            "Confirm travel (stylist count or travel fee) before submitting.",
            ["travel_unconfirmed"],
        )
    missing = sorted(needed - set(acknowledged))
    if missing:
        raise QuoteError("flags_not_acknowledged", "Acknowledge the review flags first.", missing)
    q.acknowledged_flags = sorted(needed)
    q.status = QuoteStatus.AWAITING_APPROVAL
    q.submitted_at = utcnow()
    target = Pipeline.AWAITING_APPROVAL
    if Pipeline(e.pipeline_status) != target:
        transition(db, e, target, actor)
    write_audit(
        db,
        actor,
        "quote.submit",
        entity_type="quote",
        entity_id=q.id,
        after={"acknowledged_flags": q.acknowledged_flags},
    )
    return q


def approve(db: Session, q: Quote, e: Enquiry, actor: Actor) -> Quote:
    """Jessica's approval. Freezes the exact email and queues it in the same transaction."""
    if q.status != QuoteStatus.AWAITING_APPROVAL:
        raise QuoteError("not_awaiting_approval", "This quote isn't waiting for approval.")
    rendered = render_email(db, q, e)
    q.email_subject, q.email_body_html, q.email_body_text = (
        rendered.subject,
        rendered.html,
        rendered.text,
    )
    q.status = QuoteStatus.SENDING
    q.approved_at = utcnow()
    q.send_error = None
    q.outbox_event_id = outbox.enqueue(
        db,
        "quote.send",
        f"quote_send:{q.id}:{_send_attempts(db, q) + 1}",
        {"quote_id": str(q.id)},
        aggregate_type="quote",
        aggregate_id=q.id,
    )
    write_audit(
        db,
        actor,
        "quote.approve",
        entity_type="quote",
        entity_id=q.id,
        after={"total_cents": q.total_cents, "subject": q.email_subject},
    )
    return q


def reject(db: Session, q: Quote, e: Enquiry, actor: Actor, note: str | None) -> Quote:
    if q.status != QuoteStatus.AWAITING_APPROVAL:
        raise QuoteError("not_awaiting_approval", "This quote isn't waiting for approval.")
    q.status = QuoteStatus.DRAFT
    q.rejection_note = note
    q.acknowledged_flags = []
    transition(db, e, Pipeline.QUOTE_DRAFT, actor, reason=note)
    write_audit(
        db, actor, "quote.reject", entity_type="quote", entity_id=q.id, after={"note": note}
    )
    return q


def withdraw(db: Session, q: Quote, e: Enquiry, actor: Actor, reason: str | None) -> Quote:
    if q.status not in (QuoteStatus.DRAFT, QuoteStatus.AWAITING_APPROVAL, QuoteStatus.SEND_FAILED):
        raise QuoteError("cannot_withdraw", "Only unsent quotes can be withdrawn.")
    q.status = QuoteStatus.WITHDRAWN
    q.withdrawn_reason = reason
    if Pipeline(e.pipeline_status) == Pipeline.AWAITING_APPROVAL:
        transition(db, e, Pipeline.QUOTE_DRAFT, actor, reason=reason)
    write_audit(
        db, actor, "quote.withdraw", entity_type="quote", entity_id=q.id, after={"reason": reason}
    )
    return q


def mark_sent(db: Session, q: Quote, email_message_id: uuid.UUID, actor: Actor) -> None:
    """Called by the worker in the same transaction that stored the sent email."""
    e = db.get(Enquiry, q.enquiry_id)
    assert e is not None
    q.status = QuoteStatus.SENT
    q.sent_at = utcnow()
    q.email_message_id = email_message_id
    for older in db.scalars(
        select(Quote).where(
            Quote.enquiry_id == q.enquiry_id, Quote.id != q.id, Quote.status == QuoteStatus.SENT
        )
    ):
        older.status = QuoteStatus.SUPERSEDED
    if Pipeline(e.pipeline_status) == Pipeline.AWAITING_APPROVAL:
        transition(db, e, Pipeline.QUOTE_SENT, actor)
    write_audit(db, actor, "quote.sent", entity_type="quote", entity_id=q.id)


def mark_send_failed(db: Session, q: Quote, error: str) -> None:
    q.status = QuoteStatus.SEND_FAILED
    q.send_error = error


def retry_send(db: Session, q: Quote, e: Enquiry, actor: Actor) -> Quote:
    if q.status != QuoteStatus.SEND_FAILED:
        raise QuoteError("not_failed", "Only a failed send can be retried.")
    event = db.get(OutboxEvent, q.outbox_event_id) if q.outbox_event_id else None
    if event is None:
        raise QuoteError("no_send_event", "There is no send to retry.")
    # Re-send the exact email Jessica approved; nothing is re-rendered.
    outbox.retry(event)
    q.status = QuoteStatus.SENDING
    q.send_error = None
    write_audit(db, actor, "quote.retry_send", entity_type="quote", entity_id=q.id)
    return q


def _send_attempts(db: Session, q: Quote) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.aggregate_id == q.id, OutboxEvent.kind == "quote.send")
        )
        or 0
    )


def to_dict(db: Session, q: Quote) -> dict[str, Any]:
    card = db.get(RateCardRow, q.rate_card_id)
    data = {c.name: getattr(q, c.name) for c in Quote.__table__.columns}
    data["rate_card_version"] = card.version if card else None
    data["line_items"] = [asdict_line(li) for li in lines(db, q)]
    return data


def asdict_line(li: QuoteLineItem) -> dict[str, Any]:
    return {
        "kind": li.kind,
        "description": li.description,
        "quantity": li.quantity,
        "unit_cents": li.unit_cents,
        "amount_cents": li.amount_cents,
    }
