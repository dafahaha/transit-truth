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

if (Test-Path dist) { Remove-Item -Recurse -Force dist }
if (Test-Path build) { Remove-Item -Recurse -Force build }
Remove-Item -Recurse -Force backend\transit_truth.egg-info -ErrorAction SilentlyContinue

python -m build --outdir dist
if ($LASTEXITCODE -ne 0) { throw "python -m build failed" }

# Normalize sdist tarball timestamps (wheel is already reproducible via
# SOURCE_DATE_EPOCH).
$tar = Get-ChildItem dist -Filter *.tar.gz | Select-Object -First 1
python scripts\_normalize_sdist.py $tar.FullName
if ($LASTEXITCODE -ne 0) { throw "sdist normalization failed" }

python -m twine check dist/*
if ($LASTEXITCODE -ne 0) { throw "twine check failed" }

Write-Host ""
Write-Host "== Reproducible artifacts (SOURCE_DATE_EPOCH=$env:SOURCE_DATE_EPOCH) =="
Get-ChildItem dist -File | ForEach-Object {
    $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    Write-Host ($_.Name + "`t" + $_.Length + " bytes`t" + $h)
}
