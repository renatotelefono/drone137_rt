@echo off
rem Drone137 on Windows: bootstraps the Python environment if missing, then opens the local console.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  powershell -ExecutionPolicy Bypass -File "scripts\bootstrap-windows.ps1" --minimal || exit /b 2
)
".venv\Scripts\python.exe" -m scripts.launch --mode recon --open-browser
endlocal
