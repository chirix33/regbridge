param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPath = Join-Path $repositoryRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

& $Python -m venv $venvPath
if ($LASTEXITCODE -ne 0) { throw "Failed to create the Python virtual environment." }

& $venvPython -m pip install "pip==26.2.1"
if ($LASTEXITCODE -ne 0) { throw "Failed to update pip." }

& $venvPython -m pip install -r "$repositoryRoot\backend\requirements.lock"
if ($LASTEXITCODE -ne 0) { throw "Failed to install backend dependencies." }

& $venvPython -m pip install --no-deps --no-build-isolation -e "$repositoryRoot\backend"
if ($LASTEXITCODE -ne 0) { throw "Failed to install the backend package." }

& npm --prefix (Join-Path $repositoryRoot "frontend") ci --ignore-scripts --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw "Failed to install frontend dependencies." }

Push-Location $repositoryRoot
try {
    & $venvPython -m app.schemas export
    if ($LASTEXITCODE -ne 0) { throw "Failed to export JSON Schemas." }
}
finally {
    Pop-Location
}

Write-Output "RegBridge setup complete. Run .\scripts\check.ps1 to verify M3."
