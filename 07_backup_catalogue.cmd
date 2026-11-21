@echo off
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp019_command_output.cmd" start "Back up catalogue"
py -m taiyou_storage.cli backup %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp019_command_output.cmd" end "Back up catalogue" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
