# BaluHost Dev-Storage als Netzlaufwerk mounten
# Verwendung:
#   .\mount-dev-storage.ps1                    # Einfaches SUBST-Mapping
#   .\mount-dev-storage.ps1 -UseSMB            # SMB-Freigabe (wie in Produktion)
#   .\mount-dev-storage.ps1 -DriveLetter "Y:"  # Anderen Laufwerksbuchstaben verwenden

param(
    [string]$DriveLetter = "Z:",
    [switch]$UseSMB = $false,
    [switch]$OpenExplorer = $true
)

# Pfad zum Dev-Storage
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootPath = Split-Path -Parent $scriptPath
$devStoragePath = Join-Path $rootPath "backend\dev-storage"
$devStoragePath = [System.IO.Path]::GetFullPath($devStoragePath)

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  BaluHost Dev-Storage Netzlaufwerk Setup" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pfad:      $devStoragePath" -ForegroundColor White
Write-Host "Laufwerk:  $DriveLetter" -ForegroundColor White
Write-Host "Methode:   $(if ($UseSMB) { 'SMB/CIFS (Produktions-Mode)' } else { 'SUBST (Einfach)' })" -ForegroundColor White
Write-Host ""

# Prüfe ob Dev-Storage existiert
if (-not (Test-Path $devStoragePath)) {
    Write-Host "[ERROR] Dev-Storage nicht gefunden!" -ForegroundColor Red
    Write-Host "        Erwartet: $devStoragePath" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Tipp: Starte zuerst 'python start_dev.py' um den Dev-Storage zu initialisieren" -ForegroundColor Yellow
    exit 1
}

# Entferne existierendes Mapping
if (Test-Path $DriveLetter) {
    Write-Host "[INFO] Laufwerk $DriveLetter bereits vorhanden - entferne..." -ForegroundColor Yellow
    subst $DriveLetter /d 2>$null
    net use $DriveLetter /delete /y 2>$null
    Start-Sleep -Seconds 1
}

if ($UseSMB) {
    # ===== SMB-Freigabe Methode (wie in Produktion) =====
    Write-Host "[SMB] Erstelle Windows-Freigabe..." -ForegroundColor Cyan
    
    $shareName = "BaluHostNAS"
    
    # Prüfe ob bereits vorhanden
    $existingShare = Get-SmbShare -Name $shareName -ErrorAction SilentlyContinue
    if ($existingShare) {
        Write-Host "[SMB] Entferne existierende Freigabe..." -ForegroundColor Yellow
        Remove-SmbShare -Name $shareName -Force
    }
    
    try {
        # Erstelle SMB-Freigabe
        New-SmbShare -Name $shareName -Path $devStoragePath -FullAccess "Everyone" -ErrorAction Stop | Out-Null
        Grant-SmbShareAccess -Name $shareName -AccountName "Everyone" -AccessRight Full -Force -ErrorAction Stop | Out-Null
        
        Write-Host "[SMB] Freigabe '$shareName' erstellt" -ForegroundColor Green
        Write-Host "[SMB] Verbinde Netzlaufwerk..." -ForegroundColor Cyan
        
        # Verbinde als Netzlaufwerk
        net use $DriveLetter "\\localhost\$shareName" /persistent:no 2>$null
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host ""
            Write-Host "=====================================================" -ForegroundColor Green
            Write-Host "  SUCCESS - SMB Netzlaufwerk verbunden!" -ForegroundColor Green
            Write-Host "=====================================================" -ForegroundColor Green
            Write-Host ""
            Write-Host "Laufwerk:  $DriveLetter" -ForegroundColor White
            Write-Host "Freigabe:  \\localhost\$shareName" -ForegroundColor White
            Write-Host "Pfad:      $devStoragePath" -ForegroundColor White
            Write-Host ""
            Write-Host "Zum Entfernen: .\unmount-dev-storage.ps1" -ForegroundColor Yellow
            Write-Host ""
            
            if ($OpenExplorer) {
                Start-Process explorer $DriveLetter
            }
        } else {
            throw "net use fehlgeschlagen"
        }
        
    } catch {
        Write-Host ""
        Write-Host "[ERROR] SMB-Fehler: $_" -ForegroundColor Red
        Write-Host ""
        Write-Host "Tipps:" -ForegroundColor Yellow
        Write-Host "  1. Script als Administrator ausführen" -ForegroundColor Yellow
        Write-Host "  2. Firewall-Einstellungen prüfen" -ForegroundColor Yellow
        Write-Host "  3. Alternativ ohne -UseSMB verwenden" -ForegroundColor Yellow
        Write-Host ""
        
        # Cleanup
        Remove-SmbShare -Name $shareName -Force 2>$null
        exit 1
    }
    
} else {
    # ===== SUBST Methode (einfach und schnell) =====
    Write-Host "[SUBST] Erstelle virtuelles Laufwerk..." -ForegroundColor Cyan
    
    $substResult = subst $DriveLetter $devStoragePath 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "=====================================================" -ForegroundColor Green
        Write-Host "  SUCCESS - Virtuelles Laufwerk erstellt!" -ForegroundColor Green
        Write-Host "=====================================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "Laufwerk:  $DriveLetter" -ForegroundColor White
        Write-Host "Pfad:      $devStoragePath" -ForegroundColor White
        Write-Host ""
        Write-Host "Zum Entfernen: .\unmount-dev-storage.ps1" -ForegroundColor Yellow
        Write-Host ""
        
        if ($OpenExplorer) {
            Start-Process explorer $DriveLetter
        }
    } else {
        Write-Host ""
        Write-Host "[ERROR] SUBST fehlgeschlagen: $substResult" -ForegroundColor Red
        Write-Host ""
        Write-Host "Tipps:" -ForegroundColor Yellow
        Write-Host "  1. Script als Administrator ausführen" -ForegroundColor Yellow
        Write-Host "  2. Prüfe ob Laufwerksbuchstabe verfügbar ist" -ForegroundColor Yellow
        Write-Host "  3. Verwende anderen Buchstaben: -DriveLetter Y:" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
}
