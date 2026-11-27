from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk


class SubmissionStatus(StrEnum):
    ACCEPTED = "accepted"  # created an enquiry
    MERGED = "merged"  # duplicate: added as a note on an existing enquiry
    HELD = "held"  # waiting in Spam review
    REJECTED = "rejected"  # failed a hard check; never shown to staff as an enquiry
    APPROVED = "approved"  # held, then approved by staff
    DELETED = "deleted"  # held, then deleted by staff


class FormSubmission(UUIDPk, Timestamps, Base):
    """Every public form submission, including rejected ones. Held/rejected purged at 90 days."""

    __tablename__ = "form_submissions"

    form: Mapped[str] = mapped_column(String(10))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    user_agent: Mapped[str | None] = mapped_column(Text)
    turnstile_ok: Mapped[bool | None] = mapped_column(Boolean)
    fill_seconds: Mapped[float | None] = mapped_column(Float)
    spam_score: Mapped[int] = mapped_column(Integer, default=0)
    spam_reasons: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    status: Mapped[str] = mapped_column(String(10), index=True)
    enquiry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enquiries.id")
    )
