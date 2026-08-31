$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Missing .venv. Run .\scripts\setup.ps1 first."
}

Push-Location $repositoryRoot
try {
    & $venvPython scripts\evaluate.py
    if ($LASTEXITCODE -ne 0) { throw "M3 evaluation failed." }
}
finally {
    Pop-Location
}
