# Drone137 on Windows: the Python environment from the hash-locked requirements, Node and a browser checked, folders made.
# Run from PowerShell:  powershell -ExecutionPolicy Bypass -File scripts\bootstrap-windows.ps1 --minimal
param([string]$Mode = '--minimal')
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

function Find-Python {
  foreach ($candidate in @('py -3.12', 'py -3.13', 'py -3.11', 'py -3.14', 'python')) {
    try {
      $version = & cmd /c "$candidate -c `"import sys; print('%d.%d' % sys.version_info[:2])`"" 2>$null
      if ($LASTEXITCODE -eq 0 -and $version -match '^3\.(1[1-4])$') { return $candidate }
    } catch {}
  }
  throw 'Python 3.11 to 3.14 is required; install it from python.org with the launcher (py) enabled.'
}

$free = (Get-PSDrive -Name (Get-Location).Drive.Name).Free
if ($free -lt 10.5GB) { throw 'Minimal setup needs 0.5 GiB working allowance plus 10 GiB reserve on this drive' }

$python = Find-Python
Write-Host "Using $python"
if (-not (Test-Path '.venv\Scripts\python.exe')) { & cmd /c "$python -m venv .venv" ; if ($LASTEXITCODE) { throw 'venv failed' } }
& '.venv\Scripts\python.exe' -m pip install --disable-pip-version-check --require-hashes -r requirements.lock
if ($LASTEXITCODE) { throw 'pip install from requirements.lock failed; see docs/windows.md' }
& '.venv\Scripts\python.exe' -m pip install --disable-pip-version-check -r requirements-mission.txt
if ($LASTEXITCODE) { throw 'pip install from requirements-mission.txt failed' }

try { $node = & node --version } catch { $node = $null }
if (-not $node) { Write-Warning 'Node.js not found: the simulated camera and physics need it (install Node 20 or newer from nodejs.org).' }
else {
  Write-Host "Node $node"
  if (-not (Test-Path '.local\browser-test\node_modules\playwright')) {
    New-Item -ItemType Directory -Force -Path '.local\browser-test' | Out-Null
    & npm install --prefix .local/browser-test playwright@1.58.2
    if ($LASTEXITCODE) { Write-Warning 'Playwright install failed; the simulated camera will not open until it is installed.' }
  }
}
$browser = & '.venv\Scripts\python.exe' -c "from app.portability import browser_executable; print(browser_executable() or '')"
if (-not $browser) { Write-Warning 'No Chrome, Chromium or Edge found; install one or set CHROMIUM_PATH.' } else { Write-Host "Browser: $browser" }
New-Item -ItemType Directory -Force -Path '.local\data', '.local\build', '.local\validation' | Out-Null
Write-Host 'Bootstrap done. Start with "Start drone137.bat" or scripts\run-local.ps1 --mode recon --open-browser'
