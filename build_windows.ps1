$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath ".\.build_venv\Scripts\python.exe")) {
    py -3.13 -m venv .build_venv
}

.\.build_venv\Scripts\python.exe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed with exit code $LASTEXITCODE" }
.\.build_venv\Scripts\python.exe -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "dependency installation failed with exit code $LASTEXITCODE" }
.\.build_venv\Scripts\python.exe -m PyInstaller --noconfirm .\StravaDashboardV2App.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

Write-Host ""
Write-Host "Windows application created at:"
Write-Host (Join-Path $PSScriptRoot "dist\StravaDashboard\StravaDashboard.exe")
