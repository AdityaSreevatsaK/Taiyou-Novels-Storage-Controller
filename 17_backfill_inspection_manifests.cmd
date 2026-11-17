@echo off
setlocal
cd /d "%~dp0"
py -m taiyou_storage.manifest_backfill %*
exit /b %errorlevel%
