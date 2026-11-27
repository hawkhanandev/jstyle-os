from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.platform.audit import SYSTEM
from app.modules.platform.models import AuditLog
from app.modules.pricing import Region
from app.modules.pricing.service import active_card, ensure_defaults, history


def test_defaults_seed_once(db: Session) -> None:
    assert ensure_defaults(db, SYSTEM) == 2
    assert ensure_defaults(db, SYSTEM) == 0
    _, hi = active_card(db, Region.HAWAII)
    assert hi.package_cents == 32_500 and hi.version == 1


def test_new_version_deactivates_old_and_is_audited(authed: TestClient, db: Session) -> None:
    ensure_defaults(db, SYSTEM)
    body = {
        "region": "HI",
        "package_cents": 35_000,
        "attendant_hair_cents": 12_000,
        "attendant_makeup_cents": 13_000,
        "trial_cents": 25_000,
        "deposit_cents": 10_000,
        "travel_per_stylist_cents": 7_500,
        "note": "2027 rates",
    }
    res = authed.post("/api/rate-cards", json=body)
    assert res.status_code == 201, res.text
    assert res.json()["version"] == 2
    rows = history(db, Region.HAWAII)
    assert [(r.version, r.is_active) for r in rows] == [(2, True), (1, False)]
    assert rows[1].rates["package_cents"] == 32_500  # old version untouched
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "rate_card.create")).all()
    assert audit[-1].before["package_cents"] == 32_500  # type: ignore[index]
    assert audit[-1].after["package_cents"] == 35_000  # type: ignore[index]


def test_oregon_card_needs_travel_range(authed: TestClient) -> None:
    body = {
        "region": "OR",
        "package_cents": 50_000,
        "attendant_hair_cents": 16_500,
        "attendant_makeup_cents": 19_000,
        "trial_cents": 22_500,
        "deposit_cents": 20_000,
    }
    assert authed.post("/api/rate-cards", json=body).status_code == 422


def test_preview_uses_active_card(authed: TestClient, db: Session) -> None:
    ensure_defaults(db, SYSTEM)
    res = authed.post(
        "/api/pricing/preview",
        json={
            "region": "OR",
            "attendant_hair": 2,
            "attendant_makeup": 2,
            "travel_zone": "outside",
            "travel_fee_cents": 7_500,
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["total_cents"] == 128_500
    assert res.json()["balance_cents"] == 108_500


def test_rate_cards_need_sign_in(client: TestClient) -> None:
    assert client.get("/api/rate-cards").status_code == 401
