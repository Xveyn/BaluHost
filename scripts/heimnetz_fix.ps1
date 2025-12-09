# Quick Fix: Heimnetz-Zugriff aktivieren
# Fuehre dieses Skript als Administrator aus!

Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host " BaluHost Heimnetz-Zugriff Fix" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# 1. Pruefe Admin-Rechte
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "FEHLER: Administrator-Rechte erforderlich!" -ForegroundColor Red
    Write-Host ""
    Write-Host "So funktionierts:" -ForegroundColor Yellow
    Write-Host "1. PowerShell als Administrator oeffnen (Rechtsklick -> Als Admin ausfuehren)" -ForegroundColor White
    Write-Host "2. Dieses Skript erneut ausfuehren" -ForegroundColor White
    Write-Host ""
    pause
    exit 1
}

Write-Host "Administrator: OK" -ForegroundColor Green
Write-Host ""

# 2. Netzwerkprofil pruefen
Write-Host "Pruefe Netzwerkprofil..." -ForegroundColor Yellow
$profile = Get-NetConnectionProfile | Where-Object {$_.IPv4Connectivity -ne "NoTraffic"} | Select-Object -First 1

if ($profile) {
    Write-Host "  Netzwerk: $($profile.Name)" -ForegroundColor White
    Write-Host "  Profil: $($profile.NetworkCategory)" -ForegroundColor $(if ($profile.NetworkCategory -eq "Private") { "Green" } else { "Red" })
    
    if ($profile.NetworkCategory -eq "Public") {
        Write-Host ""
        Write-Host "PROBLEM GEFUNDEN: Netzwerk ist auf 'Public' gesetzt!" -ForegroundColor Red
        Write-Host "Bei Public Networks blockiert Windows alle eingehenden Verbindungen." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "LOESUNG: Aendere zu 'Private' (Heimnetzwerk)" -ForegroundColor Green
        Write-Host ""
        
        $change = Read-Host "Zu 'Private' aendern? (j/n)"
        if ($change -eq 'j' -or $change -eq 'J' -or $change -eq 'y' -or $change -eq 'Y') {
            try {
                Set-NetConnectionProfile -InterfaceIndex $profile.InterfaceIndex -NetworkCategory Private
                Write-Host ""
                Write-Host "ERFOLG: Netzwerk ist jetzt 'Private'!" -ForegroundColor Green
            } catch {
                Write-Host ""
                Write-Host "FEHLER beim Aendern: $_" -ForegroundColor Red
                Write-Host ""
                Write-Host "Manuell aendern:" -ForegroundColor Yellow
                Write-Host "Windows Einstellungen -> Netzwerk -> Netzwerkprofil -> Privat" -ForegroundColor White
            }
        } else {
            Write-Host ""
            Write-Host "Ohne Private-Profil funktioniert der Heimnetz-Zugriff NICHT!" -ForegroundColor Red
            Write-Host ""
            pause
            exit 1
        }
    } else {
        Write-Host "  OK: Profil ist bereits 'Private'" -ForegroundColor Green
    }
} else {
    Write-Host "  WARNUNG: Kein aktives Netzwerk gefunden" -ForegroundColor Yellow
}

Write-Host ""

# 3. Firewall-Regeln erstellen
Write-Host "Erstelle Firewall-Regeln..." -ForegroundColor Yellow

# Alte Regeln entfernen
Get-NetFirewallRule -DisplayName "BaluHost*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule

$rules = @(
    @{Name="BaluHost-Frontend"; Port=5173; Protocol="TCP"; Desc="BaluHost Web UI (HTTPS)"},
    @{Name="BaluHost-API-Server"; Port=8000; Protocol="TCP"; Desc="BaluHost Backend API (HTTPS)"},
    @{Name="BaluHost-WebDAV-Server"; Port=8080; Protocol="TCP"; Desc="BaluHost WebDAV"},
    @{Name="BaluHost-mDNS-Discovery"; Port=5353; Protocol="UDP"; Desc="BaluHost mDNS"}
)

$success = 0
foreach ($rule in $rules) {
    try {
        New-NetFirewallRule -DisplayName $rule.Name `
                            -Description $rule.Desc `
                            -Direction Inbound `
                            -Protocol $rule.Protocol `
                            -LocalPort $rule.Port `
                            -Action Allow `
                            -Profile Private,Domain `
                            -Enabled True | Out-Null
        Write-Host "  OK: Port $($rule.Port)/$($rule.Protocol) ($($rule.Desc))" -ForegroundColor Green
        $success++
    } catch {
        Write-Host "  FEHLER: Port $($rule.Port)" -ForegroundColor Red
    }
}

Write-Host ""

if ($success -eq 4) {
    Write-Host "=====================================" -ForegroundColor Green
    Write-Host " ALLES ERFOLGREICH KONFIGURIERT!" -ForegroundColor Green
    Write-Host "=====================================" -ForegroundColor Green
} else {
    Write-Host "WARNUNG: Nicht alle Regeln konnten erstellt werden ($success/4)" -ForegroundColor Yellow
}

Write-Host ""

# 4. IP-Adresse anzeigen
$localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notmatch 'Loopback'} | Select-Object -First 1).IPAddress

Write-Host "DEINE IP-ADRESSE: $localIP" -ForegroundColor Cyan
Write-Host ""
Write-Host "Zugriff von anderen Geraeten:" -ForegroundColor Cyan
Write-Host "  Weboberflaeche: https://$localIP:5173" -ForegroundColor White
Write-Host "  API Docs:       https://$localIP:8000/docs" -ForegroundColor White
Write-Host "  Login:          admin / changeme" -ForegroundColor White
Write-Host ""
Write-Host "Netzlaufwerk einbinden (Windows):" -ForegroundColor Cyan
Write-Host "  \\$localIP@8080\webdav" -ForegroundColor White
Write-Host ""

# 5. Server-Status pruefen
Write-Host "Pruefe Server-Status..." -ForegroundColor Yellow
$frontend = netstat -ano | findstr ":5173" | findstr "ABHOREN"
$backend = netstat -ano | findstr ":8000" | findstr "ABHOREN"

if ($frontend -and $backend) {
    Write-Host "  OK: Server laeuft (Frontend Port 5173, Backend Port 8000)" -ForegroundColor Green
} elseif ($backend) {
    Write-Host "  WARNUNG: Nur Backend laeuft (Port 8000)" -ForegroundColor Yellow
    Write-Host "  Frontend (Port 5173) fehlt - starte: python start_dev.py" -ForegroundColor Yellow
} else {
    Write-Host "  WARNUNG: Server laeuft NICHT!" -ForegroundColor Red
    Write-Host "  Starte den Server mit: python start_dev.py" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=====================================" -ForegroundColor Green
Write-Host ""
Write-Host "FERTIG! Teste jetzt den Zugriff von einem anderen Geraet:" -ForegroundColor Green
Write-Host "  https://$localIP:8000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Hinweis: Browser zeigt Zertifikatswarnung -> das ist normal!" -ForegroundColor Yellow
Write-Host "Klicke auf 'Erweitert' -> 'Weiter zu $localIP'" -ForegroundColor Yellow
Write-Host ""

pause
