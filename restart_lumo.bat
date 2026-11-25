@echo off
setlocal
cd /d "%~dp0"
call "%~dp0stop_lumo.bat"
timeout /t 2 /nobreak >nul
call "%~dp0start_lumo.bat"
endlocal
