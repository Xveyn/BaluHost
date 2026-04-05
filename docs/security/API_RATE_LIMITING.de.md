# API Rate Limiting - Implementierungsdokumentation

## Übersicht

API Rate Limiting wurde erfolgreich mit `slowapi` implementiert, um die BaluHost-NAS-API vor Missbrauch zu schützen und eine faire Ressourcenverteilung zu gewährleisten.

## Implementierungsdetails

### Technologie-Stack

- **Bibliothek**: [slowapi](https://github.com/laurentS/slowapi) v0.1.9+
- **Speicher-Backend**: In-Memory-Speicher (`memory://`)
- **Identifikationsmethoden**: 
  - IP-basiert für nicht authentifizierte Endpoints
  - Benutzerbasiert (JWT) für authentifizierte Endpoints

### Architektur

```
┌─────────────────────────────────────────────────────────┐
│                     FastAPI App                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Rate Limit Middleware (slowapi)                  │  │
│  │  - Verfolgt Requests pro IP/Benutzer              │  │
│  │  - Gibt 429 zurück bei Überschreitung           │  │
│  │  - Fuegt X-RateLimit-* Header hinzu               │  │
│  └───────────────────────────────────────────────────┘  │
│                          ↓                              │
│  ┌───────────────────────────────────────────────────┐  │
│  │  API-Routen (mit @limiter.limit Dekoratoren)      │  │
│  │  - /api/auth/login (5/Minute)                     │  │
│  │  - /api/auth/register (3/Minute)                  │  │
│  │  - /api/files/upload (20/Minute)                  │  │
│  │  - /api/files/download (100/Minute)               │  │
│  │  - /api/shares/links (10/Minute)                  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Rate-Limit-Konfiguration

### Authentifizierungs-Endpoints (Strenge Limits)

| Endpoint | Limit | Grund |
|----------|-------|-------|
| `POST /api/auth/login` | 5/Minute | Brute-Force-Angriffe verhindern |
| `POST /api/auth/register` | 3/Minute | Spam-Registrierungen verhindern |
| `POST /api/mobile/register` | 3/Minute | Spam bei Geräteregistrierung verhindern |

### Dateioperationen (Moderate Limits)

| Endpoint | Limit | Grund |
|----------|-------|-------|
| `POST /api/files/upload` | 20/Minute | Upload-Kapazitaet ausbalancieren |
| `GET /api/files/download/*` | 100/Minute | Angemessenen Dateizugriff ermöglichen |
| `GET /api/files/list` | 60/Minute | Moderates Verzeichnis-Listing |
| `DELETE /api/files/*` | 30/Minute | Dateiloeschrate kontrollieren |

### Share-Operationen (Moderate Limits)

| Endpoint | Limit | Grund |
|----------|-------|-------|
| `POST /api/shares/links` | 10/Minute | Share-Erstellung kontrollieren |
| `GET /api/shares/links` | 60/Minute | Auflisten von Shares ermöglichen |
| `POST /api/shares/public/{token}/access` | 100/Minute | Öffentlicher Share-Zugriff |

### Systemoperationen (Großzügige Limits)

| Endpoint | Limit | Grund |
|----------|-------|-------|
| System-Monitor-Endpoints | 120/Minute | Häufiges Monitoring ermöglichen |
| Benutzeroperationen | 30/Minute | Standard-CRUD-Operationen |
| Admin-Operationen | 30/Minute | Administrative Aufgaben |

## Geänderte Dateien

### Neue Dateien

1. **`backend/app/core/rate_limiter.py`**
   - Limiter-Initialisierung mit Memory-Backend
   - Rate-Limit-Konfigurationen (RATE_LIMITS-Dictionary)
   - Benutzerdefinierter Exception-Handler für 429-Antworten
   - Benutzerbasierte Identifikationsfunktion für JWT-Benutzer

### Geänderte Dateien

1. **`backend/pyproject.toml`**
   - `slowapi>=0.1.9,<0.2.0` als Abhängigkeit hinzugefügt

2. **`backend/app/main.py`**
   - Import der slowapi-Komponenten
   - Registrierung des Limiters im App-State
   - Exception-Handler für RateLimitExceeded hinzugefügt

3. **`backend/app/api/routes/auth.py`**
   - `@limiter.limit()` zum Login-Endpoint hinzugefügt
   - `@limiter.limit()` zum Register-Endpoint hinzugefügt
   - `Request`-Parameter zu Funktionssignaturen hinzugefügt

4. **`backend/app/api/routes/files.py`**
   - Rate Limiting zu allen kritischen Datei-Endpoints hinzugefügt
   - `user_limiter` für authentifizierte Endpoints verwendet
   - `Request`-Parameter zu Funktionssignaturen hinzugefügt

5. **`backend/app/api/routes/shares.py`**
   - Rate Limiting für Share-Erstellung und -Auflistung hinzugefügt
   - Rate Limiting für öffentlichen Share-Zugriff hinzugefügt
   - `Request`-Parameter zu Funktionssignaturen hinzugefügt

### Testdateien

1. **`backend/tests/test_rate_limiting.py`**
   - Tests für Rate-Limit-Durchsetzung
   - Tests für Rate-Limit-Konfiguration
   - Tests für Antwortformat und Header

## Verwendung

### Für Entwickler

Rate Limiting auf einen neuen Endpoint anwenden:

```python
from app.core.rate_limiter import limiter, user_limiter, get_limit
from fastapi import Request

# Für nicht authentifizierte Endpoints (IP-basiert)
@router.post("/public-endpoint")
@limiter.limit(get_limit("public_share"))
async def public_endpoint(request: Request, ...):
    pass

# Für authentifizierte Endpoints (benutzerbasiert)
@router.get("/protected-endpoint")
@user_limiter.limit(get_limit("file_list"))
async def protected_endpoint(
    request: Request,
    user: UserPublic = Depends(get_current_user),
    ...
):
    pass
```

### Neue Rate Limits hinzufügen

Bearbeiten Sie `backend/app/core/rate_limiter.py`:

```python
RATE_LIMITS = {
    # ... bestehende Limits ...
    "new_endpoint_type": "50/minute",  # 50 Requests pro Minute
}
```

## Antwortformat

### Erfolgreicher Request (innerhalb des Limits)

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1704283200
```

### Rate Limit überschritten

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
X-RateLimit-Limit: 100
X-RateLimit-Reset: 1704283200
Content-Type: application/json

{
  "error": "Too Many Requests",
  "detail": "Rate limit exceeded. Please try again later.",
  "retry_after": 60
}
```

## Tests

Rate-Limiting-Tests ausführen:

```bash
cd backend
python -m pytest tests/test_rate_limiting.py -v
```

Spezifische Szenarien testen:

```bash
# Konfigurationstests
pytest tests/test_rate_limiting.py::TestRateLimitConfiguration -v

# Rate-Limit-Durchsetzungstests
pytest tests/test_rate_limiting.py::TestRateLimiting -v
```

## Konfigurationsoptionen

### Memory-Backend (aktuell)

- **Vorteile**: Keine externen Abhängigkeiten, einfache Einrichtung
- **Nachteile**: Wird bei Serverneustart zurückgesetzt, nicht für Multi-Instanz-Deployments geeignet

### Redis-Backend (zukünftige Erweiterung)

Für den Produktionsbetrieb mit mehreren Instanzen kann auf Redis umgestellt werden:

```python
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute", "1000/hour"],
    headers_enabled=True,
    storage_uri="redis://localhost:6379"
)
```

## Sicherheitsaspekte

1. **Umgehungsschutz**: Rate Limits werden auf FastAPI-Ebene durchgesetzt, bevor die Geschäftslogik erreicht wird
2. **Header-Informationen**: X-RateLimit-*-Header informieren Clients über ihre Nutzung
3. **Graceful Degradation**: 429-Antworten enthalten Retry-After-Informationen
4. **Benutzerbasiertes Tracking**: Authentifizierte Benutzer werden unabhängig von der IP verfolgt

## Monitoring

Überwachung von Rate-Limit-Treffern über:

1. **Anwendungs-Logs**: Prüfen Sie die Logs auf Rate-Limit-Warnungen
2. **Audit-Logs**: Fehlgeschlagene Authentifizierungsversuche werden protokolliert
3. **Metriken** (Zukunft): Export von Rate-Limit-Metriken an Monitoring-Systeme

## Zukünftige Erweiterungen

- [ ] Redis-Backend für verteiltes Rate Limiting hinzufügen
- [ ] Benutzerspezifische Kontingente implementieren (Tages-/Monatslimits)
- [ ] Admin-API zur dynamischen Anzeige/Änderung von Rate Limits hinzufügen
- [ ] Rate-Limit-Metriken nach Prometheus exportieren
- [ ] Gestaffelte Rate Limits basierend auf Benutzerrollen implementieren
- [ ] Konfigurierbare Rate Limits über Umgebungsvariablen hinzufügen

## Referenzen

- [slowapi-Dokumentation](https://github.com/laurentS/slowapi)
- [Flask-Limiter](https://flask-limiter.readthedocs.io/) (slowapi basiert darauf)
- [IETF Draft: RateLimit Header Fields](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-ratelimit-headers)

---

**Implementierungsdatum**: 2. Januar 2026  
**Status**: Abgeschlossen und getestet
