# BaluHost Windows Service Installer
# Installiert BaluHost als Windows Service für automatischen Start

param(
    [string]$InstallPath = "F:\Programme (x86)\Baluhost",
    [string]$PythonPath = "python",
    [int]$Port = 8000
)

Write-Host "=== BaluHost Service Installation ===" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script requires Administrator privileges!" -ForegroundColor Red
    Write-Host "Please run PowerShell as Administrator and try again." -ForegroundColor Yellow
    exit 1
}

# Install NSSM (Non-Sucking Service Manager) if not present
$nssmPath = Join-Path $InstallPath "tools\nssm.exe"
if (-not (Test-Path $nssmPath)) {
    Write-Host "Installing NSSM (Service Manager)..." -ForegroundColor Yellow
    
    $toolsDir = Join-Path $InstallPath "tools"
    New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
    
    # Download NSSM
    $nssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
    $nssmZip = Join-Path $toolsDir "nssm.zip"
    
    try {
        Write-Host "Downloading NSSM..."
        Invoke-WebRequest -Uri $nssmUrl -OutFile $nssmZip -UseBasicParsing
        
        # Extract
        Expand-Archive -Path $nssmZip -DestinationPath $toolsDir -Force
        
        # Copy exe to tools directory
        $arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
        Copy-Item -Path (Join-Path $toolsDir "nssm-2.24\$arch\nssm.exe") -Destination $nssmPath -Force
        
        # Cleanup
        Remove-Item -Path $nssmZip -Force
        Remove-Item -Path (Join-Path $toolsDir "nssm-2.24") -Recurse -Force
        
        Write-Host "✓ NSSM installed" -ForegroundColor Green
    } catch {
        Write-Host "ERROR: Failed to download NSSM: $_" -ForegroundColor Red
        exit 1
    }
}

# Create service configuration
$serviceName = "BaluHost"
$startScript = Join-Path $InstallPath "start_dev.py"
$pythonExe = (Get-Command $PythonPath).Source

Write-Host "Configuring service..." -ForegroundColor Yellow
Write-Host "  Service Name: $serviceName"
Write-Host "  Python: $pythonExe"
Write-Host "  Start Script: $startScript"
Write-Host "  Port: $Port"
Write-Host ""

# Stop existing service if running
$existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Host "Removing existing service..." -ForegroundColor Yellow
    & $nssmPath stop $serviceName
    & $nssmPath remove $serviceName confirm
    Start-Sleep -Seconds 2
}

# Install service
Write-Host "Installing service..." -ForegroundColor Yellow
& $nssmPath install $serviceName $pythonExe $startScript

# Configure service
& $nssmPath set $serviceName AppDirectory $InstallPath
& $nssmPath set $serviceName DisplayName "BaluHost NAS Server"
& $nssmPath set $serviceName Description "BaluHost - Private Cloud Storage Server (iCloud/OneDrive Alternative)"
& $nssmPath set $serviceName Start SERVICE_AUTO_START
& $nssmPath set $serviceName AppStopMethodConsole 10000
& $nssmPath set $serviceName AppStopMethodWindow 10000
& $nssmPath set $serviceName AppStopMethodThreads 10000

# Set environment variables
& $nssmPath set $serviceName AppEnvironmentExtra "NAS_MODE=production" "BALUHOST_PORT=$Port"

# Configure logging
$logDir = Join-Path $InstallPath "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

& $nssmPath set $serviceName AppStdout (Join-Path $logDir "service.log")
& $nssmPath set $serviceName AppStderr (Join-Path $logDir "service-error.log")
& $nssmPath set $serviceName AppStdoutCreationDisposition 4  # Append
& $nssmPath set $serviceName AppStderrCreationDisposition 4  # Append
& $nssmPath set $serviceName AppRotateFiles 1
& $nssmPath set $serviceName AppRotateBytes 10485760  # 10MB

Write-Host "✓ Service installed" -ForegroundColor Green
Write-Host ""

# Configure Windows Firewall
Write-Host "Configuring Windows Firewall..." -ForegroundColor Yellow

$firewallRules = @(
    @{Name = "BaluHost-API"; Port = $Port; Description = "BaluHost API Server"},
    @{Name = "BaluHost-WebDAV"; Port = 8080; Description = "BaluHost WebDAV Server"}
)

foreach ($rule in $firewallRules) {
    $existingRule = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
    if ($existingRule) {
        Remove-NetFirewallRule -DisplayName $rule.Name
    }
    
    New-NetFirewallRule -DisplayName $rule.Name `
                        -Description $rule.Description `
                        -Direction Inbound `
                        -Protocol TCP `
                        -LocalPort $rule.Port `
                        -Action Allow `
                        -Profile Private,Domain `
                        -Enabled True | Out-Null
    
    Write-Host "  ✓ Firewall rule: $($rule.Name) (Port $($rule.Port))" -ForegroundColor Green
}

Write-Host ""

# Get local IP address
$localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notmatch 'Loopback'} | Select-Object -First 1).IPAddress

Write-Host "=== Installation Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Service Status:" -ForegroundColor Cyan
Write-Host "  Service Name: $serviceName"
Write-Host "  Status: Installed (not started)"
Write-Host ""
Write-Host "Network Access:" -ForegroundColor Cyan
Write-Host "  Local IP: $localIP"
Write-Host "  API Server: https://${localIP}:${Port}"
Write-Host "  WebDAV Server: http://${localIP}:8080"
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Start the service:"
Write-Host "     Start-Service $serviceName"
Write-Host ""
Write-Host "  2. Map Network Drive (Windows):"
Write-Host "     \\${localIP}@8080\webdav"
Write-Host ""
Write-Host "  3. View logs:"
Write-Host "     Get-Content '$logDir\service.log' -Tail 50 -Wait"
Write-Host ""
Write-Host "Management Commands:" -ForegroundColor Cyan
Write-Host "  Start:   Start-Service $serviceName"
Write-Host "  Stop:    Stop-Service $serviceName"
Write-Host "  Status:  Get-Service $serviceName"
Write-Host "  Restart: Restart-Service $serviceName"
Write-Host ""

# Ask to start service
$start = Read-Host "Start the service now? (y/n)"
if ($start -eq 'y' -or $start -eq 'Y') {
    Write-Host ""
    Write-Host "Starting service..." -ForegroundColor Yellow
    Start-Service $serviceName
    Start-Sleep -Seconds 3
    
    $service = Get-Service $serviceName
    if ($service.Status -eq 'Running') {
        Write-Host "✓ Service started successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "BaluHost is now running at https://${localIP}:${Port}" -ForegroundColor Cyan
    } else {
        Write-Host "✗ Service failed to start. Check logs for details." -ForegroundColor Red
        Write-Host "  Log: $logDir\service-error.log"
    }
}
