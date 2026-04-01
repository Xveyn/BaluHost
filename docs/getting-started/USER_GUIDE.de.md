# BaluHost Benutzerhandbuch

Willkommen bei BaluHost — Ihrem selbstgehosteten NAS-System. Diese Anleitung hilft Ihnen beim Einstieg.

## Inhaltsverzeichnis

- [Zugang](#zugang)
- [Ersteinrichtung (Setup-Wizard)](#ersteinrichtung-setup-wizard)
- [Dashboard](#dashboard)
- [Dateiverwaltung](#dateiverwaltung)
- [Dateifreigaben](#dateifreigaben)
- [Benutzerverwaltung (Admin)](#benutzerverwaltung-admin)
- [RAID-Verwaltung (Admin)](#raid-verwaltung-admin)
- [Systemüberwachung](#systemüberwachung)
- [VPN (WireGuard)](#vpn-wireguard)
- [Netzwerkzugriff (Samba & WebDAV)](#netzwerkzugriff-samba--webdav)
- [Mobile App & Desktop-Client](#mobile-app--desktop-client)
- [Benachrichtigungen](#benachrichtigungen)
- [Cloud-Import](#cloud-import)
- [Sicherheit](#sicherheit)
- [Fehlerbehebung](#fehlerbehebung)

---

## Zugang

BaluHost läuft auf Ihrem lokalen Server und ist über den Browser erreichbar:

- **Lokales Netzwerk:** `http://baluhost.local` (wenn mDNS konfiguriert) oder `http://<Server-IP>`
- **Unterwegs:** Über WireGuard-VPN (siehe [VPN](#vpn-wireguard))

Unterstützte Browser: Chrome, Firefox, Edge, Safari (aktuellste Version empfohlen).

## Ersteinrichtung (Setup-Wizard)

Beim ersten Start erscheint automatisch der Setup-Wizard. Er führt Sie durch die Grundkonfiguration:

**Pflichtschritte:**
1. **Administrator-Konto** — Benutzername und Passwort für den Admin festlegen
2. **Benutzer** — Weitere Benutzerkonten anlegen (optional, auch später möglich)
3. **RAID** — Festplatten-Arrays konfigurieren (kann übersprungen werden)
4. **Dateizugriff** — Samba (SMB) und/oder WebDAV aktivieren

**Optionale Schritte:**
- Dateifreigaben, VPN, Benachrichtigungen, Cloud-Import, Pi-hole, Desktop-Sync, Mobile App

Sie können optionale Schritte überspringen und später in den Einstellungen konfigurieren.

## Dashboard

Das Dashboard zeigt eine Übersicht Ihres Systems:

- **Speicherübersicht** — Gesamtkapazität, belegter/freier Speicher
- **RAID-Status** — Gesundheit der Arrays (Healthy, Degraded, Rebuilding)
- **Systemressourcen** — CPU, RAM, Netzwerk in Echtzeit
- **Letzte Aktivitäten** — Aktuelle Dateioperationen und Ereignisse

## Dateiverwaltung

### Navigation

- Klicken Sie auf Ordner, um hineinzunavigieren
- Breadcrumb-Navigation oben für schnelle Rückkehr
- Dateien zeigen Name, Größe und Änderungsdatum

### Hochladen

- **Drag & Drop:** Dateien direkt in den Dateimanager ziehen
- **Upload-Button:** Klicken Sie auf "Hochladen" und wählen Sie Dateien aus
- **Ordner-Upload:** Ganze Ordner hochladen
- **Chunked Upload:** Große Dateien werden automatisch in Teilen hochgeladen mit Fortschrittsanzeige

### Weitere Operationen

- **Neuer Ordner** — Erstellt einen Unterordner
- **Vorschau** — Klick auf eine Datei öffnet die Vorschau (Bilder, Videos, Audio, PDFs, Text, Code)
- **Herunterladen** — Download-Symbol neben jeder Datei
- **Umbenennen** — Über das Kontextmenü (Rechtsklick)
- **Löschen** — Über das Kontextmenü oder das Papierkorb-Symbol
- **Verschieben/Kopieren** — Dateien zwischen Ordnern verschieben oder kopieren

### Dateiversionierung

BaluHost führt eine Versionshistorie für Dateien. Bei Änderungen können Sie frühere Versionen wiederherstellen.

### Eigentümerschaft

- Jede Datei gehört dem Benutzer, der sie hochgeladen hat
- Nur der Eigentümer oder ein Admin kann Dateien ändern/löschen
- Admins haben Zugriff auf alle Dateien

## Dateifreigaben

### Öffentliche Links

1. Rechtsklick auf eine Datei → "Freigabe erstellen"
2. Wählen Sie Optionen: Ablaufdatum, Passwortschutz, Download-Limit
3. Den generierten Link teilen

### Benutzerfreigaben

- Dateien oder Ordner gezielt an andere BaluHost-Benutzer freigeben
- Freigegebene Dateien erscheinen unter "Für mich freigegeben"

## Benutzerverwaltung (Admin)

Admins können unter **Benutzerverwaltung** Konten verwalten:

- **Erstellen** — Benutzername, E-Mail, Passwort, Rolle (Admin/Benutzer)
- **Bearbeiten** — Daten ändern, Passwort zurücksetzen
- **Löschen** — Konto entfernen (Dateien bleiben erhalten)
- **2FA verwalten** — TOTP-Zwei-Faktor-Authentifizierung pro Benutzer aktivieren/deaktivieren

### Rollen

| Rolle | Zugriff |
|-------|---------|
| **Admin** | Voller Zugriff: alle Dateien, Benutzerverwaltung, RAID, System, VPN |
| **Benutzer** | Eigene Dateien, Freigaben, Einstellungen |

## RAID-Verwaltung (Admin)

Unter **RAID-Verwaltung** sehen Sie:

- Aktive RAID-Arrays mit Status (Healthy/Degraded/Rebuilding/Failed)
- Mitgliedsdatenträger und deren Zustand
- SMART-Gesundheitsdaten der Festplatten
- Resync-Fortschritt bei Rebuilds

### RAID-Status

| Status | Bedeutung | Handlung |
|--------|-----------|----------|
| Healthy | Alle Disks OK | Keine |
| Degraded | Disk ausgefallen, Array läuft noch | Disk ersetzen & Rebuild starten |
| Rebuilding | Wiederherstellung läuft | Abwarten, Performance reduziert |
| Failed | Array nicht betriebsfähig | Dringende Maßnahmen erforderlich |

## Systemüberwachung

Die **Systemüberwachung** zeigt Echtzeit-Daten:

- **CPU** — Auslastung, Frequenz, Temperatur (pro Thread)
- **RAM** — Belegung und Verfügbarkeit
- **Netzwerk** — Download/Upload-Geschwindigkeit
- **Disk I/O** — Lese-/Schreibgeschwindigkeit, IOPS
- **SMART** — Festplattengesundheit, Temperatur, Betriebsstunden

Historische Daten werden als Diagramme dargestellt. Die Retention ist konfigurierbar.

## VPN (WireGuard)

BaluHost integriert WireGuard für sicheren Fernzugriff:

1. **VPN-Seite** (Admin) → "Client hinzufügen"
2. Konfiguration per **QR-Code** scannen (Mobile) oder **Datei herunterladen** (Desktop)
3. WireGuard-App auf dem Gerät installieren und Profil importieren

Alle VPN-Schlüssel werden verschlüsselt gespeichert (Fernet/AES).

## Netzwerkzugriff (Samba & WebDAV)

### Samba (SMB)

Windows-Netzlaufwerk einbinden:
1. Explorer öffnen → Adressleiste: `\\baluhost.local\` oder `\\<Server-IP>\`
2. Mit BaluHost-Zugangsdaten anmelden

### WebDAV

Browser- und WebDAV-Client-Zugriff:
- URL: `http://baluhost.local:8080/webdav/` (Port konfigurierbar)
- Authentifizierung mit BaluHost-Zugangsdaten

Beide Dienste werden im Setup-Wizard oder unter **Einstellungen** konfiguriert.

## Mobile App & Desktop-Client

### BaluApp (Android)

1. App installieren
2. QR-Code auf der BaluHost-Weboberfläche scannen (Geräte-Seite)
3. Automatische VPN-Kopplung und Authentifizierung

### BaluDesk (Windows/Linux)

1. Desktop-Client installieren
2. Pairing-Code von der Weboberfläche eingeben
3. Sync-Ordner konfigurieren für automatische Synchronisierung

## Benachrichtigungen

BaluHost kann Push-Benachrichtigungen an registrierte Mobile-Geräte senden:

- RAID-Warnungen (Degraded, Failed)
- Speicher fast voll
- Fehlgeschlagene Backups
- Sicherheitsereignisse

Konfiguration unter **Einstellungen → Benachrichtigungen** (erfordert Firebase-Setup).

## Cloud-Import

Dateien aus Cloud-Diensten importieren (via rclone):

- Google Drive, Dropbox, OneDrive und weitere
- Einmalige oder geplante Imports
- Konfiguration unter **Cloud-Import**

## Sicherheit

### Passwortrichtlinie

- Mindestens 8 Zeichen
- Groß- und Kleinbuchstaben + Zahl erforderlich
- Häufige Passwörter werden abgelehnt

### Zwei-Faktor-Authentifizierung (2FA)

1. Einstellungen → Sicherheit → 2FA aktivieren
2. QR-Code mit Authenticator-App scannen (Google Authenticator, Authy etc.)
3. Code eingeben zur Bestätigung

### Audit-Logging

Alle sicherheitsrelevanten Aktionen werden protokolliert:
- Anmeldungen (erfolgreich und fehlgeschlagen)
- Passwortänderungen
- Admin-Operationen
- Dateioperationen

Einsehbar unter **Logging** (Admin).

### API-Schlüssel

Für Integrationen können API-Schlüssel erstellt werden (Einstellungen → API-Schlüssel).

## Fehlerbehebung

### Anmeldung schlägt fehl

1. Benutzername und Passwort prüfen (Groß-/Kleinschreibung beachten)
2. Falls 2FA aktiv: Authenticator-Code prüfen
3. Browser-Cache leeren
4. Prüfen, ob der Server erreichbar ist

### Upload schlägt fehl

1. Speicherplatz im Dashboard prüfen
2. Datei nicht zu groß? (Kontingent prüfen)
3. Berechtigung: In eigenem Ordner hochladen

### Seite lädt nicht

1. Server erreichbar? Ping `baluhost.local`
2. VPN-Verbindung prüfen (falls extern)
3. Browser-Konsole auf Fehler prüfen (F12)

### RAID degraded

1. RAID-Seite öffnen → betroffene Disk identifizieren
2. Disk ersetzen und Rebuild starten
3. SMART-Daten der anderen Disks prüfen

---

**Version:** 1.23.0  
**Letzte Aktualisierung:** April 2026
