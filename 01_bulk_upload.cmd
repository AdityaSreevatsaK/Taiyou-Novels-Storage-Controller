@echo off
setlocal
cd /d "%~dp0"
echo.
echo STEP 1 - Preview the upload plan
py -m taiyou_storage.upload novels
if errorlevel 1 (echo Upload plan failed. & pause & exit /b 1)
echo.
set /p "confirm=Apply these changes to the PRIVATE HF dataset? Type YES: "
if /I not "%confirm%"=="YES" (echo Cancelled. & pause & exit /b 0)
py -m taiyou_storage.upload novels --apply
pause
