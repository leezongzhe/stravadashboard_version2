$ErrorActionPreference = "Stop"
$VersionRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvironmentPath = Join-Path $VersionRoot ".venv"
$PythonPath = Join-Path $EnvironmentPath "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonPath)) {
    py -3 -m venv $EnvironmentPath
}

& $PythonPath -m pip install --upgrade pip
& $PythonPath -m pip install -r (Join-Path $VersionRoot "requirements.txt")

Write-Output "Setup complete."
Write-Output "Run: .\.venv\Scripts\python.exe launcher.py"
