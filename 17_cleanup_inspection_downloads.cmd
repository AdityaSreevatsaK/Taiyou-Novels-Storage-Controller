@echo off
setlocal
cd /d "%~dp0"
call "%~dp0console_output.bat" start "Local inspection cache cleanup"
if "%~1"=="" (
    echo   Scope : Owned inspection cache and selected old HF cache entries.
    echo   Safety: Local only. Private HF data unchanged. Confirmation required.
    py -m taiyou_storage.inspection_cleanup --legacy-shared-cache --apply
) else (
    rem Explicit arguments retain the Python CLI semantics, including preview only.
    py -m taiyou_storage.inspection_cleanup %*
)
set "result=%errorlevel%"
call "%~dp0console_output.bat" end "Local inspection cache cleanup" "%result%"
if /I "%~1"=="--help" exit /b %result%
pause
exit /b %result%
