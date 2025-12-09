# BaluHost Firewall Configuration for Home Network
# Opens necessary ports for local network access

Write-Host "=== BaluHost Firewall Configuration ===" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script requires Administrator privileges!" -ForegroundColor Red
    Write-Host "Please run PowerShell as Administrator and try again." -ForegroundColor Yellow
    exit 1
}

# Define firewall rules
$firewallRules = @(
    @{
        Name = "BaluHost-API-Server"
        Port = 8000
        Protocol = "TCP"
        Description = "BaluHost API Server (HTTPS)"
    },
    @{
        Name = "BaluHost-WebDAV-Server"
        Port = 8080
        Protocol = "TCP"
        Description = "BaluHost WebDAV Network Drive"
    },
    @{
        Name = "BaluHost-mDNS-Discovery"
        Port = 5353
        Protocol = "UDP"
        Description = "BaluHost mDNS/Bonjour Service Discovery"
    }
)

Write-Host "Configuring Windows Firewall rules..." -ForegroundColor Yellow
Write-Host ""

foreach ($rule in $firewallRules) {
    # Remove existing rule if present
    $existingRule = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
    if ($existingRule) {
        Write-Host "  Removing old rule: $($rule.Name)" -ForegroundColor Gray
        Remove-NetFirewallRule -DisplayName $rule.Name
    }
    
    # Create new rule
    try {
        New-NetFirewallRule -DisplayName $rule.Name `
                            -Description $rule.Description `
                            -Direction Inbound `
                            -Protocol $rule.Protocol `
                            -LocalPort $rule.Port `
                            -Action Allow `
                            -Profile Private,Domain `
                            -Enabled True | Out-Null
        
        Write-Host "  ✓ $($rule.Name) - Port $($rule.Port)/$($rule.Protocol)" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ Failed to create rule: $($rule.Name)" -ForegroundColor Red
        Write-Host "    Error: $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== Configuration Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Firewall Rules Status:" -ForegroundColor Cyan

# Show all BaluHost rules
$baluRules = Get-NetFirewallRule -DisplayName "BaluHost*" -ErrorAction SilentlyContinue
if ($baluRules) {
    foreach ($rule in $baluRules) {
        $enabled = if ($rule.Enabled -eq "True") { "✓ Enabled" } else { "✗ Disabled" }
        Write-Host "  $($rule.DisplayName): $enabled" -ForegroundColor $(if ($rule.Enabled -eq "True") { "Green" } else { "Red" })
    }
} else {
    Write-Host "  No BaluHost rules found!" -ForegroundColor Red
}

Write-Host ""
Write-Host "Network Access Information:" -ForegroundColor Cyan

# Get local IP addresses
$localIPs = Get-NetIPAddress -AddressFamily IPv4 | 
            Where-Object {$_.InterfaceAlias -notmatch 'Loopback' -and $_.IPAddress -ne '127.0.0.1'} |
            Select-Object -ExpandProperty IPAddress

if ($localIPs) {
    Write-Host "  Your local IP address(es):" -ForegroundColor Yellow
    foreach ($ip in $localIPs) {
        Write-Host "    - $ip" -ForegroundColor White
    }
    
    Write-Host ""
    Write-Host "Access URLs (from other devices in your network):" -ForegroundColor Cyan
    foreach ($ip in $localIPs | Select-Object -First 1) {
        Write-Host "  Web Interface: https://$ip:8000" -ForegroundColor White
        Write-Host "  WebDAV Drive:  \\$ip@8080\webdav" -ForegroundColor White
    }
} else {
    Write-Host "  Could not determine local IP address" -ForegroundColor Red
}

Write-Host ""
Write-Host "Notes:" -ForegroundColor Yellow
Write-Host "  • Rules are only active on Private and Domain networks" 
Write-Host "  • Public networks are blocked by default (for security)"
Write-Host "  • If you can't connect, check your network profile"
Write-Host "  • Run 'Get-NetConnectionProfile' to see your network type"
Write-Host ""

# Offer to change network profile if needed
$currentProfile = Get-NetConnectionProfile | Where-Object {$_.IPv4Connectivity -eq "Internet" -or $_.IPv4Connectivity -eq "LocalNetwork"}
if ($currentProfile -and $currentProfile.NetworkCategory -eq "Public") {
    Write-Host "WARNING: Your network is set to 'Public'" -ForegroundColor Red
    Write-Host "BaluHost will not be accessible from other devices!" -ForegroundColor Red
    Write-Host ""
    $change = Read-Host "Change network to 'Private' now? (y/n)"
    if ($change -eq 'y' -or $change -eq 'Y') {
        try {
            Set-NetConnectionProfile -InterfaceIndex $currentProfile.InterfaceIndex -NetworkCategory Private
            Write-Host "✓ Network profile changed to Private" -ForegroundColor Green
        } catch {
            Write-Host "✗ Failed to change network profile: $_" -ForegroundColor Red
            Write-Host "  You can change it manually in Windows Settings" -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host "Ready to start BaluHost!" -ForegroundColor Green
Write-Host "Run: python start_dev.py" -ForegroundColor Cyan
