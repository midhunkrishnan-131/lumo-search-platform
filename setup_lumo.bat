@echo off
setlocal
cd /d "%~dp0"
echo === LUMO Windows Setup ===

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not installed or not on PATH. Install Python 3.11+ and retry.
    exit /b 1
)

if not exist "backend\.venv\Scripts\python.exe" (
    echo [SETUP] Creating virtual environment in backend\.venv ...
    python -m venv "backend\.venv"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        exit /b 1
    )
)

echo [SETUP] Installing Python dependencies ...
"backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt" --quiet
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    exit /b 1
)

if not exist "backend\.env" (
    if exist "backend\.env.example" (
        copy /Y "backend\.env.example" "backend\.env" >nul
        echo [SETUP] Created backend\.env from .env.example
    )
)

echo [SETUP] Applying non-destructive database schema checks ...
pushd backend
".venv\Scripts\python.exe" -m app.ops.cli migrate
if errorlevel 1 (
    popd
    echo [ERROR] Database migration check failed.
    exit /b 1
)
".venv\Scripts\python.exe" -m app.ops.cli check
popd

echo [OK] LUMO setup complete. Run start_lumo.bat to launch.
endlocal
