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

## Backend quick start

```bash
docker compose -f infra/docker-compose.dev.yml up -d
cd apps/api
uv sync
uv run pytest
uv run uvicorn app.main:app --reload
```

Money is stored in integer cents. Pricing lives only in `app/modules/pricing` and is a pure function.
