@echo off
setlocal
cd /d "%~dp0"
echo === LUMO Safe Update Workflow ===
if not exist "backend\.venv\Scripts\python.exe" (
    echo [ERROR] backend\.venv not found. Run setup_lumo.bat first.
    exit /b 1
)

pushd backend
echo [1/3] Creating pre-update safety backup ...
".venv\Scripts\python.exe" -m app.ops.cli backup --label pre_update
if errorlevel 1 (
    popd
    echo [ERROR] Pre-update backup failed. Aborting update.
    exit /b 1
)

echo [2/3] Verifying Python dependencies ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet

echo [3/3] Applying safe non-destructive migrations ...
".venv\Scripts\python.exe" -m app.ops.cli migrate
popd

echo [OK] Update checks complete. Run restart_lumo.bat to restart services.
endlocal
