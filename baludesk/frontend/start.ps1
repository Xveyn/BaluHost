# BaluDesk Start Script (PowerShell - Cross-Platform)
# Works on Windows and Linux

# Detect OS
$IsWindows = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)
$IsLinux = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Linux)

# On Windows: Check if running as admin, if not relaunch with admin
if ($IsWindows) {
    if (-Not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] 'Administrator')) {
        Write-Host "Requesting Administrator privileges..." -ForegroundColor Yellow
        Start-Process powershell.exe -ArgumentList "-NoExit", "-File `"$PSCommandPath`"" -Verb RunAs
        exit
    }
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host ""
Write-Host "========================================"
Write-Host "  BaluDesk - Starting Application"
Write-Host "========================================"
Write-Host ""
Write-Host "Current directory: $ScriptDir"
Write-Host ""

# Kill any running BaluDesk processes
Write-Host "[*] Cleaning up old processes..." -ForegroundColor Cyan
Get-Process baludesk-backend -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process electron -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Write-Host "[OK] Old processes cleaned" -ForegroundColor Green
echo ""

# Start backend in background
$BackendPath = Join-Path $ScriptDir "backend\baludesk-backend.exe"
if (Test-Path $BackendPath) {
    Write-Host "[*] Starting Backend..." -ForegroundColor Cyan
    Start-Process -FilePath $BackendPath -WindowStyle Hidden
    Start-Sleep -Seconds 2
    Write-Host "[OK] Backend started" -ForegroundColor Green
} else {
    Write-Host "[!] Warning: Backend not found at $BackendPath" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[*] Starting Frontend..." -ForegroundColor Cyan

# Start Electron frontend
$ElectronPath = Join-Path $ScriptDir "electron.exe"
if (Test-Path $ElectronPath) {
    # Pass path with proper escaping for spaces
    Start-Process -FilePath $ElectronPath -ArgumentList "`"$ScriptDir`"" -WindowStyle Normal
    Write-Host "[OK] Frontend started" -ForegroundColor Green
    Write-Host ""
    Write-Host "BaluDesk is running. You can close this window." -ForegroundColor Green
    Write-Host ""
    Start-Sleep -Seconds 3
} else {
    Write-Host "[ERROR] electron.exe not found at $ElectronPath" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

exit 0
