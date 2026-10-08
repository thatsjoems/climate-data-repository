#!/usr/bin/env bash
# Staged STAGING start (Linux/macOS): the same four stages as prod_up.sh, for the rehearsal copy (docs/STAGING.md). Safe to re-run. Never touches production.
# check, start db + backend as owner, create the restricted role cdr_app and switch to it, start the web server.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env.staging ] || { echo "No .env.staging. Run: python3 scripts/prod_setup.py --stack staging"; exit 1; }

if command -v python3 >/dev/null 2>&1; then python3 scripts/check_production_config.py --env-file .env.staging
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
docker compose "${C[@]}" up -d --build db backend
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
docker compose "${C[@]}" up -d --build --force-recreate frontend
wait_healthy frontend

echo; echo "Staging is up: https://localhost:8443   (open exactly this address; if the browser will not go past the certificate warning because production's HSTS is remembered for 'localhost', use https://127.0.0.1:8443)"
echo "Create the staging administrator (no demonstration accounts exist here either):"
echo '  docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging exec backend python scripts/create_admin.py --username <name> --full-name "<Full Name>" --email <address>'
