@echo off
setlocal
cd /d "%~dp0"
:menu
cls
echo Taiyou Novels Storage Controller
echo.
echo 2. Download all ZIPs
echo 3. List novels
echo 4. Detect title conflicts
echo 6. Local sync status
echo 7. Back up catalogue
echo 0. Exit
echo.
set /p "choice=Choice: "
if "%choice%"=="2" call "%~dp002_download_all.cmd"
if "%choice%"=="3" call "%~dp003_list_novels.cmd"
if "%choice%"=="4" call "%~dp004_detect_conflicts.cmd"
if "%choice%"=="6" call "%~dp006_sync_status.cmd"
if "%choice%"=="7" call "%~dp007_backup_catalogue.cmd"
if "%choice%"=="0" exit /b 0
goto menu
