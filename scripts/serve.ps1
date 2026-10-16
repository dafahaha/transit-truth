# Local one-click launcher for the TransitTruth web UI (Windows PowerShell).
# Defaults to loopback only; never passes --allow-public.
#
# Usage:
#   .\scripts\serve.ps1                # http://127.0.0.1:8766
#   .\scripts\serve.ps1 -Port 8800
#   .\scripts\serve.ps1 -Open          # auto-open browser
param(
    [string]$Listen = "127.0.0.1",
    [int]$Port = 8766,
    [switch]$Open,
    [switch]$AllowLocal
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location -Path (Join-Path $root "backend")

$cliArgs = @("serve", "--host", $Listen, "--port", $Port)
if ($Open) { $cliArgs += "--open" }
if ($AllowLocal) { $cliArgs += "--allow-local" }

# Prefer the repo venv if present; otherwise fall back to python on PATH.
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    & $venvPy -m app.cli @cliArgs
} else {
    python -m app.cli @cliArgs
}
