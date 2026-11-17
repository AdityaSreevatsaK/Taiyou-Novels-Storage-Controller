@echo off
setlocal
cd /d "%~dp0"
py -m taiyou_storage.manifest_backfill %*
set "result=%errorlevel%"
echo.
if not "%result%"=="0" echo Command failed with exit code %result%.
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
