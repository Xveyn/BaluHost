# BaluHost API-Referenz

BaluHost bietet eine REST-API für alle Funktionen. Die vollständige, interaktive Dokumentation ist als Swagger UI verfügbar.

## Swagger UI (interaktiv)

Die empfohlene Methode, die API zu erkunden:

```
http://baluhost.local/docs
```

Dort finden Sie alle Endpoints mit Parametern, Schemas und können Requests direkt testen.

## Basis-URL

```
http://baluhost.local/api
```

Alle API-Endpoints verwenden das Prefix `/api`.

## Authentifizierung

Die meisten Endpoints erfordern JWT-Authentifizierung. Der Token wird im `Authorization`-Header mitgegeben:

```http
Authorization: Bearer <access_token>
```

### Token-Typen

| Typ | Gültigkeit | Verwendung |
|-----|-----------|------------|
| **Access Token** | 15 Minuten | API-Requests |
| **Refresh Token** | 7 Tage | Access Token erneuern |
| **SSE Token** | 60 Sekunden | Server-Sent Events (Upload-Progress) |

### Login

```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "string",
  "password": "string"
}
```

Antwort:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "role": "admin"
  }
}
```

### Token erneuern

```http
POST /api/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJ..."
}
```

## API-Bereiche

| Pfad | Bereich | Auth |
|------|---------|------|
| `/api/auth/*` | Authentifizierung (Login, Register, Refresh, 2FA) | Teilweise |
| `/api/files/*` | Dateiverwaltung (Upload, Download, Ordner, Suche) | Ja |
| `/api/users/*` | Benutzerverwaltung | Admin |
| `/api/shares/*` | Dateifreigaben | Ja |
| `/api/system/*` | Systeminfo, RAID, SMART, Telemetrie | Ja |
| `/api/monitoring/*` | Echtzeit-Metriken (CPU, RAM, Netzwerk, Disk I/O) | Ja |
| `/api/power/*` | CPU-Profile, Energieverwaltung | Admin |
| `/api/fans/*` | Lüftersteuerung, Temperaturkurven | Admin |
| `/api/vpn/*` | VPN-Konfiguration | Admin |
| `/api/backup/*` | Backup/Restore | Admin |
| `/api/sync/*` | Desktop-Synchronisation | Ja |
| `/api/mobile/*` | Mobile-Geräte-Verwaltung | Admin |
| `/api/logging/*` | Audit-Logs | Ja (eingeschränkt) |
| `/api/schedulers/*` | Scheduler-Verwaltung | Admin |
| `/api/notifications/*` | Push-Benachrichtigungen | Ja |
| `/api/plugins/*` | Plugin-System | Admin |
| `/api/pihole/*` | Pi-hole DNS | Admin |
| `/api/cloud/*` | Cloud-Import (rclone) | Ja |
| `/api/updates/*` | Update-Mechanismus | Admin |
| `/api/sleep/*` | Sleep-Modus | Admin |
| `/api/webdav/*` | WebDAV-Server | Admin |
| `/api/samba/*` | Samba/SMB-Freigaben | Admin |
| `/api/benchmark/*` | System-Benchmark | Admin |
| `/api/api-keys/*` | API-Schlüssel-Verwaltung | Ja |
| `/api/admin/*` | Admin-Dashboard | Admin |
| `/api/admin-db/*` | Datenbank-Inspektion | Admin |
| `/api/energy/*` | Energieverbrauch | Admin |
| `/api/tapo/*` | Smart-Plug-Steuerung (TP-Link Tapo) | Admin |
| `/api/setup/*` | Setup-Wizard | Setup-Token |

## Rate Limiting

API-Requests sind durch Rate Limiting geschützt:

| Endpoint-Typ | Limit |
|-------------|-------|
| Allgemeine API | 100 Requests/Sekunde |
| Auth-Endpoints (Login, Register) | 10 Requests/Sekunde |
| Passwortänderung | 5 Requests/Minute |

Bei Überschreitung: HTTP 429 (Too Many Requests).

## API-Schlüssel

Alternativ zur JWT-Authentifizierung können API-Schlüssel für Integrationen verwendet werden:

1. Einstellungen → API-Schlüssel → "Neuen Schlüssel erstellen"
2. Schlüssel im Header mitgeben: `X-API-Key: <key>`

## Fehlerformat

Alle Fehler folgen einem einheitlichen Format:

```json
{
  "detail": "Beschreibung des Fehlers"
}
```

Häufige HTTP-Statuscodes:
- `401` — Nicht authentifiziert
- `403` — Keine Berechtigung
- `404` — Ressource nicht gefunden
- `422` — Validierungsfehler
- `429` — Rate Limit überschritten

---

**Version:** 1.23.0  
**Letzte Aktualisierung:** April 2026
