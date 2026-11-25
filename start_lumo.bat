@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_lumo.ps1"
if errorlevel 1 (
    echo [ERROR] LUMO startup failed. Run check_lumo.bat for diagnostics.
    exit /b 1
)
endlocal
