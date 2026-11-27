from fastapi import APIRouter, FastAPI

from app.core.config import get_settings

app = FastAPI(
    title="Jstyle Business OS",
    version="0.1.0",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
)
api = APIRouter(prefix="/api")


@api.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Database and Redis checks are added with the platform core."""
    return {"status": "ok", "env": get_settings().env}


app.include_router(api)
