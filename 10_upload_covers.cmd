@echo off
setlocal
rem Optional: suppress harmless Windows Hugging Face cache symlink warning.
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
cd /d "%~dp0"
call "%~dp019_command_output.cmd" start "Novel cover upload"
echo   Scope : Existing novels in PRIVATE Hugging Face; preview first.
set "archive=%~1"
if not defined archive if exist "covers\Downloaded_Covers.zip" set "archive=covers\Downloaded_Covers.zip"
if not defined archive if exist "covers\novel-cover-images.zip" set "archive=covers\novel-cover-images.zip"
if not defined archive if exist "Downloaded_Covers.zip" set "archive=Downloaded_Covers.zip"
if not defined archive if exist "novel-cover-images.zip" set "archive=novel-cover-images.zip"
if not defined archive set /p "archive=Path to cover ZIP (or directory): "
rem Users may paste a path with surrounding quotation marks. Strip them before re-quoting.
set "archive=%archive:"=%"
if not defined archive (echo No archive selected. & pause & exit /b 1)
echo   Mode  : Revision-guarded preview and confirmation
py -m taiyou_storage.covers "%archive%" --interactive
set "result=%errorlevel%"
call "%~dp019_command_output.cmd" end "Novel cover upload" "%result%"
pause
exit /b %result%
