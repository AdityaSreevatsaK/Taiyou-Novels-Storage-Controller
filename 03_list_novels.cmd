@echo off
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp019_command_output.cmd" start "Export novel catalogue"
py -m taiyou_storage.cli list %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp019_command_output.cmd" end "Export novel catalogue" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
