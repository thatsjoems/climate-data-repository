<#
.SYNOPSIS
  Back up the CDR database AND the uploaded submission files (Windows PowerShell version of backup.sh).

.DESCRIPTION
  Run from the repository root (the folder that holds docker-compose.yml) while the stack is up:
      .\scripts\backup.ps1 [-OutDir backups]

  Creates <OutDir>\<UTC timestamp>\ containing db.dump (PostgreSQL custom-format dump),
  uploads.tar (the uploaded Excel files - the database stores only their paths), SHA256SUMS
  (checked automatically by restore.ps1) and MANIFEST.txt.

  The two parts must come from the same moment: database rows point at the uploaded files, so
  restoring one without the other leaves submissions whose file is missing. Old backups are never
  deleted by this script - manage retention yourself (docs/DATABASE_OPERATIONS.md).
#>
param([string]$OutDir = "backups")
$ErrorActionPreference = "Stop"

# PowerShell does not stop on a failing native command by itself; check the exit code every time.
function Invoke-Docker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw "docker $($args -join ' ') failed (exit code $LASTEXITCODE)" }
}

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd'T'HHmmss'Z'")
$out = Join-Path $OutDir $stamp
New-Item -ItemType Directory -Force -Path $out | Out-Null
Write-Host "Backing up to $out ..."

# The dump is written INSIDE the container and copied out with `docker compose cp`: piping binary
# data through PowerShell (a pipe or >) re-encodes it and corrupts the file.
Invoke-Docker compose exec -T db sh -c 'pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc -f /tmp/cdr.dump'
Invoke-Docker compose exec -T db sh -c 'pg_restore --list /tmp/cdr.dump > /dev/null'   # proves the dump is readable
Invoke-Docker compose cp db:/tmp/cdr.dump (Join-Path $out "db.dump")
Invoke-Docker compose exec -T db rm -f /tmp/cdr.dump

Invoke-Docker compose exec -T backend tar -C /app -cf /tmp/uploads.tar uploads
Invoke-Docker compose cp backend:/tmp/uploads.tar (Join-Path $out "uploads.tar")
Invoke-Docker compose exec -T backend rm -f /tmp/uploads.tar

# Same format as `sha256sum`, so backup.sh / restore.sh and the .ps1 versions can verify each other.
$sums = foreach ($name in "db.dump", "uploads.tar") {
    $h = Get-FileHash -Algorithm SHA256 -Path (Join-Path $out $name)
    "{0}  {1}" -f $h.Hash.ToLower(), $name
}
[System.IO.File]::WriteAllLines((Join-Path $out "SHA256SUMS"), [string[]]$sums)

$revision = "unknown"
try {
    $r = & docker compose exec -T backend sh -c 'cd /app && python -m alembic current 2>/dev/null'
    if ($LASTEXITCODE -eq 0 -and $r) { $revision = ($r | Select-Object -Last 1).ToString().Trim() }
} catch { }

$manifest = @(
    "CDR backup",
    "taken (UTC):     $stamp",
    "schema revision: $revision",
    "files:"
) + (Get-ChildItem $out | ForEach-Object { "  {0,12}  {1}" -f $_.Length, $_.Name })
[System.IO.File]::WriteAllLines((Join-Path $out "MANIFEST.txt"), [string[]]$manifest)

Write-Host "Done. Verify it can be restored on a TEST copy before you rely on it (docs/DATABASE_OPERATIONS.md)."
Write-Host "Copy $out somewhere OFF this machine - a backup on the same disk does not survive the disk."
