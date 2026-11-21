@echo off
setlocal
cd /d "%~dp0"
call "%~dp0console_output.bat" start "Bulk novel and cover upload"
echo   Scope : novels/ plus matching covers/; preview and confirmation required.
echo   Safety: Original local files are preserved.
py -m taiyou_storage.upload novels --dedupe-local --interactive
set "result=%errorlevel%"
call "%~dp0console_output.bat" end "Bulk novel and cover upload" "%result%"
pause
exit /b %result%
