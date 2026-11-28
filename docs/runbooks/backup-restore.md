# Backup and restore (local)

Everything the CRM knows lives in two places: the Postgres database and the documents folder
(generated PDFs and uploaded signed contracts). A backup copies both.

## Make a backup

With `docker compose up` running, from the repository folder:

```bash
scripts/backup-local.sh            # writes ./backups/jstyle-YYYYMMDD-HHMMSS/
scripts/backup-local.sh ~/Backups  # or choose a folder
```

Each backup folder holds `database.dump`, `documents.tar.gz` and `SHA256SUMS`. The `backups/`
folder is git-ignored, so client data never ends up in the repository. Copy backups somewhere
safe (an external drive or encrypted cloud folder); they contain client names and emails.

## Restore a backup

```bash
scripts/restore-local.sh backups/jstyle-20261128-101500
```

The script checks the checksums, asks you to type `RESTORE`, stops the app, replaces the database
and the documents, and starts the app again. Anything entered after that backup is lost, so take a
fresh backup first if you're unsure.

## Test the restore now and then

A backup you've never restored is a guess. Once a month: make a backup, restore it, open a
booked wedding and download one of its PDFs.

## Production (later)

When the CRM moves to the server, the same two things get backed up nightly with restic to
encrypted off-site storage, with 7 daily, 4 weekly and 12 monthly copies kept. The storage
credentials go in the server's `.env`, never in chat or in the repository. That is set up with
the production deploy, after Hanan's go-ahead.
