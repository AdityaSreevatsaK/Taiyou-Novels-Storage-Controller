@echo off
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" start "Download novel ZIPs"
py -m taiyou_storage.cli download %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" end "Download novel ZIPs" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
