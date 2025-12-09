# BaluHost Netzwerk-Diagnose
# Zeigt alle relevanten Informationen fuer Heimnetz-Zugriff

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "   BaluHost Netzwerk-Diagnose" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Server Status
Write-Host "[1] Server Status" -ForegroundColor Yellow
Write-Host "---" -ForegroundColor Gray

$serverProcess = netstat -ano | Select-String ":8000" | Select-String "ABHOREN"
if ($serverProcess) {
    Write-Host "  Status: LAEUFT" -ForegroundColor Green
    $serverProcess | ForEach-Object {
        if ($_ -match "0\.0\.0\.0:8000") {
            Write-Host "  Bind: 0.0.0.0:8000 (alle Interfaces) - OK" -ForegroundColor Green
        } elseif ($_ -match "127\.0\.0\.1:8000") {
            Write-Host "  Bind: 127.0.0.1:8000 (nur localhost) - PROBLEM!" -ForegroundColor Red
            Write-Host "  Loesung: Server muss auf 0.0.0.0 binden" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "  Status: LAEUFT NICHT" -ForegroundColor Red
    Write-Host "  Loesung: python start_dev.py ausfuehren" -ForegroundColor Yellow
}

Write-Host ""

# 2. Netzwerk-Konfiguration
Write-Host "[2] Netzwerk-Konfiguration" -ForegroundColor Yellow
Write-Host "---" -ForegroundColor Gray

$profiles = Get-NetConnectionProfile
foreach ($profile in $profiles) {
    Write-Host "  Name: $($profile.Name)" -ForegroundColor White
    
    if ($profile.NetworkCategory -eq "Private") {
        Write-Host "  Profil: Private - OK" -ForegroundColor Green
    } else {
        Write-Host "  Profil: $($profile.NetworkCategory) - PROBLEM!" -ForegroundColor Red
        Write-Host "  Loesung: Als Admin ausfuehren:" -ForegroundColor Yellow
        Write-Host "    Set-NetConnectionProfile -NetworkCategory Private" -ForegroundColor Gray
    }
    
    Write-Host "  Interface: $($profile.InterfaceAlias)" -ForegroundColor White
}

Write-Host ""

# 3. IP-Adressen
Write-Host "[3] IP-Adressen" -ForegroundColor Yellow
Write-Host "---" -ForegroundColor Gray

$ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notmatch 'Loopback'}

$validIP = $null
foreach ($ip in $ips) {
    $isValid = $ip.IPAddress -notmatch "^169\.254\."
    
    if ($isValid) {
        Write-Host "  $($ip.IPAddress) ($($ip.InterfaceAlias)) - VERWENDBAR" -ForegroundColor Green
        if (-not $validIP) { $validIP = $ip.IPAddress }
    } else {
        Write-Host "  $($ip.IPAddress) ($($ip.InterfaceAlias)) - Link-local (nicht nutzbar)" -ForegroundColor Gray
    }
}

if (-not $validIP) {
    Write-Host "  PROBLEM: Keine gueltige IP gefunden!" -ForegroundColor Red
    Write-Host "  Loesung: Mit WLAN/LAN verbinden" -ForegroundColor Yellow
}

Write-Host ""

# 4. Firewall-Regeln
Write-Host "[4] Firewall-Regeln" -ForegroundColor Yellow
Write-Host "---" -ForegroundColor Gray

$rules = Get-NetFirewallRule -DisplayName "BaluHost*" -ErrorAction SilentlyContinue

if ($rules) {
    foreach ($rule in $rules) {
        $status = if ($rule.Enabled -eq "True") { "AKTIV" } else { "INAKTIV" }
        $color = if ($rule.Enabled -eq "True") { "Green" } else { "Red" }
        
        Write-Host "  $($rule.DisplayName): $status" -ForegroundColor $color
        Write-Host "    Profile: $($rule.Profile)" -ForegroundColor Gray
    }
} else {
    Write-Host "  PROBLEM: Keine Regeln gefunden!" -ForegroundColor Red
    Write-Host "  Loesung: .\scripts\heimnetz_fix.ps1 als Admin ausfuehren" -ForegroundColor Yellow
}

Write-Host ""

# 5. Port-Erreichbarkeit testen
if ($validIP) {
    Write-Host "[5] Port-Erreichbarkeit" -ForegroundColor Yellow
    Write-Host "---" -ForegroundColor Gray
    
    Write-Host "  Teste Port 5173 (Frontend) auf $validIP..." -ForegroundColor White
    
    try {
        $test5173 = Test-NetConnection -ComputerName $validIP -Port 5173 -WarningAction SilentlyContinue
        
        if ($test5173.TcpTestSucceeded) {
            Write-Host "  Port 5173 (Frontend): ERREICHBAR" -ForegroundColor Green
        } else {
            Write-Host "  Port 5173 (Frontend): NICHT ERREICHBAR" -ForegroundColor Red
        }
    } catch {
        Write-Host "  Port 5173 (Frontend): TEST FEHLGESCHLAGEN" -ForegroundColor Red
    }
    
    Write-Host "  Teste Port 8000 (Backend) auf $validIP..." -ForegroundColor White
    
    try {
        $test8000 = Test-NetConnection -ComputerName $validIP -Port 8000 -WarningAction SilentlyContinue
        
        if ($test8000.TcpTestSucceeded) {
            Write-Host "  Port 8000 (Backend): ERREICHBAR" -ForegroundColor Green
        } else {
            Write-Host "  Port 8000 (Backend): NICHT ERREICHBAR" -ForegroundColor Red
        }
    } catch {
        Write-Host "  Port 8000 (Backend): TEST FEHLGESCHLAGEN" -ForegroundColor Red
    }
    
    Write-Host ""
}

# 6. Zusammenfassung
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "   ZUGRIFFS-INFORMATIONEN" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

if ($validIP -and $serverProcess) {
    Write-Host "VON DIESEM PC:" -ForegroundColor Green
    Write-Host "  Weboberflaeche: https://localhost:5173" -ForegroundColor White
    Write-Host "  API Docs:       https://localhost:8000/docs" -ForegroundColor White
    Write-Host ""
    
    Write-Host "VON ANDEREN GERAETEN IM NETZWERK:" -ForegroundColor Green
    Write-Host "  Weboberflaeche: https://$validIP:5173" -ForegroundColor White
    Write-Host "  API Docs:       https://$validIP:8000/docs" -ForegroundColor White
    Write-Host ""
    
    Write-Host "WEBDAV NETZLAUFWERK:" -ForegroundColor Green
    Write-Host "  Windows: \\$validIP@8080\webdav" -ForegroundColor White
    Write-Host "  Mac/Linux: http://$validIP:8080/webdav" -ForegroundColor White
    Write-Host ""
    
    Write-Host "LOGIN:" -ForegroundColor Green
    Write-Host "  Username: admin" -ForegroundColor White
    Write-Host "  Password: changeme" -ForegroundColor White
    Write-Host ""
    
    Write-Host "================================================" -ForegroundColor Green
    Write-Host ""
    
    # QR-Code Text generieren (kann mit Online-Tool in QR umgewandelt werden)
    Write-Host "TIPP: Erstelle einen QR-Code mit dieser URL:" -ForegroundColor Yellow
    Write-Host "  https://$validIP:8000" -ForegroundColor Cyan
    Write-Host "  Nutze z.B.: https://qr-code-generator.com/" -ForegroundColor Gray
    
} else {
    Write-Host "PROBLEM: Server nicht erreichbar" -ForegroundColor Red
    Write-Host ""
    
    if (-not $serverProcess) {
        Write-Host "FEHLT: Server laeuft nicht" -ForegroundColor Yellow
        Write-Host "  -> python start_dev.py" -ForegroundColor White
    }
    
    if (-not $validIP) {
        Write-Host "FEHLT: Keine gueltige Netzwerk-IP" -ForegroundColor Yellow
        Write-Host "  -> Mit WLAN/LAN verbinden" -ForegroundColor White
    }
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Test-Vorschlag
if ($validIP -and $serverProcess) {
    Write-Host "NAECHSTER SCHRITT:" -ForegroundColor Cyan
    Write-Host "1. Nimm dein Smartphone/Tablet" -ForegroundColor White
    Write-Host "2. Verbinde mit dem GLEICHEN WLAN" -ForegroundColor White
    Write-Host "3. Oeffne Browser und gehe zu:" -ForegroundColor White
    Write-Host "   https://$validIP:8000" -ForegroundColor Green
    Write-Host "4. Akzeptiere Zertifikatswarnung (Erweitert -> Fortfahren)" -ForegroundColor White
    Write-Host "5. Login: admin / changeme" -ForegroundColor White
    Write-Host ""
    
    $open = Read-Host "Browser jetzt oeffnen? (j/n)"
    if ($open -eq 'j' -or $open -eq 'y') {
        Start-Process "https://$validIP:8000"
    }
}

Write-Host ""
