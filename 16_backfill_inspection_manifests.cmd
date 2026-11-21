@echo off
setlocal
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" start "Backfill inspection manifests"
py -m taiyou_storage.manifest_backfill %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" end "Backfill inspection manifests" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
