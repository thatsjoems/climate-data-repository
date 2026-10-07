#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh.
#
# DESTRUCTIVE: replaces the current database contents and the uploaded files with the backup.
# Run from the repository root:
#     scripts/restore.sh backups/20261005T101500Z
#
# Order: verify checksums -> stop the backend -> restore the database -> start the backend
# (which runs the migrations, so a backup older than the code is brought up to date) ->
# restore the uploaded files.
set -euo pipefail

DIR="${1:?Usage: scripts/restore.sh <backup-folder>   e.g. scripts/restore.sh backups/20261005T101500Z}"
for f in db.dump uploads.tar SHA256SUMS; do
  [ -f "$DIR/$f" ] || { echo "Not a complete backup: $DIR/$f is missing."; exit 1; }
done

echo "Verifying checksums ..."
( cd "$DIR" && sha256sum -c SHA256SUMS )

echo
echo "This will REPLACE the current database and uploaded files with the backup in:"
echo "    $DIR"
read -r -p "Type RESTORE to continue: " CONFIRM
[ "$CONFIRM" = "RESTORE" ] || { echo "Cancelled. Nothing was changed."; exit 1; }

docker compose stop backend

docker compose cp "$DIR/db.dump" db:/tmp/cdr.dump
docker compose exec -T db sh -c 'pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists --no-owner /tmp/cdr.dump'
docker compose exec -T db rm -f /tmp/cdr.dump

docker compose start backend

docker compose cp "$DIR/uploads.tar" backend:/tmp/uploads.tar
docker compose exec -T backend sh -c 'rm -rf /app/uploads/* && tar -C /app -xf /tmp/uploads.tar && chown -R cdr:cdr /app/uploads && rm -f /tmp/uploads.tar'

echo
echo "Restored from $DIR."
echo "Check it: docker compose exec backend python scripts/verify_db_constraints.py"
