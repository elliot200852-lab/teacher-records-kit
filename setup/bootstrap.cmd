@echo off
REM Double-click me: runs setup\bootstrap.ps1 with a safe execution policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" %*
pause
