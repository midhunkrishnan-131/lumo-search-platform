@echo off
setlocal
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
    echo [ERROR] backend\.venv not found. Run setup_lumo.bat first.
    exit /b 1
)
pushd backend
".venv\Scripts\python.exe" -m app.ops.cli check
set EXIT_CODE=%errorlevel%
popd
exit /b %EXIT_CODE%
