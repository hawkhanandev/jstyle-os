from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.email.mailer import Mailer
from app.modules.email.send import deliver
from app.modules.platform.models import OutboxEvent


@dataclass
class Deps:
    settings: Settings
    mailer: Mailer


Handler = Callable[[Session, OutboxEvent, Deps], None]


def email_send(db: Session, event: OutboxEvent, deps: Deps) -> None:
    deliver(db, event, deps.mailer, deps.settings)


HANDLERS: dict[str, Handler] = {
    "email.send": email_send,
}
