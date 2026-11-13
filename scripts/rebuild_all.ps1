# One pass over all three stacks (Windows PowerShell): build the new images, test them, and only then move staging and production onto them.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\rebuild_all.ps1
#
# What it does, in this order, and stops at the first failure (nothing later runs):
#   DEV         1. builds the backend image (tries again, up to 3 times, when the network fails)
#               2. runs the tests with the code of this folder
#               3. times the two Excel readers on a real file and compares every cell (when loans_100000.xlsx is found)
#               4. starts the development stack on the new image
#   -- asks you to type YES before touching staging and production --
#   STAGING     5. staging_up.ps1 (only when .env.staging exists)
#   PRODUCTION  6. a backup first (python scripts/prod_ops.py backup), then prod_up.ps1 (tries again, up to 3 times), then checks
#
# Safe to run again: every step can be repeated. It never deletes a volume (no `down -v`), so no account or data is removed.
# Options:  -SkipDev  -SkipStaging  -SkipProduction  -QuickTests (only the tests about uploads and the Excel reader)
#           -BenchFile <path to loans_100000.xlsx>  -FullBench (the bench also checks the whole file with each reader: several minutes)  -Yes (do not ask)
param(
  [switch]$SkipDev, [switch]$SkipStaging, [switch]$SkipProduction,
  [switch]$QuickTests, [switch]$FullBench, [switch]$Yes,
  [string]$BenchFile = ""
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$root = (Get-Location).Path
$started = Get-Date

function Say([string]$text, [string]$color = 'Cyan') { Write-Host $text -ForegroundColor $color }

function Invoke-Retry([string]$Name, [int]$Attempts, [scriptblock]$Block) {
  for ($i = 1; $i -le $Attempts; $i++) {
    & $Block
    if ($LASTEXITCODE -eq 0) { return }
    Say "  $Name failed (attempt $i of $Attempts)." 'Yellow'
    if ($i -lt $Attempts) { Say "  Waiting 20 seconds and trying again (a network problem often passes) ..." 'Yellow'; Start-Sleep -Seconds 20 }
  }
  throw "$Name failed after $Attempts attempts. Nothing after this step was run."
}

function Invoke-Once([string]$Name, [scriptblock]$Block) {
  & $Block
  if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit code $LASTEXITCODE). Nothing after this step was run." }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker is not available. Start Docker Desktop and run this again." }
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker is not running. Start Docker Desktop, wait until it says it is running, and run this again." }

# ------------------------------------------------------------------ DEV
if (-not $SkipDev) {
  Say "`n=== DEV 1/4: building the backend image ===" 'Green'
  Invoke-Retry "docker compose build backend" 3 { docker compose build backend }

  Say "`n=== DEV 2/4: tests, with the code of this folder ===" 'Green'
  $pytestArgs = @('pytest', '-q', '-p', 'no:cacheprovider')
  if ($QuickTests) {
    $pytestArgs += @('tests/test_excel_reader.py', 'tests/test_upload_and_workflow.py', 'tests/test_csv_upload.py', 'tests/test_date_rules.py', 'tests/test_official_template.py', 'tests/test_boundaries.py')
    Say "  (quick set; run without -QuickTests for the whole suite, about 9 minutes)"
  } else { Say "  (the whole suite, about 9 minutes)" }
  Invoke-Once "the tests" { docker compose run --rm --no-deps -e PYTHONDONTWRITEBYTECODE=1 -v "${root}\backend:/app" backend @pytestArgs }

  Say "`n=== DEV 3/4: the two Excel readers on a real file ===" 'Green'
  if ($BenchFile -eq "") {
    foreach ($candidate in @("$root\loans_100000.xlsx", "$HOME\Downloads\loans_100000.xlsx", "$HOME\Desktop\loans_100000.xlsx")) {
      if (Test-Path $candidate) { $BenchFile = $candidate; break }
    }
  }
  if ($BenchFile -ne "" -and (Test-Path $BenchFile)) {
    $benchDir = Split-Path -Parent (Resolve-Path $BenchFile).Path
    $benchName = Split-Path -Leaf $BenchFile
    $benchArgs = @('python', 'scripts/bench_excel_read.py', "/bench/$benchName")
    if ($FullBench) { $benchArgs += '--full' }
    Invoke-Once "the Excel reader comparison" { docker compose run --rm --no-deps -e PYTHONDONTWRITEBYTECODE=1 -v "${root}\backend:/app" -v "${benchDir}:/bench:ro" backend @benchArgs }
  } else {
    Say "  loans_100000.xlsx was not found (use -BenchFile <path>); skipping the timing. The tests above already compare the readers on generated files." 'Yellow'
  }

  Say "`n=== DEV 4/4: starting the development stack on the new image ===" 'Green'
  Invoke-Retry "docker compose up -d --build" 3 { docker compose up -d --build }
  Start-Sleep -Seconds 25
  docker compose ps
  Say "Dev is on the new code: http://localhost:5173" 'Green'
}

