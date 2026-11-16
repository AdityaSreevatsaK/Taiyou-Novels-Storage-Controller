@echo off
setlocal
cd /d "%~dp0"
echo.
echo Preview and verify duplicate old/new ZIPs before any cloud upload
echo Existing editions with conflicting chapters will block the entire batch.
echo No local ZIP files will be deleted.
echo.
py -m taiyou_storage.upload novels --dedupe-local --interactive
set "result=%errorlevel%"
pause
exit /b %result%
