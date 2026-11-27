"""Idempotent local seed. Safe to run on every start; never overwrites edited values.

Usage: python -m app.seed
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert

from app.core.db import get_sessionmaker
from app.modules.platform.audit import SYSTEM
from app.modules.platform.models import SystemSetting
from app.modules.pricing.service import ensure_defaults

DEFAULT_SETTINGS: dict[str, Any] = {
    "business": {
        "name": "Jstyle Hair & Makeup",
        "address": "Placeholder address, edit in Settings",
        "email": "",
        "phone": "",
    },
    "payment_instructions": {
        "venmo": "@placeholder-venmo",
        "zelle": "placeholder@example.com",
    },
    "deposit_due_days": 7,
    "quote_follow_up_days": 5,
}


def run() -> None:
    with get_sessionmaker()() as db:
        for key, value in DEFAULT_SETTINGS.items():
            db.execute(
                insert(SystemSetting)
                .values(key=key, value=value)
                .on_conflict_do_nothing(index_elements=["key"])
            )
        cards = ensure_defaults(db, SYSTEM)
        db.commit()
    print(f"seed: {len(DEFAULT_SETTINGS)} settings ensured, {cards} rate cards created")


if __name__ == "__main__":
    run()
