<#
.SYNOPSIS
    Starts LUMO Backend (FastAPI on 127.0.0.1:8000) and Frontend (127.0.0.1:3000) on Windows.
#>

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "lumo-frontend"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$EnvFile = Join-Path $BackendDir ".env"
$EnvExample = Join-Path $BackendDir ".env.example"

Write-Host "=== LUMO Platform Startup ===" -ForegroundColor Cyan

# 1. Validate Python virtual environment
if (-not (Test-Path $VenvPython)) {
    Write-Host "[ERROR] Backend virtual environment not found at: $VenvPython" -ForegroundColor Red
    Write-Host "Create it with:" -ForegroundColor Yellow
    Write-Host "  cd backend"
    Write-Host "  py -3.14 -m venv .venv"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

# 2. Ensure .env exists
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Host "[INFO] Created backend\.env from .env.example (SQLite fallback active if PostgreSQL is offline)." -ForegroundColor Yellow
    } else {
        Write-Host "[WARN] backend\.env not found. Using default environment settings." -ForegroundColor Yellow
    }
}

# 3. Start Backend Server (port 8000)
$port8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($port8000) {
    Write-Host "[OK] Backend already listening on http://127.0.0.1:8000" -ForegroundColor Green
} else {
    Write-Host "[START] Launching FastAPI Backend on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$BackendDir'; & '$VenvPython' -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000"
    )
}

# 4. Start Frontend Server (port 3000)
$port3000 = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if ($port3000) {
    Write-Host "[OK] Frontend already listening on http://127.0.0.1:3000" -ForegroundColor Green
} else {
    Write-Host "[START] Launching LUMO Frontend on http://127.0.0.1:3000 ..." -ForegroundColor Cyan
    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$FrontendDir'; & '$VenvPython' -m http.server 3000 --bind 127.0.0.1"
    )
}

Write-Host ""
Write-Host "LUMO is ready:" -ForegroundColor Green
Write-Host "  Frontend UI : http://127.0.0.1:3000"
Write-Host "  API Docs    : http://127.0.0.1:8000/docs"
Write-Host "  Diagnostics : http://127.0.0.1:8000/api/v1/health/diagnostics"
