#!/usr/bin/env bash
# Back up the CDR database AND the uploaded submission files.
#
# Run from the repository root (the folder that holds docker-compose.yml) while the stack is up:
#     scripts/backup.sh [output-folder]        # default output folder: ./backups
#
# Each run creates backups/<UTC timestamp>/ containing:
#     db.dump       PostgreSQL dump (custom format: compressed, restorable with pg_restore)
#     uploads.tar   the uploaded Excel files (the database stores only their paths)
#     SHA256SUMS    checksums, verified automatically by restore.sh
#     MANIFEST.txt  when it was taken and which schema revision the database was at
#
# The two parts must come from the same moment: the database rows point at the uploaded
# files, so restoring one without the other leaves submissions whose file is missing.
# This script never deletes old backups - manage retention yourself (see docs/DATABASE_OPERATIONS.md).
set -euo pipefail

OUT_ROOT="${1:-backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$OUT_ROOT/$STAMP"
mkdir -p "$OUT"
echo "Backing up to $OUT ..."

# The dump is written INSIDE the container and copied out with `docker compose cp`; piping
# binary data through a host shell can corrupt it (notably in Windows PowerShell).
docker compose exec -T db sh -c 'pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc -f /tmp/cdr.dump'
# Cheap proof the dump is readable, before we trust it.
docker compose exec -T db sh -c 'pg_restore --list /tmp/cdr.dump > /dev/null'
docker compose cp db:/tmp/cdr.dump "$OUT/db.dump"
docker compose exec -T db rm -f /tmp/cdr.dump

docker compose exec -T backend tar -C /app -cf /tmp/uploads.tar uploads
docker compose cp backend:/tmp/uploads.tar "$OUT/uploads.tar"
docker compose exec -T backend rm -f /tmp/uploads.tar

( cd "$OUT" && sha256sum db.dump uploads.tar > SHA256SUMS )

REVISION="$(docker compose exec -T backend sh -c 'cd /app && python -m alembic current 2>/dev/null' | tr -d '\r' | tail -n 1 || true)"
{
  echo "CDR backup"
  echo "taken (UTC):     $STAMP"
  echo "schema revision: ${REVISION:-unknown}"
  echo "files:"
  ls -l "$OUT" | sed 's/^/  /'
} > "$OUT/MANIFEST.txt"

echo "Done. Verify it can be restored on a TEST copy before you rely on it (docs/DATABASE_OPERATIONS.md)."
echo "Copy $OUT somewhere OFF this machine - a backup on the same disk does not survive the disk."
