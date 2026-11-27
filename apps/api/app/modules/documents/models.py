from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk


class Document(UUIDPk, Timestamps, Base):
    """Any stored file: generated PDFs and uploaded evidence."""

    __tablename__ = "documents"

    kind: Mapped[str] = mapped_column(String(30))  # contract | invoice | signed_contract | ...
    enquiry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enquiries.id"), index=True
    )
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)


class ContractStatus(StrEnum):
    PREPARED = "prepared"  # PDF generated, not yet sent
    SENDING = "sending"
    SENT = "sent"
    SIGNED = "signed"
    VOID = "void"


class Contract(UUIDPk, Timestamps, Base):
    __tablename__ = "contracts"
    __table_args__ = (UniqueConstraint("booking_id", "version"),)

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), index=True
    )
    enquiry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("enquiries.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default=ContractStatus.PREPARED)
    terms_html: Mapped[str] = mapped_column(Text)  # exact terms used, frozen
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_on: Mapped[date | None] = mapped_column(Date)
    signed_method: Mapped[str | None] = mapped_column(String(30))
    signed_note: Mapped[str | None] = mapped_column(Text)
    signed_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id")
    )
    marked_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvoiceKind(StrEnum):
    DEPOSIT = "deposit"
    BALANCE = "balance"
    ADJUSTMENT = "adjustment"


class InvoiceStatus(StrEnum):
    PREPARED = "prepared"
    ISSUED = "issued"  # sent to the client
    PAID = "paid"  # set from verified payments (Phase 6)
    VOID = "void"


class Invoice(UUIDPk, Timestamps, Base):
    __tablename__ = "invoices"

    number: Mapped[str] = mapped_column(String(20), unique=True)  # JS-2026-0001
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), index=True
    )
    enquiry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("enquiries.id"))
    kind: Mapped[str] = mapped_column(String(12))
    amount_cents: Mapped[int] = mapped_column(Integer)
    due_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default=InvoiceStatus.PREPARED)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvoiceCounter(Base):
    """One row per year; locked while a number is taken so numbers never repeat or skip."""

    __tablename__ = "invoice_counters"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last: Mapped[int] = mapped_column(Integer, default=0)
