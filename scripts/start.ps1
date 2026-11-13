$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$Vite = Join-Path $Root 'web\node_modules\vite\bin\vite.js'
if (-not (Test-Path $VenvPython) -or -not (Test-Path $Vite)) { throw 'Dependencies are missing. Run scripts\install.ps1 first.' }

New-Item -ItemType Directory -Force -Path '.aatm\logs', '.aatm\run' | Out-Null
$PreviousPythonPath = $env:PYTHONPATH
$BackendPythonPath = Join-Path $Root 'backend'
$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($PreviousPythonPath)) { $BackendPythonPath } else { $BackendPythonPath + [IO.Path]::PathSeparator + $PreviousPythonPath }
try {
    $RuntimeSettings = @(& $VenvPython -c "from app.core.config import settings; print(settings.host); print(settings.port)")
    $SettingsExitCode = $LASTEXITCODE
} finally {
    if ($null -eq $PreviousPythonPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue }
    else { $env:PYTHONPATH = $PreviousPythonPath }
}
if ($SettingsExitCode -ne 0 -or $RuntimeSettings.Count -lt 2) { throw 'Could not load runtime settings.' }
$HostAddress = if ($env:HOST) { $env:HOST } else { [string]$RuntimeSettings[0] }
$Port = if ($env:PORT) { $env:PORT } else { [string]$RuntimeSettings[1] }
$UiHost = if ($env:AATM_UI_HOST) { $env:AATM_UI_HOST } else { '127.0.0.1' }
$UiPort = if ($env:AATM_UI_PORT) { $env:AATM_UI_PORT } else { '5173' }

foreach ($Name in @('backend', 'frontend')) {
    $PidFile = Join-Path $Root ".aatm\run\$Name.pid"
    if (Test-Path $PidFile) {
        $ExistingId = [int](Get-Content $PidFile -Raw)
        if (Get-Process -Id $ExistingId -ErrorAction SilentlyContinue) { Write-Host "$Name already running (PID $ExistingId)."; continue }
        Remove-Item $PidFile -Force
    }

    if ($Name -eq 'backend') {
        $Process = Start-Process -FilePath $VenvPython -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend', '--host', $HostAddress, '--port', $Port) -WorkingDirectory $Root -PassThru -RedirectStandardOutput (Join-Path $Root '.aatm\logs\backend.log') -RedirectStandardError (Join-Path $Root '.aatm\logs\backend-error.log')
    } else {
        $PreviousApiTarget = $env:AATM_API_TARGET
        $env:AATM_API_TARGET = "http://127.0.0.1:$Port"
        try {
            $Process = Start-Process -FilePath 'node.exe' -ArgumentList @($Vite, '--host', $UiHost, '--port', $UiPort) -WorkingDirectory (Join-Path $Root 'web') -PassThru -RedirectStandardOutput (Join-Path $Root '.aatm\logs\frontend.log') -RedirectStandardError (Join-Path $Root '.aatm\logs\frontend-error.log')
        } finally {
            if ($null -eq $PreviousApiTarget) { Remove-Item Env:AATM_API_TARGET -ErrorAction SilentlyContinue }
            else { $env:AATM_API_TARGET = $PreviousApiTarget }
        }
    }
    Set-Content -Path $PidFile -Value $Process.Id -NoNewline
    Write-Host "Started $Name (PID $($Process.Id))."
}

Write-Host "AATM UI:  http://${UiHost}:${UiPort}"
Write-Host "AATM API: http://${HostAddress}:${Port}/api/v1/health"
Write-Host 'Stop with: scripts\stop.ps1'
