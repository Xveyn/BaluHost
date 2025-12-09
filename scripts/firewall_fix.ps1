# BaluHost Firewall Quick Fix
# Run as Administrator!

Write-Host ""
Write-Host "=== BaluHost Firewall Configuration ===" -ForegroundColor Cyan
Write-Host ""

# Check Admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: Run as Administrator!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Right-click PowerShell -> Run as Administrator" -ForegroundColor Yellow
    Write-Host "Then run this script again." -ForegroundColor Yellow
    pause
    exit 1
}

# Remove old rules
Write-Host "Removing old rules..." -ForegroundColor Yellow
Get-NetFirewallRule -DisplayName "BaluHost*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule

# Create new rules
Write-Host "Creating firewall rules..." -ForegroundColor Yellow

try {
    New-NetFirewallRule -DisplayName "BaluHost-API-Server" `
                        -Description "BaluHost API Server (HTTPS)" `
                        -Direction Inbound `
                        -Protocol TCP `
                        -LocalPort 8000 `
                        -Action Allow `
                        -Profile Private,Domain `
                        -Enabled True | Out-Null
    Write-Host "  OK: Port 8000 (API/HTTPS)" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: Port 8000" -ForegroundColor Red
}

try {
    New-NetFirewallRule -DisplayName "BaluHost-WebDAV-Server" `
                        -Description "BaluHost WebDAV Network Drive" `
                        -Direction Inbound `
                        -Protocol TCP `
                        -LocalPort 8080 `
                        -Action Allow `
                        -Profile Private,Domain `
                        -Enabled True | Out-Null
    Write-Host "  OK: Port 8080 (WebDAV)" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: Port 8080" -ForegroundColor Red
}

try {
    New-NetFirewallRule -DisplayName "BaluHost-mDNS-Discovery" `
                        -Description "BaluHost mDNS Service Discovery" `
                        -Direction Inbound `
                        -Protocol UDP `
                        -LocalPort 5353 `
                        -Action Allow `
                        -Profile Private,Domain `
                        -Enabled True | Out-Null
    Write-Host "  OK: Port 5353 (mDNS)" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: Port 5353" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Configuration Complete ===" -ForegroundColor Green
Write-Host ""

# Show IP
$localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notmatch 'Loopback'} | Select-Object -First 1).IPAddress

Write-Host "Your IP Address: $localIP" -ForegroundColor Cyan
Write-Host ""
Write-Host "Access from other devices:" -ForegroundColor Cyan
Write-Host "  https://$localIP:8000" -ForegroundColor White
Write-Host ""

# Check network profile
$profile = Get-NetConnectionProfile | Where-Object {$_.IPv4Connectivity -ne "NoTraffic"} | Select-Object -First 1
if ($profile) {
    Write-Host "Network Profile: $($profile.NetworkCategory)" -ForegroundColor $(if ($profile.NetworkCategory -eq "Private") { "Green" } else { "Red" })
    
    if ($profile.NetworkCategory -eq "Public") {
        Write-Host ""
        Write-Host "WARNING: Network is 'Public' - Other devices CANNOT connect!" -ForegroundColor Red
        Write-Host ""
        $change = Read-Host "Change to 'Private' now? (y/n)"
        if ($change -eq 'y') {
            Set-NetConnectionProfile -InterfaceIndex $profile.InterfaceIndex -NetworkCategory Private
            Write-Host "OK: Network changed to Private" -ForegroundColor Green
        }
    }
}

Write-Host ""
Write-Host "Done! Server should now be accessible in your home network." -ForegroundColor Green
pause
