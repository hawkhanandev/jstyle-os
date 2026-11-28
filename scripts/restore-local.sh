#!/usr/bin/env bash
# Restore a backup made by backup-local.sh. This REPLACES the current local database and documents.
# Usage: scripts/restore-local.sh backups/jstyle-YYYYMMDD-HHMMSS
set -euo pipefail

src="${1:?Give the backup folder, e.g. backups/jstyle-20261128-101500}"
[ -f "$src/database.dump" ] && [ -f "$src/documents.tar.gz" ] || { echo "Not a backup folder: $src"; exit 1; }
( cd "$src" && sha256sum -c --quiet SHA256SUMS ) || { echo "Checksum mismatch, not restoring."; exit 1; }

read -r -p "This replaces the local database and documents with $src. Type RESTORE to continue: " answer
[ "$answer" = "RESTORE" ] || { echo "Cancelled."; exit 1; }

echo "Stopping the app containers..."
docker compose stop api worker web >/dev/null

echo "Restoring the database..."
docker compose exec -T postgres psql -U jstyle -d postgres -qc \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='jstyle' AND pid <> pg_backend_pid();" >/dev/null
docker compose exec -T postgres dropdb -U jstyle jstyle
docker compose exec -T postgres createdb -U jstyle jstyle
docker compose exec -T postgres pg_restore -U jstyle -d jstyle --no-owner < "$src/database.dump"

echo "Restoring documents..."
docker compose run --rm --no-deps -T --entrypoint sh api -c \
  "rm -rf /data/documents/* && tar -C /data/documents -xzf -" < "$src/documents.tar.gz"

docker compose start api worker web >/dev/null
echo "Restored from $src. Open http://localhost:3000 to check."
