@echo off
setlocal
echo === Stopping LUMO Services (Ports 8000 and 3000) ===
powershell -NoProfile -Command "foreach ($port in 8000, 3000) { $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; foreach ($c in $conns) { if ($c.OwningProcess -gt 0) { Write-Host ('Stopping LUMO listener on port ' + $port + ' (PID ' + $c.OwningProcess + ')'); Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } } }"
echo [OK] LUMO stop completed.
endlocal
