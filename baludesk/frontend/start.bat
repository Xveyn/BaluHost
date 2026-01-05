@echo off
REM BaluDesk Start Script - Wrapper
REM This launches the PowerShell startup script

setlocal enabledelayedexpansion

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"

REM Call PowerShell to run the startup script
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start.ps1"
