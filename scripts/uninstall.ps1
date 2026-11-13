$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
& (Join-Path $PSScriptRoot 'stop.ps1')
foreach ($Path in @('.venv', 'web\node_modules', 'web\dist')) {
    if (Test-Path $Path) { Remove-Item -LiteralPath $Path -Recurse -Force }
}
Write-Host 'Removed generated Python/Node environments and frontend build output.'
Write-Host 'Preserved source, Git history, .env, and .aatm user data/database/logs.'
Write-Host 'Delete preserved user data manually only after a verified backup.'
