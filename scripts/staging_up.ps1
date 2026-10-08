# Staged STAGING start (Windows PowerShell): the same stages as prod_up.ps1, for the rehearsal copy (docs/STAGING.md). Safe to re-run.
#   1. check the configuration        2. start the database and the backend as the database owner
#   3. create the restricted database role cdr_app and switch the backend to it
#   4. start the web server (HTTPS)
# Needs: .env.staging (python scripts/prod_setup.py --stack staging). Never touches the production stack: own project, volumes, secrets and ports.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path .env.staging)) { throw "No .env.staging. Run: python scripts/prod_setup.py --stack staging" }

if (Get-Command python -ErrorAction SilentlyContinue) { python scripts/check_production_config.py --env-file .env.staging }
else { docker run --rm -v "${PWD}:/work" -w /work python:3.12-slim python scripts/check_production_config.py --env-file .env.staging --no-certs }
if ($LASTEXITCODE -ne 0) { throw "Configuration check failed. Nothing was started." }

$c = @('-p', 'cdr-staging', '-f', 'docker-compose.prod.yml', '--env-file', '.env.staging')
function Get-EnvValue($name) { (Select-String -Path .env.staging -Pattern "^$name=(.*)$").Matches[0].Groups[1].Value.Trim() }
function Wait-Healthy($service) {
  for ($i = 0; $i -lt 40; $i++) {
    $id = docker compose @c ps -q $service
    if ($id) { $st = docker inspect --format '{{.State.Health.Status}}' $id; if ($st -eq 'healthy') { return } }
    Start-Sleep -Seconds 5
  }
  throw "$service did not become healthy. See: docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging logs $service"
}

New-Item -ItemType Directory -Force -Path backups\staging-status | Out-Null
Write-Host "1/4 Starting the database and the backend ..."
docker compose @c up -d --build db backend
Wait-Healthy 'backend'

Write-Host "2/4 Creating the restricted database role cdr_app ..."
docker compose @c cp database/roles/create_app_role.sql db:/tmp/create_app_role.sql
docker compose @c exec -T db sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -v app_password=$APP_DB_PASSWORD -f /tmp/create_app_role.sql'
docker compose @c exec -T db rm -f /tmp/create_app_role.sql

Write-Host "3/4 Switching the backend to the restricted role ..."
$appPw = Get-EnvValue 'APP_DB_PASSWORD'
$user = 'cdr_app'
(Get-Content .env.staging) -replace '^BACKEND_DATABASE_URL=.*$', "BACKEND_DATABASE_URL=postgresql://${user}:${appPw}@db:5432/climate_data_repository" | Set-Content .env.staging
docker compose @c up -d --force-recreate backend
Wait-Healthy 'backend'

Write-Host "4/4 Starting the web server ..."
docker compose @c up -d --build --force-recreate frontend
Wait-Healthy 'frontend'

$domain = Get-EnvValue 'CDR_DOMAIN'
Write-Host ""
Write-Host "Staging is up: https://localhost:8443   (open exactly this address; if the browser will not go past the certificate warning because production's HSTS is remembered for 'localhost', use https://127.0.0.1:8443)"
Write-Host "Create the staging administrator (no demonstration accounts exist here either):"
Write-Host "  docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging exec backend python scripts/create_admin.py --username <name> --full-name `"<Full Name>`" --email <address>"
