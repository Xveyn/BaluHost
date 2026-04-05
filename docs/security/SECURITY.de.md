# Sicherheitsrichtlinie

## Unterstützte Versionen

| Version | Unterstützt       |
| ------- | ------------------ |
| 1.23.x  | :white_check_mark: |
| < 1.23  | :x:                |

## Meldung einer Sicherheitslücke

**Bitte melden Sie Sicherheitslücken NICHT über öffentliche GitHub-Issues.**

Senden Sie Ihre Meldung stattdessen per E-Mail an: **security@baluhost.example**

### Was Ihre Meldung enthalten sollte

Bitte geben Sie folgende Informationen an:
- Art der Sicherheitslücke
- Vollständige Pfade der betroffenen Quelldateien
- Position des betroffenen Quellcodes (Tag/Branch/Commit oder direkte URL)
- Schritt-für-Schritt-Anleitung zur Reproduktion des Problems
- Proof-of-Concept oder Exploit-Code (falls vorhanden)
- Auswirkung des Problems, einschließlich möglicher Angriffsszenarien

### Was Sie erwarten können

- Sie erhalten innerhalb von 48 Stunden eine Bestätigung
- Wir untersuchen das Problem und nennen Ihnen einen voraussichtlichen Zeitrahmen
- Wir benachrichtigen Sie, sobald das Problem behoben ist
- Wir erwähnen Sie in den Release Notes (falls gewuenscht)

## Implementierte Sicherheitsfunktionen

### Authentifizierung und Autorisierung
- [x] JWT-Authentifizierung mit HS256-Signierung (Access- + Refresh-Tokens)
- [x] Access-Tokens: 15 Min. TTL, Refresh-Tokens: 7 Tage mit JTI zur Revocation
- [x] Zwei-Faktor-Authentifizierung (TOTP) mit Authenticator-Apps
- [x] Passwortrichtlinie: 8-128 Zeichen, Groß- + Kleinbuchstaben + Ziffer, Blacklist
- [x] Rollenbasierte Zugriffskontrolle (Admin/User) mit `is_privileged()`-Prüfungen
- [x] Rate Limiting auf allen Endpoints via slowapi (endpointspezifische Limits)
- [x] Mobile Geräte-Authentifizierung mit gerätespezifischem JWT + X-Device-ID

### Eingabevalidierung und Pfadsicherheit
- [x] Pydantic-Schemas für alle Request-Validierungen
- [x] Path Jailing via `_jail_path()` — Benutzer auf eigenes Home-Verzeichnis, Shared/ oder validierte Share-Pfade beschränkt
- [x] Path-Traversal-Schutz (`..`-Ablehnung, PurePosixPath-Normalisierung)
- [x] Ausschließlich SQLAlchemy-ORM-Abfragen (kein Raw-SQL mit Benutzereingaben)
- [x] `subprocess.run()` nur mit Listenargumenten (kein `shell=True` im App-Code)

### Netzwerk und Header
- [x] Security-Headers-Middleware (CSP, X-Frame-Options, HSTS, X-Content-Type-Options)
- [x] CORS auf konfigurierte Origins-Liste beschränkt
- [x] Rate Limiting via Nginx-Reverse-Proxy (100 Req/s API, 10 Req/s Auth)
- [x] WireGuard-VPN für verschlüsselten Remote-Zugriff

### Datenschutz
- [x] Verschlüsselte VPN-/SSH-Keys im Ruhezustand (Fernet AES-128-CBC)
- [x] Produktions-Validierung für Secrets (mind. 32 Zeichen, Standardwerte werden abgelehnt)
- [x] Schwärzung sensibler Spalten in der Admin-DB-API (`REDACT_PATTERN`)
- [x] Audit-Logging für alle sicherheitsrelevanten Aktionen (Login, Passwortänderung, Admin-Operationen)
- [x] Strukturiertes JSON-Logging (keine Secrets in den Logs)

## Best Practices für die Sicherheit

### Für Entwickler

**Authentifizierung:**
- Committen Sie niemals Tokens, Passwörter oder Secrets in Git
- Verwenden Sie Umgebungsvariablen für sensible Konfigurationswerte
- Alle neuen Endpoints muessen `Depends(get_current_user)` oder `Depends(get_current_admin)` verwenden
- Wenden Sie Rate Limiting via `@limiter.limit(get_limit("..."))` auf neue Endpoints an

**Autorisierung:**
- Verwenden Sie `ensure_owner_or_privileged()` für Ownership-Prüfungen
- Validieren Sie Dateipfade durch `_jail_path()`
- Vertrauen Sie niemals ausschließlich clientseitigen Prüfungen

