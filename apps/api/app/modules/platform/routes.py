from __future__ import annotations

from typing import Annotated, Any

import nh3
from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.auth.deps import Account
from app.modules.platform import settings

router = APIRouter(prefix="/settings", tags=["settings"])
DB = Annotated[Session, Depends(get_session)]


class BusinessIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    legal_name: str = Field(default="", max_length=200)
    address: str = Field(default="", max_length=500)
    email: EmailStr | None = None
    phone: str = Field(default="", max_length=50)


class PaymentIn(BaseModel):
    venmo: str = Field(default="", max_length=100)
    zelle: str = Field(default="", max_length=200)


class TermsIn(BaseModel):
    bride: str = Field(min_length=1, max_length=50000)
    planner: str = Field(min_length=1, max_length=50000)


class SchedulingIn(BaseModel):
    deposit_due_days: int = Field(ge=1, le=60)
    balance_due_hours: int = Field(ge=0, le=24 * 30)


TERMS_TAGS = {"p", "ol", "ul", "li", "strong", "em", "b", "i", "br", "h3", "h4", "span"}


@router.get("")
def get_all(account: Account, db: DB) -> dict[str, Any]:
    return {
        "business": settings.get(db, "business"),
        "payment_instructions": settings.get(db, "payment_instructions"),
        "contract_terms": settings.get(db, "contract_terms"),
        "scheduling": {
            "deposit_due_days": settings.get(db, "deposit_due_days"),
            "balance_due_hours": settings.get(db, "balance_due_hours"),
        },
    }


@router.put("/business")
def put_business(body: BusinessIn, account: Account, db: DB) -> dict[str, Any]:
    value = settings.get(db, "business") | body.model_dump(mode="json")
    value["email"] = value.get("email") or ""
    settings.put(db, "business", value, account.actor)
    db.commit()
    return get_all(account, db)


@router.put("/payment-instructions")
def put_payment(body: PaymentIn, account: Account, db: DB) -> dict[str, Any]:
    settings.put(db, "payment_instructions", body.model_dump(), account.actor)
    db.commit()
    return get_all(account, db)


@router.put("/contract-terms")
def put_terms(body: TermsIn, account: Account, db: DB) -> dict[str, Any]:
    clean = {
        k: nh3.clean(v, tags=TERMS_TAGS, attributes={"p": {"class"}, "span": {"class"}})
        for k, v in body.model_dump().items()
    }
    settings.put(db, "contract_terms", clean, account.actor)
    db.commit()
    return get_all(account, db)


@router.put("/scheduling")
def put_scheduling(body: SchedulingIn, account: Account, db: DB) -> dict[str, Any]:
    settings.put(db, "deposit_due_days", body.deposit_due_days, account.actor)
    settings.put(db, "balance_due_hours", body.balance_due_hours, account.actor)
    db.commit()
    return get_all(account, db)
