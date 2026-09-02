$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$env:PYTHONPATH = Join-Path $root "backend"
$env:LLM_MODE = "fixture"
Remove-Item Env:LLM_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:LLM_BASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:LLM_MODEL -ErrorAction SilentlyContinue

Push-Location $root
try {
    & $python -m app.product.verify
    if ($LASTEXITCODE -ne 0) { throw "M4.1 product verification failed." }
    & $python scripts\generate_m4_1_dossier.py --check
    if ($LASTEXITCODE -ne 0) { throw "Composite dossier verification failed." }
    & $python -m ruff check backend scripts\generate_m4_1_dossier.py
    if ($LASTEXITCODE -ne 0) { throw "Backend lint failed." }
    & $python -m mypy backend\app backend\tests
    if ($LASTEXITCODE -ne 0) { throw "Backend type checking failed." }
    & $python -m pytest backend\tests
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }
    & $python -m app.schemas check
    if ($LASTEXITCODE -ne 0) { throw "Schema drift check failed." }
    npm --prefix frontend run lint
    if ($LASTEXITCODE -ne 0) { throw "Frontend lint failed." }
    npm --prefix frontend run typecheck
    if ($LASTEXITCODE -ne 0) { throw "Frontend type checking failed." }
    npm --prefix frontend run test
    if ($LASTEXITCODE -ne 0) { throw "Frontend unit tests failed." }
    npm --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }
    npm --prefix frontend run test:e2e
    if ($LASTEXITCODE -ne 0) { throw "Frontend E2E/accessibility tests failed." }
    & $python -m app.product.verify
    if ($LASTEXITCODE -ne 0) { throw "Post-test protected-artifact verification failed." }
} finally {
    Pop-Location
}
