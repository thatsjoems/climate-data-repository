# Offline images (Windows PowerShell): pack the built images into ONE file on a machine with internet, load them on a machine without.
#   .\scripts\offline_bundle.ps1 save [-Stack production|staging] [-File offline\cdr-images.tar]
#   .\scripts\offline_bundle.ps1 load [-Stack production|staging] [-File offline\cdr-images.tar]
# Same file format as offline_bundle.sh (plain docker save), so a bundle made on one system loads on the other.
param(
  [Parameter(Mandatory = $true, Position = 0)][ValidateSet('save', 'load')][string]$Mode,
  [ValidateSet('production', 'staging')][string]$Stack = 'production',
  [string]$File = 'offline\cdr-images.tar'
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$project = if ($Stack -eq 'staging') { 'cdr-staging' } else { 'cdr-prod' }
$db = 'postgres:16-alpine'; $nb = 'cdr-bundle-backend:latest'; $nf = 'cdr-bundle-frontend:latest'
function Test-Image($n) { docker image inspect $n *> $null; return ($LASTEXITCODE -eq 0) }
function Run($what) { & $what; if ($LASTEXITCODE -ne 0) { throw "Command failed: $what" } }

if ($Mode -eq 'save') {
  foreach ($s in 'backend', 'frontend') {
    if (-not (Test-Image "$project-$s")) { throw "Image $project-$s not found. Start the $Stack stack once with internet first." }
  }
  if (-not (Test-Image $db)) { docker pull $db; if ($LASTEXITCODE -ne 0) { throw "Could not pull $db" } }
  docker tag "$project-backend" $nb; docker tag "$project-frontend" $nf
  New-Item -ItemType Directory -Force -Path (Split-Path $File) | Out-Null
  Write-Host "Saving images to $File (a few hundred MB, one to two minutes) ..."
  docker save -o $File $nb $nf $db
  if ($LASTEXITCODE -ne 0) { throw "docker save failed" }
  $h = (Get-FileHash -Algorithm SHA256 $File).Hash.ToLower()
  Set-Content -Path "$File.sha256" -Value "$h  $(Split-Path $File -Leaf)" -Encoding ASCII
  docker rmi $nb $nf *> $null
  Write-Host ("Done: {0} ({1:N0} MB); checksum in {0}.sha256" -f $File, ((Get-Item $File).Length / 1MB))
  Write-Host "Copy BOTH files to the offline machine, into the project's offline folder."
}
else {
  if (-not (Test-Path $File)) { throw "No bundle at $File. Copy it there or give -File <path>." }
  if (Test-Path "$File.sha256") {
    $want = ((Get-Content "$File.sha256" -Raw).Trim() -split '\s+')[0]
    if ($want -ne (Get-FileHash -Algorithm SHA256 $File).Hash.ToLower()) { throw "CHECKSUM MISMATCH: $File is damaged or changed. Copy it again. Nothing was loaded." }
    Write-Host "checksum OK"
  } else { Write-Host "WARNING: $File.sha256 is missing, the file cannot be verified." }
  docker load -i $File
  if ($LASTEXITCODE -ne 0) { throw "docker load failed" }
  docker tag $nb "$project-backend"; docker tag $nf "$project-frontend"
  docker rmi $nb $nf *> $null
  Write-Host "Images ready for ${Stack}: $project-backend, $project-frontend, $db"
}
