$ErrorActionPreference = "Stop"
$VersionRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $VersionRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonPath)) {
    Write-Error "Environment not found. Run .\setup.ps1 first."
}

Set-Location -LiteralPath $VersionRoot
& $PythonPath launcher.py

