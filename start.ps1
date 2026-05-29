[CmdletBinding()]
param(
    [switch]$Cli,
    [switch]$Sync
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if ($Sync -or -not (Test-Path $venvPython)) {
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCommand) {
        throw "uv is required to create or refresh the virtual environment. Install uv, then run this script again."
    }

    & $uvCommand.Source sync
}

if (-not (Test-Path $venvPython)) {
    throw "Could not find .venv\Scripts\python.exe after setup."
}

$entryArgs = if ($Cli) { @("run.py") } else { @("-m", "app.main") }

& $venvPython @entryArgs
$exitCode = $LASTEXITCODE

if ($null -ne $exitCode) {
    exit $exitCode
}
