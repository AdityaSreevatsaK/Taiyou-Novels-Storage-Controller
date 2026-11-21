@echo off
setlocal
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp019_command_output.cmd" start "Backfill inspection manifests"
py -m taiyou_storage.manifest_backfill %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp019_command_output.cmd" end "Backfill inspection manifests" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
