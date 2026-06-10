$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AddonSource = Join-Path $ProjectRoot "blender_addon\pmx2xps_renamer"
$DistDir = Join-Path $ProjectRoot "dist"
$ZipPath = Join-Path $DistDir "pmx2xps_renamer.zip"

if (-not (Test-Path $AddonSource)) {
    throw "Addon source not found: $AddonSource"
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

Compress-Archive -Path $AddonSource -DestinationPath $ZipPath -Force
Write-Host "Created $ZipPath"
