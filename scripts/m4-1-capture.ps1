$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$verificationDatabase = Join-Path $repositoryRoot "results\.pytest-m4-1-capture-regbridge.sqlite3"
$apiProcess = $null
$frontendProcess = $null

function Wait-For-Http($Url) {
    $deadline = (Get-Date).AddSeconds(60)
    do {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
            return
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $Url"
}

try {
    if (Test-Path -LiteralPath $verificationDatabase) {
        Remove-Item -LiteralPath $verificationDatabase -Force
    }
    $env:REG_BRIDGE_DATABASE_PATH = $verificationDatabase
    $env:LLM_MODE = "fixture"
    Remove-Item Env:\LLM_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:\LLM_BASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:\LLM_MODEL -ErrorAction SilentlyContinue

    $apiProcess = Start-Process -FilePath $venvPython `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
        -WorkingDirectory (Join-Path $repositoryRoot "backend") `
        -WindowStyle Hidden `
        -PassThru
    Wait-For-Http "http://127.0.0.1:8000/health"

    $npmCommand = (Get-Command npm.cmd).Source
    $frontendProcess = Start-Process -FilePath $npmCommand `
        -ArgumentList "--prefix", "frontend", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173" `
        -WorkingDirectory $repositoryRoot `
        -WindowStyle Hidden `
        -PassThru
    Wait-For-Http "http://127.0.0.1:5173"

    Push-Location $repositoryRoot
    try {
        & npm --prefix frontend run capture:m4-1
        if ($LASTEXITCODE -ne 0) { throw "M4.1 screenshot capture failed." }
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($frontendProcess -ne $null -and -not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force
    }
    if ($apiProcess -ne $null -and -not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force
    }
    if (Test-Path -LiteralPath $verificationDatabase) {
        Remove-Item -LiteralPath $verificationDatabase -Force
    }
    Remove-Item Env:\REG_BRIDGE_DATABASE_PATH -ErrorAction SilentlyContinue
}

Write-Output "M4.1 screenshots captured under paper/figures/m4-1."
