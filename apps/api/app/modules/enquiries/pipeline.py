"""Commercial pipeline state machine (design doc, State machines).

Every status change goes through transition(). Routes never set pipeline_status directly.
Guards that need other modules (quotes, bookings) are passed in by those modules as
`guard_ok`/`reason`, so this module stays free of their tables.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.enquiries.models import CLOSED, Enquiry, Pipeline, PipelineHistory
from app.modules.platform.audit import Actor, write_audit

P = Pipeline
OPEN = set(Pipeline) - CLOSED

ALLOWED: dict[Pipeline, set[Pipeline]] = {
    P.NEW_INQUIRY: {P.UNDER_REVIEW, P.LOST_DECLINED},
    P.UNDER_REVIEW: {P.NEEDS_INFORMATION, P.QUOTE_DRAFT, P.LOST_DECLINED},
    P.NEEDS_INFORMATION: {P.UNDER_REVIEW, P.QUOTE_DRAFT, P.LOST_DECLINED},
    P.QUOTE_DRAFT: {P.AWAITING_APPROVAL, P.LOST_DECLINED},
    P.AWAITING_APPROVAL: {P.QUOTE_DRAFT, P.QUOTE_SENT, P.LOST_DECLINED},
    P.QUOTE_SENT: {P.DISCUSSION_REVISION, P.QUOTE_ACCEPTED, P.LOST_DECLINED, P.EXPIRED},
    P.DISCUSSION_REVISION: {P.AWAITING_APPROVAL, P.QUOTE_ACCEPTED, P.LOST_DECLINED, P.EXPIRED},
    P.QUOTE_ACCEPTED: {P.CONTRACT_DEPOSIT_PENDING, P.CANCELLED},
    P.CONTRACT_DEPOSIT_PENDING: {P.BOOKED, P.CANCELLED},
    P.BOOKED: {P.CANCELLED},
    P.LOST_DECLINED: {P.UNDER_REVIEW},  # reopen
    P.EXPIRED: {P.UNDER_REVIEW},  # reopen
    P.CANCELLED: set(),
}

NEEDS_REASON = {P.NEEDS_INFORMATION, P.LOST_DECLINED, P.EXPIRED, P.CANCELLED}


class TransitionBlocked(Exception):
    def __init__(self, current: str, target: str, missing: list[str]) -> None:
        super().__init__(f"{current} -> {target} blocked: {', '.join(missing)}")
        self.current = current
        self.target = target
        self.missing = missing


def transition(
    db: Session,
    enquiry: Enquiry,
    target: Pipeline,
    actor: Actor,
    *,
    reason: str | None = None,
    missing: list[str] | None = None,
) -> None:
    """Move the enquiry to `target`, writing history and audit in the caller's transaction.

    `missing` lets a calling module report guard failures (e.g. booking gate items); any
    entry blocks the transition.
    """
    current = Pipeline(enquiry.pipeline_status)
    problems = list(missing or [])
    if target not in ALLOWED[current]:
        problems.append(f"not_allowed_from_{current.value}")
    if target in NEEDS_REASON and not (reason and reason.strip()):
        problems.append("reason_required")
    if problems:
        raise TransitionBlocked(current.value, target.value, problems)

    enquiry.pipeline_status = target.value
    if target in CLOSED:
        enquiry.closed_reason = reason
    elif current in CLOSED:
        enquiry.closed_reason = None
    db.add(
        PipelineHistory(
            enquiry_id=enquiry.id,
            from_status=current.value,
            to_status=target.value,
            reason=reason,
            at=utcnow(),
        )
    )
    write_audit(
        db,
        actor,
        "enquiry.transition",
        entity_type="enquiry",
        entity_id=enquiry.id,
        before={"pipeline_status": current.value},
        after={"pipeline_status": target.value, "reason": reason},
    )
