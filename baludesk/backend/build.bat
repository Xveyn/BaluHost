@echo off
REM ============================================================================
REM BaluDesk Backend Build Script (Windows)
REM ============================================================================

setlocal EnableDelayedExpansion

REM Configuration
set BUILD_TYPE=Release
set BUILD_DIR=build
set CMAKE_GENERATOR=Visual Studio 17 2022
REM Compute absolute path to vcpkg
pushd %~dp0
cd ..\..
set VCPKG_ROOT=%CD%\vcpkg
popd

REM Ensure working directory is the script directory (backend/) so build dir is created there
cd /d "%~dp0"

REM Parse arguments
:parse_args
if "%1"=="" goto after_parse
if /i "%1"=="debug" set BUILD_TYPE=Debug
if /i "%1"=="release" set BUILD_TYPE=Release
if /i "%1"=="clean" (
    echo Cleaning build directory...
    if exist %BUILD_DIR% rmdir /s /q %BUILD_DIR%
    echo Clean complete.
    exit /b 0
)
shift
goto parse_args
:after_parse

echo ============================================================================
echo BaluDesk C++ Backend - Build Script
echo ============================================================================
echo Build Type: %BUILD_TYPE%
echo Build Directory: %BUILD_DIR%
echo CMake Generator: %CMAKE_GENERATOR%
echo ============================================================================

REM Check if vcpkg toolchain exists
if not exist "%VCPKG_ROOT%\scripts\buildsystems\vcpkg.cmake" (
    echo ERROR: vcpkg toolchain not found at "%VCPKG_ROOT%"
    echo Please install vcpkg and set VCPKG_ROOT correctly
    exit /b 1
)

REM Create build directory
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
cd "%BUILD_DIR%"

echo.
echo [1/3] Configuring CMake...
echo ============================================================================
cmake .. ^
    -G "%CMAKE_GENERATOR%" ^
    -A x64 ^
    -DCMAKE_BUILD_TYPE="%BUILD_TYPE%" ^
    -DCMAKE_TOOLCHAIN_FILE="%VCPKG_ROOT%\scripts\buildsystems\vcpkg.cmake" ^
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

if errorlevel 1 (
    echo ERROR: CMake configuration failed
    cd ..
    exit /b 1
)

echo.
echo [2/3] Building project...
echo ============================================================================
cmake --build . --config "%BUILD_TYPE%" --parallel

if errorlevel 1 (
    echo ERROR: Build failed
    cd ..
    exit /b 1
)

echo.
echo [3/3] Build complete!
echo ============================================================================
echo Executable: %BUILD_DIR%\%BUILD_TYPE%\baludesk-backend.exe
echo.
echo To run: .\%BUILD_DIR%\%BUILD_TYPE%\baludesk-backend.exe
echo ============================================================================

cd ..
exit /b 0
