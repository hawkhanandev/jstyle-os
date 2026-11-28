from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.responses import Response as StarletteResponse

from app.core.config import get_settings
from app.core.db import get_session
from app.modules.auth.routes import router as auth_router
from app.modules.bookings.routes import router as bookings_router
from app.modules.documents.routes import router as documents_router
from app.modules.email.routes import router as email_router
from app.modules.enquiries.routes import router as enquiries_router
from app.modules.forms.routes import public as forms_public
from app.modules.forms.routes import staff as forms_staff
from app.modules.inbox.routes import router as inbox_router
from app.modules.operations.routes import router as operations_router
from app.modules.payments.routes import router as payments_router
from app.modules.platform.routes import router as settings_router
from app.modules.pricing.routes import router as pricing_router
from app.modules.quotes.routes import router as quotes_router
from app.modules.replies.routes import router as replies_router

_local = get_settings().env == "local"
app = FastAPI(
    title="Jstyle Business OS",
    version="0.1.0",
    # API docs only on a developer's machine.
    openapi_url="/api/openapi.json" if _local else None,
    docs_url="/api/docs" if _local else None,
    redoc_url=None,
)


@app.middleware("http")
async def security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[StarletteResponse]]
) -> StarletteResponse:
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    # Client data must never sit in a shared or browser cache.
    response.headers.setdefault("Cache-Control", "no-store")
    return response


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
api.include_router(documents_router)
api.include_router(settings_router)
api.include_router(payments_router)
api.include_router(operations_router)
api.include_router(forms_public)
api.include_router(forms_staff)
app.include_router(api)
