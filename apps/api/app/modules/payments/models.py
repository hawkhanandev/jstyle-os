from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk


class PaymentMethod(StrEnum):
    VENMO = "venmo"
    ZELLE = "zelle"
    CASH = "cash"
    CHECK = "check"
    OTHER = "other"


class PaymentStatus(StrEnum):
    RECORDED = "recorded"  # client says they paid; not yet seen in the account
    VERIFIED = "verified"  # seen in Venmo/Zelle; counts towards balances
    REJECTED = "rejected"  # never arrived or wrong amount
    VOID = "void"  # entered by mistake


class Payment(UUIDPk, Timestamps, Base):
    __tablename__ = "payments"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), index=True
    )
    enquiry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("enquiries.id"))
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id")
    )
    method: Mapped[str] = mapped_column(String(10))
    amount_cents: Mapped[int] = mapped_column(Integer)
    received_on: Mapped[date] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default=PaymentStatus.RECORDED, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_reason: Mapped[str | None] = mapped_column(Text)
