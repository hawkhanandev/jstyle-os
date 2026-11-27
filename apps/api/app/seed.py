"""Idempotent local seed. Safe to run on every start; never overwrites edited values.

Usage: python -m app.seed
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.demo_data import seed_demo
from app.modules.email.templates import ensure_defaults as ensure_templates
from app.modules.platform.audit import SYSTEM
from app.modules.platform.models import SystemSetting
from app.modules.platform.settings import DEFAULT_SETTINGS
from app.modules.pricing.service import ensure_defaults


def run() -> None:
    with get_sessionmaker()() as db:
        for key, value in DEFAULT_SETTINGS.items():
            db.execute(
                insert(SystemSetting)
                .values(key=key, value=value)
                .on_conflict_do_nothing(index_elements=["key"])
            )
        cards = ensure_defaults(db, SYSTEM)
        tpls = ensure_templates(db, SYSTEM)
        demo = seed_demo(db) if get_settings().env == "local" else 0
        db.commit()
    print(
        f"seed: {len(DEFAULT_SETTINGS)} settings, {cards} rate cards, "
        f"{tpls} templates, {demo} demo enquiries"
    )


if __name__ == "__main__":
    run()
