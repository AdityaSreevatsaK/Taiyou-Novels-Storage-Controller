@echo off
setlocal
cd /d "%~dp0"
:menu
cls
echo ====================================================
echo Taiyou Novels Storage Controller
echo Local commands ^| private HF data remains protected
echo ====================================================
echo.
echo 1. Upload novels and covers
echo 2. Download all ZIPs
echo 3. List novels
echo 4. Detect title conflicts
echo 5. Verify library integrity (read-only)
echo 6. Local sync status
echo 7. Back up catalogue
echo 10. Upload novel cover images (ZIP)
echo 11. RESET private HF data (DANGEROUS, full backup required)
echo 12. Export chapter inventory
echo 13. Audit missing covers
echo 14. Compare Novel Retriever inventory
echo 15. Library health dashboard
echo 16. Backfill remote inspection manifests (preview or approved upload)
echo 17. Clean local inspection cache
echo 18. Audit or repair novel metadata
echo 0. Exit
echo.
set /p "choice=Choice: "
if "%choice%"=="1" call "%~dp001_bulk_upload.cmd"
if "%choice%"=="2" call "%~dp002_download_all.cmd"
if "%choice%"=="3" call "%~dp003_list_novels.cmd"
if "%choice%"=="4" call "%~dp004_detect_conflicts.cmd"
if "%choice%"=="5" call "%~dp005_verify_integrity.cmd"
if "%choice%"=="6" call "%~dp006_sync_status.cmd"
if "%choice%"=="7" call "%~dp007_backup_catalogue.cmd"
if "%choice%"=="10" call "%~dp010_upload_covers.cmd"
if "%choice%"=="11" call "%~dp011_clear_hf_data.cmd"
if "%choice%"=="12" call "%~dp012_export_novel_inventory.cmd"
if "%choice%"=="13" call "%~dp013_audit_missing_covers.cmd"
if "%choice%"=="14" call "%~dp014_compare_retriever_inventory.cmd"
if "%choice%"=="15" call "%~dp015_library_health_report.cmd"
if "%choice%"=="16" call "%~dp016_backfill_inspection_manifests.cmd"
if "%choice%"=="17" call "%~dp017_cleanup_inspection_downloads.cmd"
if "%choice%"=="18" call "%~dp018_repair_novel_metadata.cmd"
if "%choice%"=="0" (echo Controller closed. No files changed. & exit /b 0)
goto menu
