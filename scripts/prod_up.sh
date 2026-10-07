#!/usr/bin/env bash
# Staged production start (Linux/macOS). Safe to re-run. Same four stages as prod_up.ps1:
# check, start db + backend as owner, create the restricted role cdr_app and switch to it, start the web server.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env.production ] || { echo "No .env.production. Run: python3 scripts/prod_setup.py --domain <address>"; exit 1; }

if command -v python3 >/dev/null 2>&1; then python3 scripts/check_production_config.py
else docker run --rm -v "$PWD:/work" -w /work python:3.12-slim python scripts/check_production_config.py --no-certs; fi

C=(-f docker-compose.prod.yml --env-file .env.production)
env_value() { grep -E "^$1=" .env.production | head -1 | cut -d= -f2-; }
wait_healthy() {
  for _ in $(seq 1 40); do
    id=$(docker compose "${C[@]}" ps -q "$1")
    if [ -n "$id" ] && [ "$(docker inspect --format '{{.State.Health.Status}}' "$id")" = "healthy" ]; then return 0; fi
    sleep 5
  done
  echo "$1 did not become healthy. See: docker compose -f docker-compose.prod.yml --env-file .env.production logs $1"; exit 1
}

echo "1/4 Starting the database and the backend ..."
docker compose "${C[@]}" up -d --build db backend
wait_healthy backend

echo "2/4 Creating the restricted database role cdr_app ..."
docker compose "${C[@]}" cp database/roles/create_app_role.sql db:/tmp/create_app_role.sql
docker compose "${C[@]}" exec -T db sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -v app_password=$APP_DB_PASSWORD -f /tmp/create_app_role.sql'
docker compose "${C[@]}" exec -T db rm -f /tmp/create_app_role.sql

echo "3/4 Switching the backend to the restricted role ..."
APP_PW=$(env_value APP_DB_PASSWORD)
sed -i.bak "s|^BACKEND_DATABASE_URL=.*|BACKEND_DATABASE_URL=postgresql://cdr_app:${APP_PW}@db:5432/climate_data_repository|" .env.production && rm -f .env.production.bak
docker compose "${C[@]}" up -d --force-recreate backend
wait_healthy backend

echo "4/4 Starting the web server ..."
docker compose "${C[@]}" up -d --build frontend
wait_healthy frontend

echo; echo "Production is up: https://$(env_value CDR_DOMAIN)"
echo "Create the first administrator (no demonstration accounts exist in production):"
echo '  docker compose -f docker-compose.prod.yml --env-file .env.production exec backend python scripts/create_admin.py --username <name> --full-name "<Full Name>" --email <address>'
