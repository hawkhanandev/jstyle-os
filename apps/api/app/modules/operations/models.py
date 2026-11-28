from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk


class TrialStatus(StrEnum):
    SCHEDULED = "scheduled"
    DONE = "done"
    CANCELLED = "cancelled"


class Trial(UUIDPk, Timestamps, Base):
    __tablename__ = "trials"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), index=True
    )
    enquiry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("enquiries.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    location: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(12), default=TrialStatus.SCHEDULED)
    notes: Mapped[str | None] = mapped_column(Text)


class WeddingPlan(UUIDPk, Timestamps, Base):
    """Day-of details for a booking: getting-ready place and the timeline."""

    __tablename__ = "wedding_plans"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), unique=True
    )
    getting_ready_address: Mapped[str | None] = mapped_column(Text)
    # [{"time": "07:30", "person": "Bride", "service": "Hair", "stylist": "Jessica"}]
    timeline: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    final_timeline_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
