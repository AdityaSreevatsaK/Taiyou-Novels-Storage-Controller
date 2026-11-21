@echo off
setlocal
cd /d "%~dp0"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" start "Compare retriever inventory"
py -m taiyou_storage.inspection_cli compare --retriever-root "%~dp0..\Novel-Retriever" %*
set "result=%errorlevel%"
if /I not "%~1"=="--help" call "%~dp0console_output.bat" end "Compare retriever inventory" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
