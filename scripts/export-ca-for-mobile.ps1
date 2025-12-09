# Export mkcert CA for Mobile Devices
# This script helps you export the root CA certificate to install on mobile devices

$caPath = "$env:LOCALAPPDATA\mkcert\rootCA.pem"
$outputPath = "$env:USERPROFILE\Desktop\baluhost-ca.crt"

Write-Host "=== BaluHost mkcert CA Export ===" -ForegroundColor Cyan
Write-Host ""

# Check if CA exists
if (-not (Test-Path $caPath)) {
    Write-Host "❌ CA certificate not found at: $caPath" -ForegroundColor Red
    Write-Host "Run 'mkcert -install' first to create the CA." -ForegroundColor Yellow
    exit 1
}

# Copy CA to desktop with .crt extension (better for mobile)
Copy-Item $caPath $outputPath -Force

Write-Host "✅ CA certificate exported to:" -ForegroundColor Green
Write-Host "   $outputPath" -ForegroundColor White
Write-Host ""

Write-Host "📱 Next steps:" -ForegroundColor Cyan
Write-Host "   1. Transfer this file to your mobile device" -ForegroundColor White
Write-Host "      - Email it to yourself" -ForegroundColor Gray
Write-Host "      - Use USB/AirDrop" -ForegroundColor Gray
Write-Host "      - Upload to cloud storage" -ForegroundColor Gray
Write-Host ""
Write-Host "   2. Install on mobile:" -ForegroundColor White
Write-Host "      Android: Settings → Security → Install certificate" -ForegroundColor Gray
Write-Host "      iOS: Open file → Install Profile → Trust Certificate" -ForegroundColor Gray
Write-Host ""
Write-Host "   3. Access BaluHost:" -ForegroundColor White
Write-Host "      https://192.168.178.21:5173" -ForegroundColor Gray
Write-Host ""

# Offer to open file location
Write-Host "Press any key to open Desktop folder..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
Start-Process "explorer.exe" "/select,$outputPath"

Write-Host ""
Write-Host "✅ Done!" -ForegroundColor Green
