@echo off
rem Common readable framing for Taiyou Storage Controller Windows launchers.
rem Do not write private novel filenames, tokens or raw archive contents.
setlocal
set "phase=%~1"
set "task=%~2"
if /I "%phase%"=="start" (
    echo.
    echo === %task% ===
    echo   Status : Started
    echo ----------------------------------------
    exit /b 0
)
if /I "%phase%"=="end" (
    echo.
    echo ----------------------------------------
    echo === %task% ^| END ===
    if "%~3"=="0" (
        echo   Result : Finished
    ) else (
        echo   Result : Failed, exit code %~3
        echo   Action : Review the error above or the private report.
    )
    echo.
    exit /b 0
)
echo Usage: 19_command_output.cmd start^|end "Operation" [exit-code]
exit /b 2
