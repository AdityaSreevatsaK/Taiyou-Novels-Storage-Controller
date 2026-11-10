@echo off
setlocal
cd /d "%~dp0"
echo.
echo DANGER: This deletes every file under data/ in your private Hugging Face dataset:
echo novels, ZIPs, EPUBs, covers, personal reviews, progress and collections.
echo This is NOT a duplicate-only cleanup.
echo.
echo Step 1: READ-ONLY preview
py -m taiyou_storage.reset
if errorlevel 1 (echo Preview failed. Nothing deleted. & pause & exit /b 1)
echo.
set /p "confirm=Begin FULL backup followed by a confirmed reset? Type YES: "
if /I not "%confirm%"=="YES" (echo Cancelled. & pause & exit /b 0)
py -m taiyou_storage.reset --apply
set "result=%errorlevel%"
pause
exit /b %result%
