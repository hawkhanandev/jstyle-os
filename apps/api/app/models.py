"""Import every module's models so Alembic and tests see the full schema."""

from app.modules.auth.models import User, UserSession
from app.modules.bookings.models import Booking
from app.modules.documents.models import Contract, Document, Invoice, InvoiceCounter
from app.modules.email.models import EmailMessage, EmailTemplate, EmailThread
from app.modules.enquiries.models import Enquiry, PipelineHistory, PlannerCompany, Task
from app.modules.forms.models import FormSubmission
from app.modules.operations.models import Trial, WeddingPlan
from app.modules.payments.models import Payment
from app.modules.platform.models import AuditLog, OutboxEvent, SystemSetting
from app.modules.pricing.models import RateCardRow
from app.modules.quotes.models import Quote, QuoteLineItem
from app.modules.replies.models import ReplySuggestion
from app.modules.scheduling.models import ScheduledEmail

__all__ = [
    "Trial",
    "WeddingPlan",
    "ScheduledEmail",
    "Payment",
    "Contract",
    "Document",
    "Invoice",
    "InvoiceCounter",
    "Booking",
    "ReplySuggestion",
    "Quote",
    "QuoteLineItem",
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
