@echo off
setlocal
cd /d "%~dp0"
echo.
echo Smart combined novel and cover upload - batched for speed
echo Novels from novels\ and matching images from covers\ are included.
echo Up to 10 novels and their covers share one HF commit.
echo Equivalent ZIPs are skipped; ambiguous covers or editions block writes.
echo No local ZIP files will be deleted.
echo.
py -m taiyou_storage.upload novels --dedupe-local --interactive
set "result=%errorlevel%"
pause
exit /b %result%
