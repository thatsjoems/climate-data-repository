#!/usr/bin/env bash
# Offline images (Linux/macOS): pack the built images into ONE file on a machine with internet, load them on a machine without.
#   scripts/offline_bundle.sh save [--stack production|staging] [--out offline/cdr-images.tar]
#   scripts/offline_bundle.sh load [--stack production|staging] [--file offline/cdr-images.tar]
# `save` needs the stack's images to exist (run prod_up / staging_up once, with internet). `load` verifies the checksum, loads the images and
# tags them as the stack expects (<project>-backend, <project>-frontend). Then: scripts/prod_up.sh --offline  (or staging_up.sh --offline).
# The same file serves both stacks: the images are identical, only their names differ.
set -euo pipefail
cd "$(dirname "$0")/.."
MODE="${1:-}"; shift || true
STACK=production; FILE=offline/cdr-images.tar
while [ $# -gt 0 ]; do
  case "$1" in
    --stack) STACK="$2"; shift 2;;
    --out|--file) FILE="$2"; shift 2;;
    *) echo "Unknown option: $1"; exit 2;;
  esac
done
case "$STACK" in production) PROJECT=cdr-prod;; staging) PROJECT=cdr-staging;; *) echo "--stack must be production or staging"; exit 2;; esac
DB=postgres:16-alpine; NB=cdr-bundle-backend:latest; NF=cdr-bundle-frontend:latest
sha() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

case "$MODE" in
  save)
    for s in backend frontend; do
      docker image inspect "$PROJECT-$s" >/dev/null 2>&1 || { echo "Image $PROJECT-$s not found. Start the $STACK stack once with internet first (scripts/${STACK/production/prod}_up.sh)."; exit 1; }
    done
    docker image inspect "$DB" >/dev/null 2>&1 || docker pull "$DB"
    docker tag "$PROJECT-backend" "$NB"; docker tag "$PROJECT-frontend" "$NF"
    mkdir -p "$(dirname "$FILE")"
    echo "Saving images to $FILE (a few hundred MB, one to two minutes) ..."
    docker save -o "$FILE" "$NB" "$NF" "$DB"
    echo "$(sha "$FILE")  $(basename "$FILE")" > "$FILE.sha256"
    docker rmi "$NB" "$NF" >/dev/null 2>&1 || true
    echo "Done: $FILE ($(du -h "$FILE" | cut -f1)); checksum in $FILE.sha256"
    echo "Copy BOTH files to the offline machine (USB or the Bank's transfer route), into the project's offline/ folder."
    ;;
  load)
    [ -f "$FILE" ] || { echo "No bundle at $FILE. Copy it there or give --file <path>."; exit 1; }
    if [ -f "$FILE.sha256" ]; then
      [ "$(cut -d' ' -f1 "$FILE.sha256")" = "$(sha "$FILE")" ] || { echo "CHECKSUM MISMATCH: $FILE is damaged or changed. Copy it again. Nothing was loaded."; exit 1; }
      echo "checksum OK"
    else echo "WARNING: $FILE.sha256 is missing, the file cannot be verified."; fi
    docker load -i "$FILE"
    docker tag "$NB" "$PROJECT-backend"; docker tag "$NF" "$PROJECT-frontend"
    docker rmi "$NB" "$NF" >/dev/null 2>&1 || true
    echo "Images ready for $STACK: $PROJECT-backend, $PROJECT-frontend, $DB"
    ;;
  *) echo "Usage: $0 save|load [--stack production|staging] [--out|--file <path>]"; exit 2;;
esac
