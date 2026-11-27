from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.enquiries.models import Enquiry, EnquiryType, Pipeline, PlannerCompany
from app.modules.enquiries.pipeline import TransitionBlocked, transition
from app.modules.enquiries.service import EnquiryInput, create_enquiry, find_duplicate
from app.modules.platform.audit import SYSTEM

TODAY = date(2026, 12, 1)


def bride(**kw: object) -> EnquiryInput:
    base: dict[str, object] = dict(
        type=EnquiryType.BRIDE,
        client_name="Kailani Akana",
        email="Kailani@Example.com",
        wedding_date=date(2027, 6, 12),
        venue_address="Kualoa Ranch, Kaneohe HI 96744",
        attendant_hair_count=2,
        attendant_makeup_count=2,
    )
    base.update(kw)
    return EnquiryInput(**base)  # type: ignore[arg-type]


def test_create_detects_region_and_flags(db: Session) -> None:
    e = create_enquiry(db, bride(), SYSTEM, today=TODAY)
    assert e.region == "HI" and e.timezone == "Pacific/Honolulu"
    assert e.travel_zone == "outside"
    assert e.email == "kailani@example.com"
    assert e.needs_review_flags == []
    soon = create_enquiry(
        db, bride(wedding_date=TODAY + timedelta(days=5), venue_address="TX"), SYSTEM, today=TODAY
    )
    assert set(soon.needs_review_flags) == {"region_unknown", "date_under_14_days"}


def test_planner_creates_company_once(db: Session) -> None:
    for _ in range(2):
        create_enquiry(
            db,
            bride(
                type=EnquiryType.PLANNER, planner_company="Aloha Events", email="plan@aloha.example"
            ),
            SYSTEM,
            today=TODAY,
        )
    assert len(db.scalars(select(PlannerCompany)).all()) == 1


def test_duplicate_lookup(db: Session) -> None:
    create_enquiry(db, bride(), SYSTEM, today=TODAY)
    db.flush()
    assert find_duplicate(db, "KAILANI@example.com", date(2027, 6, 12), today=date.today())
    assert find_duplicate(db, "kailani@example.com", date(2027, 6, 13), today=date.today()) is None


def test_transitions_are_guarded(db: Session) -> None:
    e = create_enquiry(db, bride(), SYSTEM, today=TODAY)
    with pytest.raises(TransitionBlocked):
        transition(db, e, Pipeline.BOOKED, SYSTEM)
    with pytest.raises(TransitionBlocked) as info:
        transition(db, e, Pipeline.LOST_DECLINED, SYSTEM)
    assert "reason_required" in info.value.missing
    transition(db, e, Pipeline.UNDER_REVIEW, SYSTEM)
    transition(db, e, Pipeline.LOST_DECLINED, SYSTEM, reason="Booked another artist")
    assert e.closed_reason == "Booked another artist"
    transition(db, e, Pipeline.UNDER_REVIEW, SYSTEM)
    assert e.closed_reason is None


def test_api_list_patch_and_actions(authed: TestClient, db: Session) -> None:
    e = create_enquiry(db, bride(), SYSTEM, today=TODAY)
    create_enquiry(
        db,
        bride(client_name="Ava Oregon", email="ava@example.com", venue_address="Portland OR 97201"),
        SYSTEM,
        today=TODAY,
    )
    db.flush()
    assert len(authed.get("/api/enquiries", params={"region": "HI"}).json()) == 1
    assert authed.get("/api/enquiries", params={"q": "ava"}).json()[0]["region"] == "OR"

    res = authed.patch(f"/api/enquiries/{e.id}", json={"stylists_required": 1})
    assert res.status_code == 200 and res.json()["stylists_required"] == 1

    blocked = authed.post(f"/api/enquiries/{e.id}/mark-lost", json={})
    assert blocked.status_code == 409
    assert "reason_required" in blocked.json()["detail"]["details"]

    assert authed.post(f"/api/enquiries/{e.id}/start-review").status_code == 200
    detail = authed.get(f"/api/enquiries/{e.id}").json()
    assert detail["pipeline_status"] == "UNDER_REVIEW"
    assert detail["history"][0]["to_status"] == "UNDER_REVIEW"


def test_status_cannot_be_patched(authed: TestClient, db: Session) -> None:
    e = create_enquiry(db, bride(), SYSTEM, today=TODAY)
    db.flush()
    authed.patch(f"/api/enquiries/{e.id}", json={"pipeline_status": "BOOKED"})
    assert db.get(Enquiry, e.id).pipeline_status == "NEW_INQUIRY"  # type: ignore[union-attr]


def test_demo_seed_runs_once(db: Session) -> None:
    from app.demo_data import seed_demo

    assert seed_demo(db, TODAY) == 5
    assert seed_demo(db, TODAY) == 0
