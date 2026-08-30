$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Missing .venv. Run .\scripts\setup.ps1 first."
}

Push-Location $repositoryRoot
try {
    & $venvPython -m ruff check backend
    if ($LASTEXITCODE -ne 0) { throw "Backend lint failed." }

    & $venvPython -m mypy backend/app backend/tests
    if ($LASTEXITCODE -ne 0) { throw "Backend type check failed." }

    & $venvPython -m pytest backend/tests
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }

    & $venvPython -m app.schemas check
    if ($LASTEXITCODE -ne 0) { throw "Schema drift check failed." }

    & npm --prefix frontend run lint
    if ($LASTEXITCODE -ne 0) { throw "Frontend lint failed." }

    & npm --prefix frontend run typecheck
    if ($LASTEXITCODE -ne 0) { throw "Frontend type check failed." }

    & npm --prefix frontend run test
    if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }

    & npm --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
}
finally {
    Pop-Location
}

Write-Output "M2 verification passed."