# ------------------------------------------------------------------ the gate
if (-not ($SkipStaging -and $SkipProduction)) {
  if (-not $Yes) {
    Say "`nDev is done. Staging and production are about to be rebuilt and restarted (about a minute or two of downtime each; no data or account is removed)." 'Yellow'
    $answer = Read-Host "Type YES to continue (anything else stops here)"
    if ($answer -ne 'YES') { Say "Stopped before staging and production. Dev is already updated." 'Yellow'; exit 0 }
  }
}

# ------------------------------------------------------------------ STAGING
if (-not $SkipStaging) {
  Say "`n=== STAGING ===" 'Green'
  if (Test-Path .env.staging) {
    Invoke-Retry "staging_up.ps1" 3 { powershell -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\staging_up.ps1" }
  } else {
    Say "  No .env.staging: staging is not set up on this machine, skipped." 'Yellow'
  }
}

# ------------------------------------------------------------------ PRODUCTION
if (-not $SkipProduction) {
  Say "`n=== PRODUCTION 1/3: a backup first ===" 'Green'
  Invoke-Once "the backup" { python scripts/prod_ops.py backup }

  Say "`n=== PRODUCTION 2/3: building and restarting ===" 'Green'
  Invoke-Retry "prod_up.ps1" 3 { powershell -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\prod_up.ps1" }

  Say "`n=== PRODUCTION 3/3: checks ===" 'Green'
  $p = @('-f', 'docker-compose.prod.yml', '--env-file', '.env.production')
  docker compose @p ps
  Say "-- the template in the image (expect yyyy\-mm\-dd):"
  docker compose @p exec backend python -c "import openpyxl; from app.services.template_generator import TEMPLATE_FILE as T; print(openpyxl.load_workbook(T)['Loan_Collateral_Data'].column_dimensions['H'].number_format)"
  Say "-- the fast Excel reader (expect: calamine OK, ['calamine', 'openpyxl']):"
  docker compose @p exec backend python -c "import python_calamine; from app.services.excel_reader import engines_for; print('calamine OK', engines_for(b'PK'))"
  Say "-- the accounts (expect admin, admin2, bot_analyst and Institution User):"
  docker compose @p exec db psql -U postgres -d climate_data_repository -tA -c "SELECT username, role FROM users ORDER BY role, username;"
  python scripts/check_production_config.py
  python scripts/prod_ops.py check
  python scripts/prod_ops.py status
}

$minutes = [math]::Round(((Get-Date) - $started).TotalMinutes, 1)
Say "`nFinished in $minutes minutes. If anything in the checks above looks wrong, copy it to the developer; nothing was deleted, and the backup made at the start is in backups\prod." 'Green'
Say "The way back for the Excel reader alone (no rebuild): add  EXCEL_READER=openpyxl  to .env.production, then  docker compose -f docker-compose.prod.yml --env-file .env.production up -d backend" 'Gray'
