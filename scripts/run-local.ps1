# Drone137 launcher on Windows; the same as run-local.sh.
Set-Location (Join-Path $PSScriptRoot '..')
& '.venv\Scripts\python.exe' -m scripts.launch @args
exit $LASTEXITCODE
