# mkcert Mobile Setup Guide

## ✅ Server Setup (Erledigt)

Die lokale Certificate Authority (CA) wurde erfolgreich installiert:
- **Tool:** mkcert v1.4.4
- **CA installiert:** Windows Certificate Store
- **Zertifikate:** `dev-certs/cert.pem` + `key.pem`
- **Gültig für:** localhost, 127.0.0.1, 192.168.178.21, ::1
- **Gültigkeit:** Bis 7. März 2028 (3 Jahre)

## 📱 Mobile Geräte Setup

Um auf deinem Handy/Tablet keine Zertifikatswarnungen mehr zu sehen, musst du die CA einmalig installieren:

### Android

1. **CA-Zertifikat auf Handy kopieren**
   ```powershell
   # Auf dem PC ausführen:
   # CA-Zertifikat liegt hier:
   $env:LOCALAPPDATA\mkcert\rootCA.pem
   
   # Per E-Mail an dich selbst senden oder via USB kopieren
   ```

2. **Zertifikat installieren**
   - Einstellungen → Sicherheit → Verschlüsselung & Anmeldedaten
   - "Zertifikat installieren" oder "Von SD-Karte installieren"
   - `rootCA.pem` auswählen
   - Name: "BaluHost mkcert CA"
   - Verwendung: VPN & Apps

3. **Fertig!** Browser vertraut nun allen BaluHost-Zertifikaten

### iOS (iPhone/iPad)

1. **CA-Zertifikat auf iPhone kopieren**
   - CA per E-Mail an dich selbst senden
   - Oder via AirDrop vom Mac

2. **Profil installieren**
   - E-Mail öffnen, Anhang antippen
   - "Profil wird heruntergeladen"
   - Einstellungen → Profil heruntergeladen
   - "Installieren" antippen
   - Passcode eingeben

3. **Zertifikat vertrauen**
   - Einstellungen → Allgemein → Info
   - Ganz nach unten scrollen: "Zertifikatsvertrauenseinstellungen"
   - mkcert CA aktivieren (grüner Schalter)

4. **Fertig!** Safari vertraut nun allen BaluHost-Zertifikaten

## 🔍 CA-Zertifikat finden

Das Root-Zertifikat liegt hier:
```
Windows: C:\Users\<Username>\AppData\Local\mkcert\rootCA.pem
macOS:   ~/Library/Application Support/mkcert/rootCA.pem
Linux:   ~/.local/share/mkcert/rootCA.pem
```

## 📤 CA exportieren (für andere Geräte)

```powershell
# Per E-Mail versenden
$caPath = "$env:LOCALAPPDATA\mkcert\rootCA.pem"
Start-Process "mailto:?subject=BaluHost%20CA&body=Anhang:%20$caPath"

# Oder auf Desktop kopieren
Copy-Item "$env:LOCALAPPDATA\mkcert\rootCA.pem" "$env:USERPROFILE\Desktop\baluhost-ca.pem"
```

## ✅ Testen

Nach CA-Installation:
1. Öffne auf dem mobilen Gerät: `https://192.168.178.21:5173`
2. **Kein Zertifikatsfehler** → Alles funktioniert! ✅
3. Grünes Schloss im Browser → Vertrauenswürdige Verbindung

## 🔒 Sicherheitshinweise

- **Private Key schützen:** `rootCA-key.pem` niemals weitergeben!
- **Nur im Heimnetz:** Diese CA ist für interne Nutzung
- **Nicht für öffentliche Server:** Nur deine Geräte vertrauen dieser CA
- **Backup erstellen:** CA-Zertifikat sichern, falls PC neu installiert wird

## 🔄 Zertifikate erneuern

Falls Zertifikate ablaufen (März 2028):

```powershell
cd "f:\Programme (x86)\Baluhost\dev-certs"
& "$env:USERPROFILE\mkcert\mkcert.exe" localhost 127.0.0.1 192.168.178.21 ::1
Move-Item -Force "localhost+3.pem" "cert.pem"
Move-Item -Force "localhost+3-key.pem" "key.pem"
```

Dann BaluHost neu starten.

## 🆘 Troubleshooting

### "Zertifikat nicht vertrauenswürdig" auf Mobile

1. Prüfe ob CA installiert ist (siehe oben)
2. Stelle sicher, dass CA auch **aktiviert** ist (iOS: Vertrauenseinstellungen)
3. Browser-Cache leeren
4. Gerät neu starten

### Firefox unterstützt mkcert nicht

Firefox nutzt eigenen Certificate Store. Lösung:
- Chrome/Edge/Safari verwenden (diese nutzen System-Store)
- Oder Firefox manuell konfigurieren (kompliziert)

## 📝 Vorteile gegenüber Self-Signed

| Feature | Self-Signed | mkcert |
|---------|-------------|--------|
| Zertifikatswarnungen | ❌ Immer | ✅ Keine |
| Browser-Vertrauen | ❌ Manuell | ✅ Automatisch |
| Mobile Setup | ❌ Kompliziert | ✅ Einmalig einfach |
| Gültigkeit | 365 Tage | 825 Tage |
| Erneuerung | Manuell | Ein Befehl |

---

**Status:** ✅ mkcert installiert und aktiv  
**Nächster Schritt:** CA auf mobilen Geräten installieren (siehe oben)
