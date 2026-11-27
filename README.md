# Jstyle Business OS

Custom CRM for Jstyle wedding hair and makeup: website enquiries, Hawaii and Oregon pricing,
quote approval, Gmail conversations, contracts and deposit invoices, Venmo/Zelle payment
verification, and wedding preparation emails.

Design: see the Jstyle Business OS design document and execution plan.

## Layout

| Path | What |
| --- | --- |
| `apps/api` | FastAPI backend (Python 3.12, SQLAlchemy, Alembic, Celery) |
| `apps/web` | Next.js admin app and public form pages |
| `infra` | Docker Compose, Caddy, backups, runbooks |
| `wordpress` | Form embed snippet |
| `docs` | Acceptance checklist, setup guides |

## Run it locally

```bash
docker compose up --build
```

Then open http://localhost:3000 and click **Local sign-in**. Emails land in Mailpit at
http://localhost:8025. Full guide: [docs/local-setup.md](docs/local-setup.md).

Money is stored in integer cents. Pricing lives only in `apps/api/app/modules/pricing` and is a
pure function.
