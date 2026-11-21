@echo off
setlocal
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" start "Create library health report"
py -m taiyou_storage.inspection_cli health %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" end "Create library health report" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
