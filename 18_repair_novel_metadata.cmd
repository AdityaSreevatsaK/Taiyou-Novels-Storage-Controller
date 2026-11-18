@echo off
setlocal
cd /d "%~dp0"
if /I "%~1"=="--help" goto :help
echo.
echo Taiyou Novels - Source Metadata Audit and Repair
echo.
echo 1. Audit ALL novels for missing source synopsis, genres and status (READ ONLY)
echo 2. Prepare JSON for ONE novel (READ ONLY)
echo 3. Preview an existing repair JSON (READ ONLY)
echo 4. Apply the PREVIEWED metadata repair (PRIVATE CATALOGUE ONLY)
echo 0. Cancel
echo.
set /p "choice=Choose: "
if "%choice%"=="1" goto :audit
if "%choice%"=="2" goto :prepare
if "%choice%"=="3" goto :preview
if "%choice%"=="4" goto :apply
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

:help
py -m taiyou_storage.metadata_repair --help
goto :finish

:finish
set "result=%errorlevel%"
if not "%result%"=="0" echo Command failed with exit code %result%.
if /I "%~1"=="--help" exit /b %result%
echo.
pause
exit /b %result%
