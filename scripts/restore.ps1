<#
.SYNOPSIS
  Restore a backup made by backup.ps1 / backup.sh (Windows PowerShell version of restore.sh).

.DESCRIPTION
  DESTRUCTIVE: replaces the current database contents and the uploaded files with the backup.
  Run from the repository root:
      .\scripts\restore.ps1 backups\20261005T101500Z

  Order: verify checksums -> stop the backend -> restore the database -> start the backend (which
  runs the migrations, so a backup older than the code is brought up to date) -> restore the files.
#>
param([Parameter(Mandatory = $true, Position = 0)][string]$BackupDir)
$ErrorActionPreference = "Stop"

function Invoke-Docker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw "docker $($args -join ' ') failed (exit code $LASTEXITCODE)" }
}

foreach ($f in "db.dump", "uploads.tar", "SHA256SUMS") {
    if (-not (Test-Path (Join-Path $BackupDir $f))) { throw "Not a complete backup: $BackupDir\$f is missing." }
}

Write-Host "Verifying checksums ..."
foreach ($line in Get-Content (Join-Path $BackupDir "SHA256SUMS")) {
    if (-not $line.Trim()) { continue }
    $expected, $name = $line -split "\s+", 2
    $name = $name.TrimStart("*").Trim()
    $actual = (Get-FileHash -Algorithm SHA256 -Path (Join-Path $BackupDir $name)).Hash.ToLower()
    if ($actual -ne $expected.ToLower()) { throw "Checksum mismatch for $name - the backup is damaged. Nothing was changed." }
    Write-Host "  ok  $name"
}

Write-Host ""
Write-Host "This will REPLACE the current database and uploaded files with the backup in:"
Write-Host "    $BackupDir"
$confirm = Read-Host "Type RESTORE to continue"
if ($confirm -ne "RESTORE") { Write-Host "Cancelled. Nothing was changed."; exit 1 }

Invoke-Docker compose stop backend

Invoke-Docker compose cp (Join-Path $BackupDir "db.dump") db:/tmp/cdr.dump
Invoke-Docker compose exec -T db sh -c 'pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists --no-owner /tmp/cdr.dump'
Invoke-Docker compose exec -T db rm -f /tmp/cdr.dump

Invoke-Docker compose start backend

Invoke-Docker compose cp (Join-Path $BackupDir "uploads.tar") backend:/tmp/uploads.tar
Invoke-Docker compose exec -T backend sh -c 'rm -rf /app/uploads/* && tar -C /app -xf /tmp/uploads.tar && chown -R cdr:cdr /app/uploads && rm -f /tmp/uploads.tar'

Write-Host ""
Write-Host "Restored from $BackupDir."
Write-Host "Check it: docker compose exec backend python scripts/verify_db_constraints.py"
