from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk


class RateCardRow(UUIDPk, Timestamps, Base):
    """One immutable version of a region's rates. Edits create a new version."""

    __tablename__ = "rate_cards"
    __table_args__ = (
        UniqueConstraint("region", "version"),
        # At most one active card per region.
        Index(
            "uq_rate_cards_active_region", "region", unique=True, postgresql_where=text("is_active")
        ),
    )

    region: Mapped[str] = mapped_column(String(2))
    version: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rates: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(500))
