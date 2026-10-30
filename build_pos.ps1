param(
    [string]$Version = "1.2.13"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot "venv\Scripts\python.exe"
$sevenZip = "C:\Program Files\7-Zip\7z.exe"
$sfxModule = "C:\Program Files\7-Zip\7z.sfx"
$releaseDirectory = Join-Path (Split-Path -Parent (Split-Path -Parent $projectRoot)) "storage\app\pos-python-releases"
$packageName = "PopCentral-POS-UAT-$Version-setup.exe"
$distDirectory = Join-Path $projectRoot "dist"

if (-not (Test-Path $python)) {
    throw "Python POS virtual environment was not found: $python"
}
if (-not (Test-Path $sevenZip)) {
    throw "7-Zip was not found: $sevenZip"
}
if (-not (Test-Path $sfxModule)) {
    throw "7-Zip SFX module was not found: $sfxModule"
}

Push-Location $projectRoot
try {
    & $python -m PyInstaller --noconfirm --clean --onedir --windowed --icon="assets\icon.ico" --name "PopCentral POS" --add-data "assets;assets" --add-data "pos.db;." "main.py"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    Push-Location $distDirectory
    try {
        & $sevenZip a "-sfx$sfxModule" $packageName "PopCentral POS\*"
        if ($LASTEXITCODE -ne 0) {
            throw "7-Zip packaging failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    New-Item -ItemType Directory -Force -Path $releaseDirectory | Out-Null
    Move-Item -Force (Join-Path $distDirectory $packageName) (Join-Path $releaseDirectory $packageName)
    Write-Output "Created $(Join-Path $releaseDirectory $packageName)"
}
finally {
    Pop-Location
}

