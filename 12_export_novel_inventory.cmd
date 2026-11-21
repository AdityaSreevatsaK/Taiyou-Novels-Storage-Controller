@echo off
setlocal
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" start "Export chapter inventory"
py -m taiyou_storage.inspection_cli inventory %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" end "Export chapter inventory" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
