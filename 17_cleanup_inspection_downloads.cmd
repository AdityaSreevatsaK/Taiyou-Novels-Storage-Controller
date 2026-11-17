@echo off
setlocal
cd /d "%~dp0"
echo.
echo Taiyou's Personal Library - Local Inspection Download Cleanup
echo.
if "%~1"=="" (
    echo Double-click mode: checking both recent inspection downloads and older
    echo Hugging Face novel EPUB / ZIP / cover cache entries.
    echo Only local cache files are eligible. No files on Hugging Face are deleted.
    echo You will see the preview and must type DELETE LOCAL CACHE to proceed.
    echo.
    py -m taiyou_storage.inspection_cleanup --legacy-shared-cache --apply
) else (
    rem Explicit arguments retain the Python CLI semantics, including preview only.
    py -m taiyou_storage.inspection_cleanup %*
)
set "result=%errorlevel%"
echo.
if not "%result%"=="0" echo Command failed with exit code %result%.
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