**Eingabevalidierung:**
- Verwenden Sie Pydantic-Schemas für alle Request-Bodies (niemals rohes `dict`)
- Lehnen Sie `..` in allen benutzergelieferten Dateipfaden ab
- Verwenden Sie `subprocess.run()` mit expliziten Argumentlisten (niemals String-Kommandos)

**Dateioperationen:**
- Alle Dateioperationen durchlaufen die `_jail_path()`-Sandbox
- Prüfen Sie Kontingente vor Uploads
- Ownership wird über die Datenbank nachverfolgt

### Für Benutzer

**Passwörter:**
- Verwenden Sie starke, einzigartige Passwörter (mind. 8 Zeichen, Groß- + Kleinbuchstaben + Ziffer)
- Ändern Sie Standardpasswörter sofort nach der Einrichtung
- Aktivieren Sie 2FA in den Einstellungen für zusaetzliche Sicherheit
- Teilen Sie niemals Ihre Passwörter

**Zugriffskontrolle:**
- Überprüfen Sie Benutzerberechtigungen regelmäßig
- Entfernen Sie ungenutzte Konten
- Wenden Sie das Prinzip der geringsten Rechte an
- Überwachen Sie die Audit-Logs (Logging-Seite)

**Netzwerksicherheit:**
- Verwenden Sie WireGuard-VPN für den Remote-Zugriff
- Setzen Sie das System nicht ohne VPN oder Reverse-Proxy dem Internet aus
- Konfigurieren Sie die Firewall ordnungsgemäß

## Bekannte Einschränkungen und akzeptierte Kompromisse

Dies sind dokumentierte Kompromisse — versuchen Sie nicht, diese ohne Absprache zu beheben:

1. **Tokens in localStorage** — XSS-Risiko durch CSP-Header abgemildert; HttpOnly-Cookies würden einen umfangreichen Auth-Umbau erfordern
2. **CSP `unsafe-inline`/`unsafe-eval`** — Vom Vite-Dev-Server benötigt; koennte in der Produktion verschärft werden
3. **CORS `allow_methods=["*"]`/`allow_headers=["*"]`** — Auf die konfigurierte `cors_origins`-Liste beschränkt
4. **In-Memory Rate Limiter** — Wird bei Neustart zurückgesetzt; akzeptabel für Single-Instance-Deployment
5. **Kein CSRF-Schutz** — Durch JWT-Bearer-Authentifizierung abgemildert (nicht Cookie-basiert)
6. **HTTPS nicht erzwungen** — Externer Zugriff über WireGuard-VPN (verschlüsselter Tunnel); HTTP im vertrauenswürdigen LAN
7. **JTI ohne serverseitigen Revocation-Store** — Token-Rotation ist die primäre Schutzstrategie

## Sicherheits-Checkliste für die Produktion

Vor dem Produktions-Deployment:

- [x] Alle Standardpasswörter geändert
- [x] Starken `SECRET_KEY` gesetzt (mind. 32 Zeichen, wird beim Start validiert)
- [x] Starkes `TOKEN_SECRET` gesetzt (mind. 32 Zeichen, wird beim Start validiert)
- [x] Firewall-Regeln konfiguriert
- [x] Debug-Modus deaktiviert
- [x] CORS-Einstellungen geprüft (auf bekannte Origins beschränkt)
- [x] Audit-Logging aktiviert
- [x] Backups eingerichtet (pg_dump)
- [x] Strukturiertes JSON-Logging konfiguriert
- [x] Benutzerberechtigungen geprüft
- [ ] HTTPS mit gueltigem SSL-Zertifikat verwenden (optional, VPN bietet Verschlüsselung)
- [ ] Log-Rotation einrichten
- [ ] Sicherheits-Audit-Tools ausführen

## Abhängigkeitssicherheit

Wir verwenden automatisierte Tools zur Prüfung auf Schwachstellen:

**Python (Backend):**
```bash
pip install safety
safety check
```

**Node.js (Frontend):**
```bash
npm audit
npm audit fix
```

## Sicherheitsressourcen

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)

## Offenlegungsrichtlinie

- Wir folgen den Grundsätzen der verantwortungsvollen Offenlegung (Responsible Disclosure)
- Wir erwähnen Sicherheitsforscher in den Release Notes
- Wir streben an, kritische Probleme innerhalb von 7 Tagen zu beheben
- Wir benachrichtigen betroffene Benutzer bei Bedarf

## Kontakt

Für sicherheitsbezogene Fragen oder Anliegen:
- **E-Mail:** security@baluhost.example

---

**Zuletzt aktualisiert:** April 2026
**Version:** 1.23.0
