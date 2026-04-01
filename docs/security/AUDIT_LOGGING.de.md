# Audit-Logging

BaluHost protokolliert sicherheitsrelevante Aktionen automatisch in der Datenbank. Die Logs sind über die Weboberfläche einsehbar.

## Was wird protokolliert?

### Authentifizierung
- Erfolgreiche und fehlgeschlagene Anmeldungen
- Passwortänderungen
- 2FA-Aktivierung/Deaktivierung
- Token-Erneuerungen

### Dateizugriffe
- Uploads, Downloads, Löschungen
- Ordner erstellen, verschieben, umbenennen
- Freigaben erstellen und löschen

### Administration
- Benutzer erstellen, bearbeiten, löschen
- RAID-Operationen
- VPN-Client-Verwaltung
- Konfigurationsänderungen

### System
- Server-Start und -Stop
- Backup-Operationen
- Scheduler-Ausführungen

## Logging-Seite

Die Logging-Seite ist unter **Logging** in der Seitenleiste erreichbar (Admin-Bereich).

### Filter

| Filter | Optionen |
|--------|----------|
| **Zeitraum** | 1 Tag, 7 Tage, 30 Tage, bis zu 365 Tage |
| **Event-Typ** | FILE_ACCESS, AUTH, SYSTEM, ADMIN |
| **Benutzer** | Nach Benutzername filtern (nur Admin) |
| **Aktion** | upload, download, delete, login, etc. |
| **Status** | Erfolgreich / Fehlgeschlagen |

### Paginierung

Logs werden seitenweise angezeigt (50 Einträge pro Seite). Navigation über die Seitenleiste.

### Sichtbarkeit nach Rolle

| Rolle | Sichtbarkeit |
|-------|-------------|
| **Admin** | Alle Events, alle Benutzer, vollständige Details |
| **Benutzer** | Eingeschränkte Events, anonymisierte Benutzernamen, keine Details |

## Jeder Log-Eintrag enthält

- **Zeitstempel** — Wann die Aktion stattfand
- **Event-Typ** — Kategorie (FILE_ACCESS, AUTH, SYSTEM, ADMIN)
- **Benutzer** — Wer die Aktion ausgeführt hat
- **Aktion** — Was getan wurde (upload, login, delete, etc.)
- **Ressource** — Betroffene Datei oder Ressource
- **Status** — Erfolg oder Fehlschlag
- **Details** — Zusätzliche Informationen (z.B. Dateigröße, Zielpfad)

## Speicherung

- Logs werden in der PostgreSQL-Datenbank gespeichert (Tabelle `audit_logs`)
- Retention ist über die Monitoring-Konfiguration einstellbar
- Sensible Daten (Passwörter, Tokens, Private Keys) werden **niemals** geloggt

## API-Zugriff

Audit-Logs sind auch über die REST-API abrufbar:

```
GET /api/logging/audit?days=7&page=1&page_size=50
```

Erfordert Authentifizierung. Admins sehen vollständige Logs, normale Benutzer eine eingeschränkte Ansicht.

---

**Version:** 1.23.0  
**Letzte Aktualisierung:** April 2026
