<#
.SYNOPSIS
    Builds the LUMO Windows Desktop distribution using PyInstaller.
    Note: Does NOT delete user data in %LOCALAPPDATA%\LUMO.
#>

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VenvPython = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
$SpecFile = Join-Path $RepoRoot "desktop\lumo_desktop.spec"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[ERROR] Virtual environment not found at $VenvPython" -ForegroundColor Red
    exit 1
}

& $VenvPython -m pip show pyinstaller 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[INFO] Installing PyInstaller into .venv..." -ForegroundColor Cyan
    & $VenvPython -m pip install pyinstaller
}

Write-Host "[BUILD] Packaging LUMO Windows Desktop bundle..." -ForegroundColor Cyan
Set-Location $RepoRoot
& $VenvPython -m PyInstaller --noconfirm --clean $SpecFile

Write-Host "[DONE] Output available in: $(Join-Path $RepoRoot 'dist\LUMO\LUMO.exe')" -ForegroundColor Green
