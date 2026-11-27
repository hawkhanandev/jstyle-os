"""Sample enquiries for local testing only. Never runs outside JSTYLE_ENV=local."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.enquiries.models import Enquiry, EnquiryType, Pipeline
from app.modules.enquiries.pipeline import transition
from app.modules.enquiries.service import EnquiryInput, create_enquiry
from app.modules.platform.audit import SYSTEM


def seed_demo(db: Session, today: date | None = None) -> int:
    if db.scalar(select(func.count()).select_from(Enquiry)):
        return 0
    today = today or date.today()
    samples = [
        (
            EnquiryInput(
                EnquiryType.BRIDE,
                "Kailani Akana",
                "kailani@example.com",
                "808-555-0101",
                "email",
                today + timedelta(days=190),
                "HI",
                "Kualoa Ranch",
                "49-560 Kamehameha Hwy, Kaneohe, HI 96744",
                "Outdoor ceremony",
                "full",
                2,
                2,
                True,
                "Ranch is about 45 minutes from Waikiki",
                None,
            ),
            [],
        ),
        (
            EnquiryInput(
                EnquiryType.BRIDE,
                "Mia Fernandez",
                "mia.f@example.com",
                "808-555-0144",
                "text",
                today + timedelta(days=95),
                "HI",
                "Halekulani",
                "2199 Kalia Rd, Honolulu, HI 96815",
                "Hotel ballroom",
                "full",
                4,
                3,
                False,
                None,
                "Getting ready from 7am",
            ),
            [Pipeline.UNDER_REVIEW],
        ),
        (
            EnquiryInput(
                EnquiryType.BRIDE,
                "Ava Thompson",
                "ava.t@example.com",
                "503-555-0188",
                "email",
                today + timedelta(days=240),
                "OR",
                "The Allison Inn",
                "2525 Allison Ln, Newberg, OR 97132",
                "Vineyard",
                "full",
                2,
                2,
                False,
                "About 40 minutes from Portland",
                None,
            ),
            [Pipeline.UNDER_REVIEW],
        ),
        (
            EnquiryInput(
                EnquiryType.BRIDE,
                "Grace Lee",
                "grace.lee@example.com",
                "503-555-0122",
                "phone",
                today + timedelta(days=60),
                "OR",
                "Elopement at Multnomah Falls",
                "Multnomah Falls, OR 97014",
                "Elopement",
                "full",
                0,
                0,
                False,
                None,
                "Just me!",
            ),
            [],
        ),
        (
            EnquiryInput(
                EnquiryType.PLANNER,
                "Leilani Kahale",
                "leilani@alohaevents.example",
                "808-555-0177",
                "email",
                today + timedelta(days=150),
                "HI",
                "Four Seasons Ko Olina",
                "92-1001 Olani St, Kapolei, HI 96707",
                "Resort",
                None,
                6,
                6,
                False,
                None,
                "Bride plus six bridesmaids",
                planner_company="Aloha Events Co.",
                planner_contact_name="Leilani Kahale",
            ),
            [],
        ),
    ]
    for data, steps in samples:
        e = create_enquiry(db, data, SYSTEM, today=today)
        for step in steps:
            transition(db, e, step, SYSTEM)
    return len(samples)
