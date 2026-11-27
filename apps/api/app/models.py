"""Import every module's models so Alembic and tests see the full schema."""

from app.modules.auth.models import User, UserSession
from app.modules.platform.models import AuditLog, OutboxEvent, SystemSetting
from app.modules.pricing.models import RateCardRow

__all__ = ["AuditLog", "OutboxEvent", "RateCardRow", "SystemSetting", "User", "UserSession"]
