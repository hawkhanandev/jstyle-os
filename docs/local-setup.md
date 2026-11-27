# Running Jstyle Business OS on your computer

Everything runs locally in Docker. You don't need a Google, Cloudflare or server account.

## One-time setup

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac or Windows) and start it.
2. Install [Git](https://git-scm.com/downloads) if you don't have it.
3. Get the code:

   ```bash
   git clone https://github.com/hawkhanandev/jstyle-os.git
   cd jstyle-os
   ```

## Start it

```bash
docker compose up --build
```

The first start takes a few minutes while images download. It's ready when the log shows
`Ready` from `web` and `Application startup complete` from `api`.

| Open | What it is |
| --- | --- |
| http://localhost:3000 | The CRM. Click **Local sign-in (development only)** |
| http://localhost:8025 | Mailpit: every email the CRM sends locally lands here, nothing reaches real people |
| http://localhost:8000/api/docs | API reference |

## Everyday commands

| Task | Command |
| --- | --- |
| Stop | `Ctrl+C`, or `docker compose down` |
| Start again (faster after the first time) | `docker compose up` |
| Get the latest code | `git pull && docker compose up --build` |
| Wipe all local data and start fresh | `docker compose down -v && docker compose up --build` |
| See the API log | `docker compose logs -f api` |

Code changes in `apps/api/app` and `apps/web/src` reload automatically.

## Signing in

Locally the CRM allows `owner@jstyle.local` and shows a **Local sign-in** button, so no Google
account is needed. That button only exists when `JSTYLE_ENV=local`; staging and production
use Google sign-in only.

To try real Google sign-in locally, copy `.env.example` to `.env` and fill in
`JSTYLE_GOOGLE_CLIENT_ID`, `JSTYLE_GOOGLE_CLIENT_SECRET` and `JSTYLE_ALLOWED_EMAIL`.

## Running the tests

```bash
docker compose up -d postgres
cd apps/api
uv sync
JSTYLE_TEST_DATABASE_URL=postgresql+psycopg://jstyle:jstyle@localhost:5432/jstyle_test uv run pytest
```

Create the test database once with
`docker compose exec postgres createdb -U jstyle jstyle_test`.

## If something goes wrong

- **Port already in use**: another program is using 3000, 5432, 6379, 8000 or 8025. Stop it, or
  stop an old run with `docker compose down`.
- **Sign-in loops back to the sign-in page**: clear cookies for localhost and try again.
- **Database errors after pulling new code**: run `docker compose up --build` again; migrations
  run on every start.
