@echo off
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp019_command_output.cmd" start "Check local sync"
py -m taiyou_storage.cli status %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp019_command_output.cmd" end "Check local sync" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
