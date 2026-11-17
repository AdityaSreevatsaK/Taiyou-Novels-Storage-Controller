@echo off
cd /d "%~dp0"
py -m taiyou_storage.cli status %*
set "result=%errorlevel%"
echo.
if not "%result%"=="0" echo Command failed with exit code %result%.
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
