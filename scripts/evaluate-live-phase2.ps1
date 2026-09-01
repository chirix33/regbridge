param(
    [switch]$Prepare,
    [string]$Execute
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Missing .venv. Run .\scripts\setup.ps1 first."
}
if (($Prepare -and $Execute) -or (-not $Prepare -and -not $Execute)) {
    throw "Specify exactly one of -Prepare or -Execute <generated-run-id>."
}

Push-Location $repositoryRoot
try {
    if ($Prepare) {
        & $venvPython -m app.evaluation.live_phase2 --prepare
    }
    else {
        & $venvPython -m app.evaluation.live_phase2 --execute $Execute
    }
    if ($LASTEXITCODE -ne 0) { throw "M3 live Phase 2 command failed." }
}
finally {
    Pop-Location
}
