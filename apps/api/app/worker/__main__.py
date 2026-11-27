import logging

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.modules.email.mailer import Mailer, SmtpMailer
from app.worker.handlers import Deps
from app.worker.runner import run_forever


def build_mailer() -> Mailer:
    s = get_settings()
    if s.smtp_host:
        return SmtpMailer(s.smtp_host, s.smtp_port)
    raise SystemExit("No mail transport: set JSTYLE_SMTP_HOST (local) or connect Gmail.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_forever(get_sessionmaker(), Deps(settings=get_settings(), mailer=build_mailer()))
