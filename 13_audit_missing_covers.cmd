@echo off
setlocal
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" start "Audit missing covers"
py -m taiyou_storage.inspection_cli covers %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" end "Audit missing covers" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
