@echo off
setlocal
cd /d "%~dp0"
echo.
echo Preview and confirm novel uploads in one revision-guarded run
py -m taiyou_storage.upload novels --interactive
set "result=%errorlevel%"
pause
exit /b %result%
