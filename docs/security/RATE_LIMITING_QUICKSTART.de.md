# API Rate Limiting - Schnellstart-Anleitung

## Was implementiert wurde

API Rate Limiting ist jetzt aktiv und schützt vor:
- Brute-Force-Login-Angriffen (5 Versuche/Minute)
- Spam-Registrierungen (3/Minute)
- Upload-Flooding (20/Minute)
- Missbrauch von Share-Links (10/Minute)
- Allgemeinem API-Missbrauch (individuelle Limits pro Endpoint-Typ)

## Rate-Limits-Übersicht

### Kritische Sicherheits-Endpoints
- **Login**: 5 Requests/Minute
- **Registrierung**: 3 Requests/Minute
- **Mobile Registrierung**: 3 Requests/Minute

### Dateioperationen
- **Upload**: 20 Requests/Minute
- **Download**: 100 Requests/Minute
- **Dateien auflisten**: 60 Requests/Minute
- **Löschen**: 30 Requests/Minute

### Freigaben
- **Freigabe erstellen**: 10 Requests/Minute
- **Freigaben auflisten**: 60 Requests/Minute
- **Öffentlicher Zugriff**: 100 Requests/Minute

## Funktionsweise

1. **IP-basiertes Tracking** für nicht authentifizierte Requests
2. **Benutzerbasiertes Tracking** für authentifizierte Requests (via JWT)
3. **Automatische 429-Antworten** bei Überschreitung der Limits
4. **X-RateLimit-*-Header** informieren Clients über die Nutzung

## Für Frontend-Entwickler

Wenn Sie ein Rate Limit erreichen, erhalten Sie:

```json
HTTP/1.1 429 Too Many Requests
Retry-After: 60

{
  "error": "Too Many Requests",
  "detail": "Rate limit exceeded. Please try again later.",
  "retry_after": 60
}
```

**Empfohlenes Client-Verhalten:**
1. Prüfen Sie auf den Statuscode `429`
2. Lesen Sie den `Retry-After`-Header oder `retry_after` aus der Antwort
3. Zeigen Sie eine benutzerfreundliche Nachricht an: "Zu viele Anfragen. Bitte warten Sie {retry_after} Sekunden."
4. Implementieren Sie optional einen automatischen Retry mit exponentiellem Backoff

## Tests

```bash
# Alle Rate-Limiting-Tests ausführen
cd backend
python -m pytest tests/test_rate_limiting.py -v

# Nur Konfigurationstests
pytest tests/test_rate_limiting.py::TestRateLimitConfiguration -v
```

## Konfiguration

Alle Rate Limits sind in `backend/app/core/rate_limiter.py` definiert:

```python
RATE_LIMITS = {
    "auth_login": "5/minute",
    "file_upload": "20/minute",
    # ... usw.
}
```

## Monitoring

- Prüfen Sie die Logs auf Rate-Limit-Warnungen
- Audit-Logs verfolgen fehlgeschlagene Authentifizierungsversuche
- 429-Antworten werden mit IP-/Benutzerinformationen protokolliert

## Sicherheitsvorteile

1. **Brute-Force-Schutz**: Login-Rate-Limits verhindern Passwort-Erraten
2. **DoS-Prävention**: Request-Limits verhindern Ressourcenerschöpfung
3. **Faire Nutzung**: Stellt sicher, dass alle Benutzer gleichmäßigen Zugriff erhalten
4. **Spam-Prävention**: Limits verhindern automatisierten Missbrauch

## Zukünftige Erweiterungen

- [ ] Redis-Backend für Multi-Instanz-Deployments
- [ ] Benutzerspezifische Tages-/Monatskontingente
- [ ] Admin-Dashboard für Rate-Limit-Monitoring
- [ ] Konfigurierbare Limits über Umgebungsvariablen
- [ ] Rollenbasierte Rate-Limit-Stufen (Premium-Benutzer erhalten höhere Limits)

## Vollständige Dokumentation

Siehe `docs/API_RATE_LIMITING.md` für vollständige Implementierungsdetails.
