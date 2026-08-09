@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
start "WendaXitog Installer" /wait powershell.exe -NoLogo -NoProfile -STA -WindowStyle Normal -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install-bundle.ps1" -PackageZip "%SCRIPT_DIR%payload.zip"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo WendaXitog installation failed. Exit code: %EXIT_CODE%
    pause
)

exit /b %EXIT_CODE%
