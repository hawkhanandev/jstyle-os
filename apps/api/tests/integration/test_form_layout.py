from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.enquiries.models import Enquiry

from .test_forms import bride
from .test_operations import TODAY, book, make_enquiry


def names(cfg: dict) -> list[str]:  # type: ignore[type-arg]
    return [f["name"] for f in cfg["layout"]["fields"]]


def test_default_layout_matches_the_built_in_form(authed: TestClient) -> None:
    cfg = authed.get("/api/public/forms/config", params={"kind": "bride"}).json()
    assert cfg["form_token"]
    assert names(cfg)[:3] == ["full_name", "email", "phone"]
    email = next(f for f in cfg["layout"]["fields"] if f["name"] == "email")
    assert email["required"] and email["label"] == "Email"
    assert "layout" not in authed.get("/api/public/forms/config").json()


def test_edit_layout_then_submit(authed: TestClient, db: Session) -> None:
    editor = authed.get("/api/form-layouts/bride").json()
    lay = editor["layout"]
    lay["title"] = "Tell us about your day"
    lay["fields"]["phone"]["hidden"] = True
    lay["fields"]["venue_name"]["required"] = True
    lay["fields"]["venue_name"]["label"] = "Ceremony venue"
    # Locked fields can't be hidden or made optional.
    lay["fields"]["email"]["hidden"] = True
    lay["fields"]["email"]["required"] = False
    lay["fields"]["region"]["hidden"] = True
    lay["custom"] = [
        {
            "id": "c_howfound",
            "label": "How did you hear about us?",
            "type": "text",
            "required": True,
        },
        {"id": "c_airbrush", "label": "Interested in airbrush?", "type": "yesno"},
    ]
    lay["order"] = ["c_howfound", *lay["order"]]
    saved = authed.put("/api/form-layouts/bride", json=lay)
    assert saved.status_code == 200, saved.text
    f = saved.json()["layout"]["fields"]
    assert not f["email"]["hidden"] and f["email"]["required"] and not f["region"]["hidden"]

    cfg = authed.get("/api/public/forms/config", params={"kind": "bride"}).json()
    assert cfg["layout"]["title"] == "Tell us about your day"
    assert names(cfg)[0] == "c_howfound"
    assert "phone" not in names(cfg)
    venue = next(x for x in cfg["layout"]["fields"] if x["name"] == "venue_name")
    assert venue["label"] == "Ceremony venue" and venue["required"]

    missing = authed.post(
        "/api/public/enquiries/bride", json=bride(venue_name="", custom={"c_airbrush": "yes"})
    )
    assert missing.status_code == 422
    assert "Ceremony venue" in missing.json()["message"]
    assert "How did you hear about us?" in missing.json()["message"]

    ok = authed.post(
        "/api/public/enquiries/bride",
        json=bride(custom={"c_howfound": "Instagram", "c_airbrush": "yes", "c_unknown": "x"}),
    )
    assert ok.status_code == 200, ok.text
    e = db.scalars(select(Enquiry)).one()
    assert e.notes is not None
    assert "How did you hear about us?: Instagram" in e.notes
    assert "Interested in airbrush?: Yes" in e.notes
    assert "c_unknown" not in e.notes

    reset = authed.post("/api/form-layouts/bride/reset").json()
    assert reset["layout"]["custom"] == [] and reset["layout"]["title"] == "Bridal enquiry"


def test_dashboard_splits_hawaii_and_oregon(authed: TestClient, db: Session) -> None:
    e = make_enquiry(db, TODAY + timedelta(days=60))
    book(authed, db, e)
    d = authed.get("/api/dashboard").json()
    hi, or_ = d["regions"]["HI"], d["regions"]["OR"]
    assert hi["upcoming_weddings"] == 1 and hi["booked_value_cents"] > 0
    assert hi["next_wedding"]["client_name"] == "Kailani Akana"
    assert or_["upcoming_weddings"] == 0 and or_["next_wedding"] is None
    assert d["upcoming_weddings"][0]["region"] == "HI"
