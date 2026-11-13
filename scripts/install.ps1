$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root

$PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($PythonLauncher) {
    $PythonVersion = (& py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
    $VersionParts = $PythonVersion.Split('.')
    if ([int]$VersionParts[0] -lt 3 -or ([int]$VersionParts[0] -eq 3 -and [int]$VersionParts[1] -lt 11)) {
        throw "Python 3.11 or newer is required (found $PythonVersion)."
    }
    if (-not (Test-Path '.venv')) { & py -3 -m venv .venv }
} else {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) { throw 'Python 3.11 or newer is required.' }
    $PythonVersion = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Python is unavailable.' }
    $VersionParts = $PythonVersion.Split('.')
    if ([int]$VersionParts[0] -lt 3 -or ([int]$VersionParts[0] -eq 3 -and [int]$VersionParts[1] -lt 11)) {
        throw "Python 3.11 or newer is required (found $PythonVersion)."
    }
    if (-not (Test-Path '.venv')) { & python -m venv .venv }
}

$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$Node = Get-Command node -ErrorAction SilentlyContinue
$Npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $Node -or -not $Npm) { throw 'Node.js 20+ and npm are required.' }
$NodeMajor = [int]((& node -p "process.versions.node.split('.')[0]").Trim())
if ($NodeMajor -lt 20) { throw 'Node.js 20 or newer is required.' }

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Failed to upgrade pip.' }
& $VenvPython -m pip install -r (Join-Path $Root 'backend\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Failed to install backend dependencies.' }

Push-Location (Join-Path $Root 'web')
try {
    if (Test-Path 'package-lock.json') { & npm ci } else { & npm install }
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install frontend dependencies.' }
} finally { Pop-Location }

New-Item -ItemType Directory -Force -Path '.aatm\logs', '.aatm\run' | Out-Null
Write-Host 'AATM dependencies installed. Start the application with scripts\start.ps1.'
