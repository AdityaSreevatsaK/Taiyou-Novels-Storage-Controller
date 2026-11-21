@echo off
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" start "Export novel catalogue"
py -m taiyou_storage.cli list %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" end "Export novel catalogue" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
