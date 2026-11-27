from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk


class EnquiryType(StrEnum):
    BRIDE = "bride"
    PLANNER = "planner"


class Pipeline(StrEnum):
    NEW_INQUIRY = "NEW_INQUIRY"
    UNDER_REVIEW = "UNDER_REVIEW"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    QUOTE_DRAFT = "QUOTE_DRAFT"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    QUOTE_SENT = "QUOTE_SENT"
    DISCUSSION_REVISION = "DISCUSSION_REVISION"
    QUOTE_ACCEPTED = "QUOTE_ACCEPTED"
    CONTRACT_DEPOSIT_PENDING = "CONTRACT_DEPOSIT_PENDING"
    BOOKED = "BOOKED"
    LOST_DECLINED = "LOST_DECLINED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


CLOSED = {Pipeline.LOST_DECLINED, Pipeline.CANCELLED, Pipeline.EXPIRED}


class PlannerCompany(UUIDPk, Timestamps, Base):
    __tablename__ = "planner_companies"

    name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)


class Enquiry(UUIDPk, Timestamps, Base):
    __tablename__ = "enquiries"

    type: Mapped[str] = mapped_column(String(10))
    pipeline_status: Mapped[str] = mapped_column(
        String(30), default=Pipeline.NEW_INQUIRY, index=True
    )
    closed_reason: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(String(2), index=True)
    timezone: Mapped[str | None] = mapped_column(String(40))

    client_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    preferred_contact: Mapped[str | None] = mapped_column(String(20))

    wedding_date: Mapped[date | None] = mapped_column(Date, index=True)
    venue_name: Mapped[str | None] = mapped_column(String(300))
    venue_address: Mapped[str | None] = mapped_column(Text)
    wedding_type: Mapped[str | None] = mapped_column(String(100))

    bridal_package: Mapped[str | None] = mapped_column(String(20))
    attendant_hair_count: Mapped[int] = mapped_column(Integer, default=0)
    attendant_makeup_count: Mapped[int] = mapped_column(Integer, default=0)
    trial_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    travel_zone: Mapped[str | None] = mapped_column(String(20))
    stylists_required: Mapped[int | None] = mapped_column(Integer)
    travel_notes: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    services: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    planner_company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("planner_companies.id")
    )
    raw_submission: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_form: Mapped[str | None] = mapped_column(String(20))
    needs_review_flags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    follow_ups_paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineHistory(UUIDPk, Base):
    __tablename__ = "enquiry_status_history"

    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enquiries.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Task(UUIDPk, Timestamps, Base):
    __tablename__ = "tasks"

    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
