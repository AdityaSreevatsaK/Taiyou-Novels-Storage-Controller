@echo off
setlocal
cd /d "%~dp0"
py -m taiyou_storage.inspection_cleanup %*
exit /b %errorlevel%
