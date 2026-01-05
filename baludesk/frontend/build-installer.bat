@echo off
REM BaluDesk NSIS Installer Build Script
REM Usage: build-installer.bat
REM Requirements: NSIS installed and in PATH

setlocal enabledelayedexpansion

echo.
echo ====================================================================
echo BaluDesk - Professional NSIS Installer Build
echo ====================================================================
echo.

REM Check if NSIS is installed
where makensis >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: NSIS is not installed or not in PATH
    echo.
    echo To install NSIS:
    echo 1. Download from: https://nsis.sourceforge.io/Download
    echo 2. Run the installer
    echo 3. Choose "Add NSIS to System PATH" during installation
    echo.
    pause
    exit /b 1
)

echo [1/5] Cleaning old builds...
if exist "dist-electron" (
    echo Removing old dist-electron...
    powershell -Command "Remove-Item -Path 'dist-electron' -Recurse -Force -ErrorAction SilentlyContinue"
)

echo [2/5] Compiling TypeScript (Electron Main Process)...
call npm run compile
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: TypeScript compilation failed
    exit /b 1
)

echo [3/5] Building React Frontend with Vite...
call vite build
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Vite build failed
    exit /b 1
)

echo [4/5] Creating distribution directory...
if not exist "dist-electron" mkdir dist-electron

echo [5/5] Building NSIS Installer...
makensis.exe /V3 "BaluDesk-Installer.nsi"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: NSIS build failed
    exit /b 1
)

echo.
echo ====================================================================
echo SUCCESS! Installer created: dist-electron\BaluDesk-Setup-1.0.0.exe
echo ====================================================================
echo.
echo Next steps:
echo 1. Test the installer: dist-electron\BaluDesk-Setup-1.0.0.exe
echo 2. Verify installation in "C:\Program Files\BaluDesk\"
echo 3. Check Start Menu for BaluDesk entry
echo 4. Distribute to users
echo.
pause
exit /b 0
