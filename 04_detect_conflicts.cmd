@echo off
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp019_command_output.cmd" start "Check title conflicts"
py -m taiyou_storage.cli conflicts %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp019_command_output.cmd" end "Check title conflicts" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
