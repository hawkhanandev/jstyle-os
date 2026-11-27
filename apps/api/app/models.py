"""Import every module's models so Alembic and tests see the full schema."""

from app.modules.auth.models import User, UserSession
from app.modules.email.models import EmailMessage, EmailTemplate, EmailThread
from app.modules.enquiries.models import Enquiry, PipelineHistory, PlannerCompany, Task
from app.modules.forms.models import FormSubmission
from app.modules.platform.models import AuditLog, OutboxEvent, SystemSetting
from app.modules.pricing.models import RateCardRow

__all__ = [
    "EmailMessage",
    "EmailTemplate",
    "EmailThread",
    "FormSubmission",
    "Enquiry",
    "PipelineHistory",
    "PlannerCompany",
    "Task",
    "AuditLog",
    "OutboxEvent",
    "RateCardRow",
    "SystemSetting",
    "User",
    "UserSession",
]
