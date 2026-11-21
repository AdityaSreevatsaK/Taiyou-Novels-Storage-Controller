@echo off
setlocal
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp019_command_output.cmd" start "Audit missing covers"
py -m taiyou_storage.inspection_cli covers %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp019_command_output.cmd" end "Audit missing covers" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
