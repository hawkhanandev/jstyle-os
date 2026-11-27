from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.modules.platform.models import AuditLog


@dataclass(frozen=True)
class Actor:
    """Who did it. There is one business account; the device tells sessions apart.

    The UI shows this as "Business account" plus the device label, never as a person.
    """

    account_email: str | None = None
    session_id: uuid.UUID | None = None
    ip: str | None = None
    user_agent: str | None = None
    device_label: str | None = None


SYSTEM = Actor(device_label="system")


def write_audit(
    session: Session,
    actor: Actor,
    action: str,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    """Add an audit row to the caller's transaction. The caller commits."""
    row = AuditLog(
        account_email=actor.account_email,
        session_id=actor.session_id,
        ip=actor.ip,
        user_agent=actor.user_agent,
        device_label=actor.device_label,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
    )
    session.add(row)
    return row
