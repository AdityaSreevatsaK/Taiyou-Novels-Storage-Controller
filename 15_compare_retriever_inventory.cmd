@echo off
setlocal
cd /d "%~dp0"
py -m taiyou_storage.inspection_cli compare --retriever-root "%~dp0..\Novel-Retriever" %*
exit /b %errorlevel%
