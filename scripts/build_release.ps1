#Requires -Version 5.1
# Reproducible release build for transit-truth.
#
# WHY: `python -m build` alone is NOT reproducible on this platform — the
# wheel honors SOURCE_DATE_EPOCH, but the sdist tar.gz stamps every member and
# the gzip header with the actual wall-clock build time, so the SHA256 drifts
# between rebuilds. Run this script (never bare `python -m build`) when
# producing artifacts meant for PyPI / hashing; see docs/PUBLISHING.md.
#
# Output: dist/transit_truth-0.5.9-{py3-none-any.whl,tar.gz} + twine check.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

# 0.5.9 release date, 00:00 UTC — the fixed build timestamp.
$env:SOURCE_DATE_EPOCH = "1792368000"

# --- Interpreter resolution ---------------------------------------------
# Prefer $env:PYTHON (explicit override), otherwise `python` from PATH.
# PATH ordering is fragile: anaconda base 3.11 lacks build/twine, so verify
# the chosen interpreter can import them and install if missing.
$py = if ($env:PYTHON) { $env:PYTHON } else { "python" }
Write-Host "Using interpreter: $py"
# Probe build/twine availability. Under EAP=Stop a nonzero exit of the probe
# (ImportError traceback on stderr) raises a terminating NativeCommandError
# BEFORE $LASTEXITCODE is read, which would make the auto-install branch
# dead. Temporarily relax EAP and swallow stderr, then decide on exit code.
$prevEAP = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    & $py -c "import build, twine" 2>&1 | Out-Null
    $probeExit = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $prevEAP
}
if ($probeExit -ne 0) {
    Write-Host "build/twine missing in $py — installing them now..."
    & $py -m pip install --upgrade build twine
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install build/twine into '$py'. Fix with: `"$py`" -m pip install build twine (or set `$env:PYTHON` to the right interpreter)."
    }
}

if (Test-Path dist) { Remove-Item -Recurse -Force dist }
if (Test-Path build) { Remove-Item -Recurse -Force build }
Remove-Item -Recurse -Force backend\transit_truth.egg-info -ErrorAction SilentlyContinue

& $py -m build --outdir dist
if ($LASTEXITCODE -ne 0) { throw "python -m build failed" }

# Normalize sdist tarball timestamps (wheel is already reproducible via
# SOURCE_DATE_EPOCH).
$tar = Get-ChildItem dist -Filter *.tar.gz | Select-Object -First 1
& $py scripts\_normalize_sdist.py $tar.FullName
if ($LASTEXITCODE -ne 0) { throw "sdist normalization failed" }

# Strip the legacy online-platform module from the wheel (setuptools cannot
# exclude a single module of a shipped package; the source checkout keeps it).
$whl = Get-ChildItem dist -Filter *.whl | Select-Object -First 1
& $py scripts\_strip_wheel_legacy.py $whl.FullName
if ($LASTEXITCODE -ne 0) { throw "wheel legacy-strip failed" }

& $py -m twine check dist/*
if ($LASTEXITCODE -ne 0) { throw "twine check failed" }

Write-Host ""
Write-Host "== Reproducible artifacts (SOURCE_DATE_EPOCH=$env:SOURCE_DATE_EPOCH) =="
Get-ChildItem dist -File | ForEach-Object {
    $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    Write-Host ($_.Name + "`t" + $_.Length + " bytes`t" + $h)
}
