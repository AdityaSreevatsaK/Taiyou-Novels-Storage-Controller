@echo off
setlocal
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" start "Verify novel integrity"
py -m taiyou_storage.inspection_cli integrity %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" end "Verify novel integrity" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
