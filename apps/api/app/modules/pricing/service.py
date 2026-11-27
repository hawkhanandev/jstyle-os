from __future__ import annotations

from dataclasses import replace

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.platform.audit import Actor, write_audit
from app.modules.pricing.models import RateCardRow
from app.modules.pricing.rate_cards import DEFAULT_RATE_CARDS, RateCard
from app.modules.pricing.types import Region


class NoActiveRateCard(Exception):
    pass


def to_card(row: RateCardRow) -> RateCard:
    return RateCard.from_dict({**row.rates, "region": row.region, "version": row.version})


def active_card(db: Session, region: Region) -> tuple[RateCardRow, RateCard]:
    row = db.scalar(
        select(RateCardRow).where(RateCardRow.region == region.value, RateCardRow.is_active)
    )
    if row is None:
        raise NoActiveRateCard(region.value)
    return row, to_card(row)


def history(db: Session, region: Region) -> list[RateCardRow]:
    return list(
        db.scalars(
            select(RateCardRow)
            .where(RateCardRow.region == region.value)
            .order_by(RateCardRow.version.desc())
        )
    )


def create_version(
    db: Session, actor: Actor, card: RateCard, note: str | None = None
) -> RateCardRow:
    """Save `card` as the next version for its region and make it active.

    Old versions stay in the table, read-only. Existing quotes keep their own snapshot and are
    never touched by this.
    """
    region = card.region.value
    # Serialise concurrent edits for the same region.
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"rate_cards:{region}"))))
    current = db.scalar(select(func.max(RateCardRow.version)).where(RateCardRow.region == region))
    version = (current or 0) + 1
    previous = db.scalar(
        select(RateCardRow).where(RateCardRow.region == region, RateCardRow.is_active)
    )
    db.execute(
        update(RateCardRow)
        .where(RateCardRow.region == region, RateCardRow.is_active)
        .values(is_active=False)
    )
    db.flush()
    card = replace(card, version=version)
    rates = {k: v for k, v in card.to_dict().items() if k not in ("region", "version")}
    row = RateCardRow(
        region=region,
        version=version,
        effective_from=utcnow(),
        rates=rates,
        is_active=True,
        note=note,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        actor,
        "rate_card.create",
        entity_type="rate_card",
        entity_id=row.id,
        before=previous.rates | {"version": previous.version} if previous else None,
        after=rates | {"version": version},
    )
    return row


def ensure_defaults(db: Session, actor: Actor) -> int:
    """Seed version 1 for any region without a card. Returns how many were created."""
    created = 0
    for region, card in DEFAULT_RATE_CARDS.items():
        exists = db.scalar(select(RateCardRow.id).where(RateCardRow.region == region.value))
        if exists is None:
            create_version(db, actor, card, note="Initial rates from the PRD")
            created += 1
    return created
