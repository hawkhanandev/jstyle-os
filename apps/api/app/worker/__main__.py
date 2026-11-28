import logging

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.modules.email.mailer import SmtpMailer
from app.modules.google.client import HttpGoogleApi
from app.modules.google.service import RoutingMailer
from app.worker.handlers import Deps
from app.worker.runner import run_forever

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    s = get_settings()
    factory = get_sessionmaker()
    google = (
        HttpGoogleApi(s.google_client_id, s.google_client_secret) if s.google_configured else None
    )
    fallback = SmtpMailer(s.smtp_host, s.smtp_port) if s.smtp_host else None
    if google is None and fallback is None:
        raise SystemExit("No mail transport: set JSTYLE_SMTP_HOST (local) or connect Gmail.")
    # Gmail when an account is connected with sending switched on; otherwise SMTP (Mailpit locally).
    mailer = RoutingMailer(factory, google, s, fallback) if google else fallback
    assert mailer is not None
    run_forever(factory, Deps(settings=s, mailer=mailer, google=google))
