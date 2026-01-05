@echo off
REM BaluDesk Electron App Launcher
REM This batch file launches Electron with the correct working directory

cd /d "%~dp0..\.."
start electron.exe dist/main/main.js
