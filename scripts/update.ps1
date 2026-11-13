$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$Changes = & git status --porcelain
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect Git status.' }
if ($Changes) { throw 'Refusing to update with local changes. Commit, stash, or back them up first.' }
& git pull --ff-only
if ($LASTEXITCODE -ne 0) { throw 'Fast-forward update failed; inspect the Git output and resolve manually.' }
& (Join-Path $PSScriptRoot 'install.ps1')
