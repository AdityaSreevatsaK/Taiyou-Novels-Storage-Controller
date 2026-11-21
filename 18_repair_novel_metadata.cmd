@echo off
setlocal
cd /d "%~dp0"
if /I "%~1"=="--help" goto :help
call "%~dp0console_output.bat" start "Novel source metadata"
echo 1. Audit ALL novels for missing source synopsis, genres and status (READ ONLY)
echo 2. Prepare JSON for ONE novel (READ ONLY)
echo 3. Preview an existing repair JSON (READ ONLY)
echo 4. Apply the PREVIEWED metadata repair (PRIVATE CATALOGUE ONLY)
echo.
echo --- MULTI-NOVEL REPAIR ---
echo 5. Discover missing metadata for ALL novels (read public BOOK pages ONLY)
echo 6. Review and approve verified proposals one by one (LOCAL ONLY)
echo 7. Approve ALL verified proposals after reviewing CSV (LOCAL ONLY)
echo 8. Preview approved bulk changes against PRIVATE HF catalogue
echo 9. Apply reviewed bulk changes in ONE PRIVATE HF commit
echo 10. Import researched source metadata JSON (requires individual review)
echo 0. Cancel
echo.
set /p "choice=Choose: "
if "%choice%"=="1" goto :audit
if "%choice%"=="2" goto :prepare
if "%choice%"=="3" goto :preview
if "%choice%"=="4" goto :apply
if "%choice%"=="5" goto :batch_discover
if "%choice%"=="6" goto :batch_review
if "%choice%"=="7" goto :batch_all
if "%choice%"=="8" goto :batch_preview
if "%choice%"=="9" goto :batch_apply
if "%choice%"=="10" goto :batch_import
if "%choice%"=="0" exit /b 0
echo Unrecognised option.
exit /b 1

:audit
py -m taiyou_storage.metadata_repair audit
goto :finish

:prepare
py -m taiyou_storage.metadata_repair prepare
goto :finish

:preview
py -m taiyou_storage.metadata_repair preview
goto :finish

:apply
py -m taiyou_storage.metadata_repair apply
goto :finish

:batch_discover
py -m taiyou_storage.metadata_batch discover
goto :finish

:batch_import
py -m taiyou_storage.metadata_batch import
goto :finish

:batch_review
py -m taiyou_storage.metadata_batch review
goto :finish

:batch_all
py -m taiyou_storage.metadata_batch review --approve-all
goto :finish

:batch_preview
py -m taiyou_storage.metadata_batch preview
goto :finish

:batch_apply
py -m taiyou_storage.metadata_batch apply
goto :finish

:help
py -m taiyou_storage.metadata_repair --help
goto :finish

:finish
set "result=%errorlevel%"
call "%~dp0console_output.bat" end "Novel source metadata" "%result%"
if /I "%~1"=="--help" exit /b %result%
echo.
pause
exit /b %result%
