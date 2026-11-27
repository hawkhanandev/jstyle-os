from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.modules.auth.routes import router as auth_router
from app.modules.bookings.routes import router as bookings_router
from app.modules.email.routes import router as email_router
from app.modules.enquiries.routes import router as enquiries_router
from app.modules.forms.routes import public as forms_public
from app.modules.forms.routes import staff as forms_staff
from app.modules.inbox.routes import router as inbox_router
from app.modules.pricing.routes import router as pricing_router
from app.modules.quotes.routes import router as quotes_router
from app.modules.replies.routes import router as replies_router

app = FastAPI(
    title="Jstyle Business OS",
    version="0.1.0",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
)
api = APIRouter(prefix="/api")


@api.get("/health")
def health(response: Response, db: Annotated[Session, Depends(get_session)]) -> dict[str, str]:
    """Used by Docker health checks and Uptime Kuma. Redis is added with the worker."""
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "down"
        response.status_code = 503
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "env": get_settings().env,
    }


api.include_router(auth_router)
api.include_router(pricing_router)
api.include_router(enquiries_router)
api.include_router(email_router)
api.include_router(quotes_router)
api.include_router(inbox_router)
api.include_router(replies_router)
api.include_router(bookings_router)
api.include_router(forms_public)
api.include_router(forms_staff)
app.include_router(api)
