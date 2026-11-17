@echo off
setlocal
cd /d "%~dp0"
echo.
echo Smart bulk upload with verified local deduplication
echo Equivalent local ZIPs will be skipped. Conflicting editions block all uploads.
echo No local ZIP files will be deleted.
echo.
py -m taiyou_storage.upload novels --dedupe-local --interactive
set "result=%errorlevel%"
pause
exit /b %result%
