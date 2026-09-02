param(
    [switch]$SkipBrowser
)
$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$verificationDatabase = Join-Path $repositoryRoot "results\.pytest-m4-verify-regbridge.sqlite3"
$frontendTestResults = Join-Path $repositoryRoot "frontend\test-results"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Missing .venv. Run .\scripts\setup.ps1 first."
}

Push-Location $repositoryRoot
try {
    if (Test-Path -LiteralPath $verificationDatabase) {
        Remove-Item -LiteralPath $verificationDatabase -Force
    }
    $env:REG_BRIDGE_DATABASE_PATH = $verificationDatabase

    & $venvPython -m ruff check backend
    if ($LASTEXITCODE -ne 0) { throw "Backend lint failed." }

    & $venvPython -m mypy backend/app backend/tests
    if ($LASTEXITCODE -ne 0) { throw "Backend type check failed." }

    & $venvPython -m pytest backend/tests
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }

    & $venvPython -m app.schemas check
    if ($LASTEXITCODE -ne 0) { throw "Schema drift check failed." }

    Push-Location (Join-Path $repositoryRoot "backend")
    try {
        & $venvPython -m app.presentation.verify
        if ($LASTEXITCODE -ne 0) { throw "M4 presentation verification failed." }
    }
    finally {
        Pop-Location
    }

    & npm --prefix frontend run lint
    if ($LASTEXITCODE -ne 0) { throw "Frontend lint failed." }

    & npm --prefix frontend run typecheck
    if ($LASTEXITCODE -ne 0) { throw "Frontend type check failed." }

    & npm --prefix frontend run test
    if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }

    & npm --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }

    if (-not $SkipBrowser) {
        & npm --prefix frontend run test:e2e
        if ($LASTEXITCODE -ne 0) { throw "Frontend E2E tests failed." }
    }
}
finally {
    if (Test-Path -LiteralPath $verificationDatabase) {
        Remove-Item -LiteralPath $verificationDatabase -Force
    }
    if (Test-Path -LiteralPath $frontendTestResults) {
        Remove-Item -LiteralPath $frontendTestResults -Recurse -Force
    }
    Remove-Item Env:\REG_BRIDGE_DATABASE_PATH -ErrorAction SilentlyContinue
    Pop-Location
}

Write-Output "M4 verification passed."
