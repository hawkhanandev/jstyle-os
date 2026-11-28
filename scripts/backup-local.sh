#!/usr/bin/env bash
# Back up the local Jstyle CRM: the database and every generated document (PDFs, signed contracts).
# Usage: scripts/backup-local.sh [backup-dir]      (default: ./backups)
# Run it from the folder that holds docker-compose.yml while `docker compose up` is running.
set -euo pipefail

dest="${1:-./backups}"
stamp="$(date +%Y%m%d-%H%M%S)"
out="$dest/jstyle-$stamp"
mkdir -p "$out"

echo "Backing up the database..."
docker compose exec -T postgres pg_dump -U jstyle -d jstyle --format=custom --no-owner \
  > "$out/database.dump"

echo "Backing up documents..."
docker compose exec -T api tar -C /data/documents -czf - . > "$out/documents.tar.gz"

( cd "$out" && sha256sum database.dump documents.tar.gz > SHA256SUMS )
echo "Backup written to $out"
