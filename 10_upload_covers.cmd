@echo off
setlocal
cd /d "%~dp0"
echo.
echo Novel Cover Uploader - Private Hugging Face Dataset
echo Provide Downloaded_Covers.zip (the artifact ZIP can also be used).
echo.
set "archive=%~1"
if not defined archive if exist "covers\Downloaded_Covers.zip" set "archive=covers\Downloaded_Covers.zip"
if not defined archive if exist "covers\novel-cover-images.zip" set "archive=covers\novel-cover-images.zip"
if not defined archive if exist "Downloaded_Covers.zip" set "archive=Downloaded_Covers.zip"
if not defined archive if exist "novel-cover-images.zip" set "archive=novel-cover-images.zip"
if not defined archive set /p "archive=Path to cover ZIP (or directory): "
rem Users may paste a path with surrounding quotation marks. Strip them before re-quoting.
set "archive=%archive:"=%"
if not defined archive (echo No archive selected. & pause & exit /b 1)
echo.
echo Step 1: Preview only
py -m taiyou_storage.covers "%archive%"
if errorlevel 1 (echo Upload cancelled due to errors. & pause & exit /b 1)
echo.
set /p "confirm=Upload changed covers to your PRIVATE HF dataset? Type YES: "
if /I not "%confirm%"=="YES" (echo Cancelled. & pause & exit /b 0)
py -m taiyou_storage.covers "%archive%" --apply
set "result=%errorlevel%"
pause
exit /b %result%
