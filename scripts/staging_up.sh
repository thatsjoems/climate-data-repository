#!/usr/bin/env bash
# Staged STAGING start (Linux/macOS): the same four stages as prod_up.sh, for the rehearsal copy (docs/STAGING.md). Safe to re-run. Never touches production.
# check, start db + backend as owner, create the restricted role cdr_app and switch to it, start the web server.
set -euo pipefail
cd "$(dirname "$0")/.."
# --offline: no internet needed. Loads the images from offline/cdr-images.tar (made by scripts/offline_bundle.sh save) and never builds or pulls.
BUILD=--build; BUNDLE=offline/cdr-images.tar
while [ $# -gt 0 ]; do case "$1" in
  --offline) BUILD=--no-build; shift;;
  --bundle) BUNDLE="$2"; shift 2;;
  *) echo "Unknown option: $1 (use --offline [--bundle <file>])"; exit 2;; esac; done
[ -f .env.staging ] || { echo "No .env.staging. Run: python3 scripts/prod_setup.py --stack staging"; exit 1; }
[ "$BUILD" = "--no-build" ] && "$(dirname "$0")/offline_bundle.sh" load --stack staging --file "$BUNDLE"

if command -v python3 >/dev/null 2>&1; then python3 scripts/check_production_config.py --env-file .env.staging
elif [ "$BUILD" = "--no-build" ]; then echo "NOTE: python3 not found; configuration check skipped (offline, no image to run it in)."
else docker run --rm -v "$PWD:/work" -w /work python:3.12-slim python scripts/check_production_config.py --env-file .env.staging --no-certs; fi

C=(-p cdr-staging -f docker-compose.prod.yml --env-file .env.staging)
env_value() { grep -E "^$1=" .env.staging | head -1 | cut -d= -f2-; }
wait_healthy() {
  for _ in $(seq 1 40); do
    id=$(docker compose "${C[@]}" ps -q "$1")
    if [ -n "$id" ] && [ "$(docker inspect --format '{{.State.Health.Status}}' "$id")" = "healthy" ]; then return 0; fi
    sleep 5
  done
  echo "$1 did not become healthy. See: docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging logs $1"; exit 1
}

mkdir -p backups/staging-status
echo "1/4 Starting the database and the backend ..."
docker compose "${C[@]}" up -d db
wait_healthy db
# A brand-new database (a first start, after `down -v`, or a restore onto a new machine) has no cdr_app role yet, while this file may already point the backend
# at it from an earlier run, and the backend would never become healthy. Only when the role is missing, start the backend as the database owner again.
role_there=$(echo "select 1 from pg_roles where rolname='cdr_app'" | docker compose "${C[@]}" exec -T db sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -tA' || true)
if ! echo "$role_there" | grep -q 1; then
  echo "    (a new database: the backend starts as the database owner until cdr_app exists)"
  sed -i.bak "s|^BACKEND_DATABASE_URL=.*|BACKEND_DATABASE_URL=postgresql://$(env_value POSTGRES_USER):$(env_value POSTGRES_PASSWORD)@db:5432/climate_data_repository|" .env.staging && rm -f .env.staging.bak
fi
docker compose "${C[@]}" up -d $BUILD backend
wait_healthy backend

echo "2/4 Creating the restricted database role cdr_app ..."
docker compose "${C[@]}" cp database/roles/create_app_role.sql db:/tmp/create_app_role.sql
docker compose "${C[@]}" exec -T db sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -v app_password=$APP_DB_PASSWORD -f /tmp/create_app_role.sql'
docker compose "${C[@]}" exec -T db rm -f /tmp/create_app_role.sql

echo "3/4 Switching the backend to the restricted role ..."
APP_PW=$(env_value APP_DB_PASSWORD)
sed -i.bak "s|^BACKEND_DATABASE_URL=.*|BACKEND_DATABASE_URL=postgresql://cdr_app:${APP_PW}@db:5432/climate_data_repository|" .env.staging && rm -f .env.staging.bak
docker compose "${C[@]}" up -d --force-recreate backend
wait_healthy backend

echo "4/4 Starting the web server ..."
docker compose "${C[@]}" up -d $BUILD --force-recreate frontend
wait_healthy frontend

echo; echo "Staging is up: https://localhost:8443   (open exactly this address; if the browser will not go past the certificate warning because production's HSTS is remembered for 'localhost', use https://127.0.0.1:8443)"
echo "Create the staging administrator (no demonstration accounts exist here either):"
echo '  docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging exec backend python scripts/create_admin.py --username <name> --full-name "<Full Name>" --email <address>'
