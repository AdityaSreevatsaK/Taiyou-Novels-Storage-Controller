@echo off
cd /d "%~dp0"
py -m taiyou_storage.cli status
pause
