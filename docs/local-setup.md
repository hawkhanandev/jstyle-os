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
| http://localhost:3000 | The CRM. Click **Local sign-in (this computer only)** |
| http://localhost:8025 | Mailpit: every email the CRM sends locally lands here, nothing reaches real people. Submit a form and the acknowledgement appears within a few seconds |
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
The **Sign in with Google** button only appears once Google credentials are set.

To try real Google sign-in locally, copy `.env.example` to `.env` and fill in
`JSTYLE_GOOGLE_CLIENT_ID`, `JSTYLE_GOOGLE_CLIENT_SECRET` and `JSTYLE_ALLOWED_EMAIL`.

## Ports

The stack publishes only these ports on your machine, all bound to `127.0.0.1`:

| Port | Service | Change it with |
| --- | --- | --- |
| 3000 | CRM web app | `JSTYLE_WEB_PORT` |
| 8000 | API | `JSTYLE_API_PORT` |
| 8025 | Mailpit inbox | `JSTYLE_MAIL_PORT` |
| 55432 | Postgres (for running tests or a database tool) | `JSTYLE_PG_PORT` |

Redis isn't published at all. Postgres uses 55432 rather than 5432, so a Postgres you
already run on your machine doesn't get in the way.

If a port is taken, create a file called `.env` next to `docker-compose.yml`, for example:

```bash
JSTYLE_WEB_PORT=3100
JSTYLE_PG_PORT=55433
```

then run `docker compose up` again and open the new address (here http://localhost:3100).

## Running the tests

```bash
docker compose up -d postgres
cd apps/api
uv sync
JSTYLE_TEST_DATABASE_URL=postgresql+psycopg://jstyle:jstyle@localhost:55432/jstyle_test uv run pytest
```

Create the test database once with
`docker compose exec postgres createdb -U jstyle jstyle_test`.

## If something goes wrong

- **"port is already allocated" or "address already in use"**: another program is using one of
  the ports above. Pick a different one in `.env` (see Ports), or stop an old run with
  `docker compose down`.
- **`npm error code ETIMEDOUT` (or another network error) during the build**: the connection
  dropped while downloading packages. Run `docker compose up --build` again; packages already
  downloaded are cached, so each re-run picks up where the last one stopped.
- **Sign-in loops back to the sign-in page**: clear cookies for localhost and try again.
- **"Internal Server Error" on a `/api/...` page, or "The CRM server isn't responding"**: the API container
  is not running. Run `docker compose logs api` to see why, then `docker compose up --build` again.
- **Database errors after pulling new code**: run `docker compose up --build` again; migrations
  run on every start.

## Testing client replies locally

Gmail isn't connected locally, so client replies can't arrive by email. Open an enquiry, go to the
**Email** tab and use **Local testing: pretend the client replied**. The reply goes through the same
matching code the Gmail sync will use, then shows up in the **Inbox** as unread. Replies you send
from the Inbox land in Mailpit.

## Testing scheduled emails without waiting

Scheduled emails (follow-ups, preparation guide, reminders) list on each enquiry. Locally, each one
has a **Send now (test)** button that sends it on the worker's next run instead of on its date.

## Backups and the walk-through

- Back up and restore with `scripts/backup-local.sh` and `scripts/restore-local.sh`; see
  [runbooks/backup-restore.md](runbooks/backup-restore.md).
- The full journey to test before going live is in [uat.md](uat.md).

## Connecting a Gmail account (optional)

1. Put the Google OAuth client in `.env` next to `docker-compose.yml`:
   ```bash
   JSTYLE_GOOGLE_CLIENT_ID=...
   JSTYLE_GOOGLE_CLIENT_SECRET=...
   ```
   The client must allow the redirect URI `http://localhost:3000/api/integrations/google/callback`,
   and the Gmail address must be a test user on the OAuth consent screen.
2. `docker compose up --build`, sign in with **Local sign-in**, open **Settings → Google account**
   and click **Connect Google account**. Sign in as the Gmail account and leave every box ticked.
   Google warns that the app isn't verified; that's expected for a test app.
3. The worker checks Gmail every minute (or click **Check Gmail now**). Only emails from people who
   already have an enquiry are added to the Inbox; everything else is left alone. The CRM never
   deletes or changes anything in Gmail.
4. **Send emails from this account** is off at first, so emails keep landing in Mailpit. Switch it
   on to send real emails from the Gmail address. Use a test enquiry with your own email address.
5. **Add booked weddings and trials to this calendar** creates all-day wedding events and two-hour
   trial events in the account's main calendar, moves them when dates change and removes them when
   a wedding is cancelled.

Disconnecting from Settings revokes the CRM's access at Google.
