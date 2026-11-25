<#
.SYNOPSIS
    Launches LUMO as a native Windows Desktop Application (Edge WebView2).
#>

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[ERROR] Backend virtual environment not found at $VenvPython" -ForegroundColor Red
    Write-Host "Run: cd backend; py -3.14 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

# Ensure pywebview is installed
& $VenvPython -c "import webview" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[SETUP] Installing pywebview desktop runtime..." -ForegroundColor Cyan
    & $VenvPython -m pip install -r (Join-Path $RepoRoot "desktop\requirements-desktop.txt")
}

Write-Host "[START] Launching LUMO Desktop..." -ForegroundColor Cyan
Set-Location $RepoRoot
$env:PYTHONPATH = $RepoRoot
& $VenvPython -m desktop.app
