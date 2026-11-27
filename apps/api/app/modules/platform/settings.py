"""Business settings stored in system_settings, with defaults for missing fields."""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from app.modules.documents.defaults import BRIDE_TERMS, PLANNER_TERMS
from app.modules.platform.audit import Actor, write_audit
from app.modules.platform.models import SystemSetting

DEFAULT_SETTINGS: dict[str, Any] = {
    "business": {
        "name": "Jstyle Hair & Makeup",
        "legal_name": "",
        "address": "Placeholder address, edit in Settings",
        "email": "",
        "phone": "",
    },
    "payment_instructions": {
        "venmo": "@placeholder-venmo",
        "zelle": "placeholder@example.com",
    },
    "deposit_due_days": 7,
    "balance_due_hours": 48,
    "contract_terms": {"bride": BRIDE_TERMS, "planner": PLANNER_TERMS},
    "quote_follow_up_days": 5,
}


def get(db: Session, key: str) -> Any:
    default = copy.deepcopy(DEFAULT_SETTINGS.get(key))
    row = db.get(SystemSetting, key)
    if row is None:
        return default
    if isinstance(default, dict) and isinstance(row.value, dict):
        return default | row.value
    return row.value


def put(db: Session, key: str, value: Any, actor: Actor) -> None:
    row = db.get(SystemSetting, key)
    before = row.value if row else None
    if row is None:
        db.add(SystemSetting(key=key, value=value))
    else:
        row.value = value
    write_audit(
        db,
        actor,
        "settings.update",
        entity_type="setting",
        before={key: before},
        after={key: value},
    )
    db.flush()
