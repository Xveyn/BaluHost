# BaluHost Dev-Storage Netzlaufwerk trennen
# Verwendung: .\unmount-dev-storage.ps1 [-DriveLetter "Z:"]

param(
    [string]$DriveLetter = "Z:"
)

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  BaluHost Dev-Storage Netzlaufwerk trennen" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Laufwerk: $DriveLetter" -ForegroundColor White
Write-Host ""

$removed = $false

# Prüfe ob Laufwerk existiert
if (-not (Test-Path $DriveLetter)) {
    Write-Host "[INFO] Laufwerk $DriveLetter ist nicht verbunden" -ForegroundColor Yellow
} else {
    # Versuche SUBST zu entfernen
    Write-Host "[SUBST] Entferne virtuelles Laufwerk..." -ForegroundColor Cyan
    $substResult = subst $DriveLetter /d 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[SUBST] Laufwerk getrennt" -ForegroundColor Green
        $removed = $true
    }
    
    # Versuche SMB-Verbindung zu trennen
    Write-Host "[SMB] Trenne Netzlaufwerk..." -ForegroundColor Cyan
    $netResult = net use $DriveLetter /delete /y 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[SMB] Netzlaufwerk getrennt" -ForegroundColor Green
        $removed = $true
    }
}

# Entferne SMB-Freigabe
Write-Host "[SMB] Entferne Freigabe..." -ForegroundColor Cyan
$shareName = "BaluHostNAS"
$share = Get-SmbShare -Name $shareName -ErrorAction SilentlyContinue
if ($share) {
    Remove-SmbShare -Name $shareName -Force 2>$null
    if ($?) {
        Write-Host "[SMB] Freigabe '$shareName' entfernt" -ForegroundColor Green
        $removed = $true
    }
} else {
    Write-Host "[SMB] Keine Freigabe gefunden" -ForegroundColor Gray
}

Write-Host ""
if ($removed) {
    Write-Host "=====================================================" -ForegroundColor Green
    Write-Host "  SUCCESS - Netzlaufwerk getrennt" -ForegroundColor Green
    Write-Host "=====================================================" -ForegroundColor Green
} else {
    Write-Host "=====================================================" -ForegroundColor Yellow
    Write-Host "  Keine aktiven Verbindungen gefunden" -ForegroundColor Yellow
    Write-Host "=====================================================" -ForegroundColor Yellow
}
Write-Host ""
