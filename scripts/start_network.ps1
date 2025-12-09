# BaluHost Home Network Quick Setup
# Configures firewall and starts server for home network access

param(
    [switch]$SkipFirewall
)

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║        BaluHost - Home Network Quick Setup           ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir

# Check if running as Administrator for firewall config
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $SkipFirewall) {
    if (-not $isAdmin) {
        Write-Host "⚠️  Not running as Administrator" -ForegroundColor Yellow
        Write-Host "   Firewall configuration will be skipped." -ForegroundColor Yellow
        Write-Host "   If other devices can't connect, run as Admin:" -ForegroundColor Yellow
        Write-Host "   .\scripts\configure_firewall.ps1" -ForegroundColor Cyan
        Write-Host ""
        
        $continue = Read-Host "Continue without firewall config? (y/n)"
        if ($continue -ne 'y' -and $continue -ne 'Y') {
            Write-Host "Exiting. Please run as Administrator." -ForegroundColor Yellow
            exit 1
        }
    } else {
        Write-Host "Configuring firewall rules..." -ForegroundColor Yellow
        & "$scriptDir\configure_firewall.ps1"
        Write-Host ""
    }
}

# Get local IP
Write-Host "Detecting network configuration..." -ForegroundColor Yellow
$localIP = $null
try {
    $socket = New-Object System.Net.Sockets.UdpClient
    $socket.Connect("8.8.8.8", 80)
    $localIP = $socket.Client.LocalEndPoint.Address.ToString()
    $socket.Close()
} catch {
    $localIP = (Get-NetIPAddress -AddressFamily IPv4 | 
                Where-Object {$_.InterfaceAlias -notmatch 'Loopback'} | 
                Select-Object -First 1).IPAddress
}

if (-not $localIP) {
    $localIP = "localhost"
}

Write-Host "✓ Network detected" -ForegroundColor Green
Write-Host ""

# Display access information
Write-Host "╔════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║              Access Information                       ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "📱 On This Computer:" -ForegroundColor Cyan
Write-Host "   Web Interface: https://localhost:8000" -ForegroundColor White
Write-Host "   Network Drive: \\localhost@8080\webdav" -ForegroundColor White
Write-Host ""
Write-Host "🌐 From Other Devices in Your Network:" -ForegroundColor Cyan
Write-Host "   Your IP: $localIP" -ForegroundColor Yellow
Write-Host "   Web Interface: https://$localIP:8000" -ForegroundColor White
Write-Host "   Network Drive: \\$localIP@8080\webdav" -ForegroundColor White
Write-Host ""
Write-Host "👤 Login Credentials:" -ForegroundColor Cyan
Write-Host "   Username: admin" -ForegroundColor White
Write-Host "   Password: changeme" -ForegroundColor White
Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════╗" -ForegroundColor Yellow
Write-Host "║                Important Notes                        ║" -ForegroundColor Yellow
Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Yellow
Write-Host ""
Write-Host "⚠️  Self-Signed Certificate:" -ForegroundColor Yellow
Write-Host "   Your browser will show a security warning." -ForegroundColor Gray
Write-Host "   This is normal for local development." -ForegroundColor Gray
Write-Host "   Click 'Advanced' → 'Continue to localhost'" -ForegroundColor Gray
Write-Host ""
Write-Host "🔒 Security:" -ForegroundColor Yellow
Write-Host "   • Server is only accessible in your local network" -ForegroundColor Gray
Write-Host "   • Change the default password after first login" -ForegroundColor Gray
Write-Host "   • Don't expose to the internet without proper security" -ForegroundColor Gray
Write-Host ""
Write-Host "🔍 Network Discovery:" -ForegroundColor Yellow
Write-Host "   • Server broadcasts via mDNS/Bonjour" -ForegroundColor Gray
Write-Host "   • Desktop client can auto-find the server" -ForegroundColor Gray
Write-Host "   • Test: python client-desktop\discover_server.py" -ForegroundColor Gray
Write-Host ""

# Check network profile
$profile = Get-NetConnectionProfile | Where-Object {$_.IPv4Connectivity -eq "Internet" -or $_.IPv4Connectivity -eq "LocalNetwork"} | Select-Object -First 1
if ($profile -and $profile.NetworkCategory -eq "Public") {
    Write-Host "⚠️  WARNING: Network is set to 'Public'" -ForegroundColor Red
    Write-Host "   Other devices won't be able to connect!" -ForegroundColor Red
    Write-Host "   Change to 'Private' in Windows Settings" -ForegroundColor Yellow
    Write-Host ""
}

# Offer to start server
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
$start = Read-Host "Start BaluHost server now? (y/n)"

if ($start -eq 'y' -or $start -eq 'Y') {
    Write-Host ""
    Write-Host "Starting BaluHost..." -ForegroundColor Green
    Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
    Write-Host ""
    Start-Sleep -Seconds 2
    
    # Change to root directory and start
    Set-Location $rootDir
    python start_dev.py
} else {
    Write-Host ""
    Write-Host "To start manually, run:" -ForegroundColor Cyan
    Write-Host "  cd '$rootDir'" -ForegroundColor White
    Write-Host "  python start_dev.py" -ForegroundColor White
    Write-Host ""
}
