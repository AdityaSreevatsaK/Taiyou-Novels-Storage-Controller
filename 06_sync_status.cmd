@echo off
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" start "Check local sync"
py -m taiyou_storage.cli status %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" end "Check local sync" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
