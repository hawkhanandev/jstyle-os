from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.modules.enquiries.models import EnquiryType
from app.modules.enquiries.service import EnquiryInput

Text = Field(default=None, max_length=2000)


class _Common(BaseModel):
    # Anti-spam fields. `website` is the hidden honeypot; real people leave it empty.
    form_token: str | None = Field(default=None, max_length=100)
    turnstile_token: str | None = Field(default=None, max_length=4096)
    website: str | None = Field(default=None, max_length=500)

    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    region: Literal["HI", "OR", ""] | None = None
    venue_name: str | None = Field(default=None, max_length=300)
    venue_address: str | None = Field(default=None, max_length=500)
    notes: str | None = Text


class BrideForm(_Common):
    full_name: str = Field(min_length=2, max_length=200)
    preferred_contact: Literal["email", "phone", "text"] | None = None
    wedding_date: date
    wedding_type: str | None = Field(default=None, max_length=100)
    bridal_service: Literal["full", "hair_only", "makeup_only", "none"] = "full"
    attendants_hair: int = Field(default=0, ge=0, le=30)
    attendants_makeup: int = Field(default=0, ge=0, le=30)
    trial: bool = False
    travel_notes: str | None = Text

    def to_input(self) -> EnquiryInput:
        return EnquiryInput(
            type=EnquiryType.BRIDE,
            client_name=self.full_name,
            email=str(self.email),
            phone=self.phone,
            preferred_contact=self.preferred_contact,
            wedding_date=self.wedding_date,
            region=self.region or None,
            venue_name=self.venue_name,
            venue_address=self.venue_address,
            wedding_type=self.wedding_type,
            bridal_package=self.bridal_service,
            attendant_hair_count=self.attendants_hair,
            attendant_makeup_count=self.attendants_makeup,
            trial_requested=self.trial,
            travel_notes=self.travel_notes,
            notes=self.notes,
            raw=self.model_dump(mode="json", exclude=SPAM_FIELDS),
        )


class PlannerForm(_Common):
    company_name: str = Field(min_length=2, max_length=200)
    contact_name: str = Field(min_length=2, max_length=200)
    event_date: date
    client_name: str | None = Field(default=None, max_length=200)
    services_needed: str | None = Text
    people_count: int | None = Field(default=None, ge=0, le=100)
    stylists_needed: int | None = Field(default=None, ge=0, le=20)

    def to_input(self) -> EnquiryInput:
        return EnquiryInput(
            type=EnquiryType.PLANNER,
            client_name=self.client_name or self.contact_name,
            email=str(self.email),
            phone=self.phone,
            wedding_date=self.event_date,
            region=self.region or None,
            venue_name=self.venue_name,
            venue_address=self.venue_address,
            notes=self.notes,
            planner_company=self.company_name,
            planner_contact_name=self.contact_name,
            services={
                "services_needed": self.services_needed,
                "people_count": self.people_count,
                "stylists_needed": self.stylists_needed,
            },
            raw=self.model_dump(mode="json", exclude=SPAM_FIELDS),
        )


SPAM_FIELDS = {"form_token", "turnstile_token", "website"}
