@echo off
setlocal
cd /d "%~dp0"
py -m taiyou_storage.inspection_cleanup %*
set "result=%errorlevel%"
echo.
if not "%result%"=="0" echo Command failed with exit code %result%.
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
