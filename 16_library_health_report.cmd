@echo off
setlocal
cd /d "%~dp0"
py -m taiyou_storage.inspection_cli health %*
exit /b %errorlevel%
