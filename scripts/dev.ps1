$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Missing .venv. Run .\scripts\setup.ps1 first."
}

$apiJob = Start-Job -ScriptBlock {
    param($PythonPath, $WorkingDirectory)
    Set-Location $WorkingDirectory
    & $PythonPath -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
} -ArgumentList $venvPython, $repositoryRoot

try {
    Write-Output "RegBridge API: http://127.0.0.1:8000/docs"
    Write-Output "RegBridge UI:  http://127.0.0.1:5173"
    & npm --prefix (Join-Path $repositoryRoot "frontend") run dev
}
finally {
    Stop-Job -Job $apiJob -ErrorAction SilentlyContinue
    Receive-Job -Job $apiJob -ErrorAction SilentlyContinue
    Remove-Job -Job $apiJob -Force -ErrorAction SilentlyContinue
}

