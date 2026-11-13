$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RunDirectory = Join-Path $Root '.aatm\run'
foreach ($Name in @('frontend', 'backend')) {
    $PidFile = Join-Path $RunDirectory "$Name.pid"
    if (-not (Test-Path $PidFile)) { Write-Host "$Name is not recorded as running."; continue }
    $ProcessId = [int](Get-Content $PidFile -Raw)
    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        & taskkill.exe /PID $ProcessId /T /F | Out-Null
        Write-Host "Stopped $Name (PID $ProcessId)."
    } else { Write-Host "$Name process (PID $ProcessId) was already stopped." }
    Remove-Item $PidFile -Force
}
