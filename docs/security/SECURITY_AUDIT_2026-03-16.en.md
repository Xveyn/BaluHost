# BaluHost Security Audit Report

**Datum**: 16. März 2026 | **Branch**: `development` | **Produktion**: Debian 13, PostgreSQL 17.7

Geprüft: 44 Route-Module, alle Services, Frontend, Dependencies, Middleware, Config.
Methodik: Parallele Code-Review-Agents + manuelle Analyse + OWASP Top 10:2025 Mapping.

---

## KRITISCH (Sofortiger Handlungsbedarf)

### K1. Token-Revocation-System ist vollständig inoperativ

**Dateien**: `backend/app/services/auth.py:63`, `backend/app/schemas/auth.py:91`, `backend/app/core/security.py`

Drei zusammenhängende Fehler machen das gesamte JTI-basierte Revocation-System (Security Fix #6) unwirksam:

1. **`auth_service.decode_token()` hardcoded `token_type="access"`** — Der Refresh-Endpoint akzeptiert Access-Tokens als Refresh-Tokens (Token-Type-Confusion). Echte Refresh-Tokens (`type="refresh"`) werden **abgelehnt**.
2. **JTI wird nie in `TokenPayload` gemappt** — `jti` bleibt immer `None`, daher wird `token_service.is_token_revoked()` nie aufgerufen.
3. **Mobile "Refresh Token" ist ein Access-Token** (`mobile.py:268`) — `create_access_token()` mit 30-Tage-TTL statt `create_refresh_token()`. Kein JTI, keine Revocation möglich.

**Auswirkung**: Kein Token kann serverseitig widerrufen werden. Gestohlene Tokens bleiben bis Ablauf gültig.

**Fix**:
- `auth_service.decode_token()` um `token_type`-Parameter erweitern, Refresh-Endpoint muss `token_type="refresh"` übergeben
- JTI aus decoded payload in `TokenPayload` mappen: `jti=decoded.get("jti")`
- Mobile: `create_refresh_token()` statt `create_access_token()` verwenden, JTI in `RefreshToken` speichern

### K2. Logout invalidiert keine Tokens serverseitig

**Datei**: `backend/app/api/routes/auth.py:484-487`

Der `/logout`-Endpoint gibt `{"message": "Logged out"}` zurück, ohne Refresh-Tokens zu revoken. Die `RefreshToken.revoke()`-Methode existiert, wird aber nie aufgerufen. Tests bestätigen explizit: "refresh token revocation not yet implemented."

**Auswirkung**: Kombiniert mit K1 — gestohlene Tokens können nicht invalidiert werden.

**Fix**: `token_service.revoke_all_user_tokens(db, current_user.id, reason="logout")` im Logout-Handler aufrufen.

### K3. Access-Tokens leben 12 Stunden statt 15 Minuten

**Dateien**: `backend/app/core/config.py:37`, `backend/app/services/auth.py:49`

`auth_service.create_access_token()` verwendet `settings.token_expire_minutes` (720 min = 12h) statt `settings.ACCESS_TOKEN_EXPIRE_MINUTES` (15 min). Das Short-TTL-Design ist komplett ausgehebelt.

**Auswirkung**: K1 + K2 + K3 zusammen = gestohlener Token ist **12 Stunden** nutzbar und **nicht widerrufbar**.

**Fix**: `settings.ACCESS_TOKEN_EXPIRE_MINUTES` verwenden statt `settings.token_expire_minutes`. Legacy-Feld entfernen oder deprecation-warning hinzufügen.

### K4. Prometheus-Metrics ohne Authentifizierung

**Datei**: `backend/app/api/routes/metrics.py:483-509`

`GET /api/metrics` verwendet `get_current_user_optional` — gibt volle System-Metriken (CPU, RAM, Disk, RAID-Status, SMART, User-Anzahl, Version) an **jeden unauthentifizierten Requester** zurück.

**Auswirkung**: Vollständiges System-Fingerprinting für Angreifer im Netzwerk.

**Fix**: `get_current_admin` als Dependency verwenden. Für Prometheus-Scraping: dediziertes Scrape-Secret via Query-Parameter validieren.

---

## HOCH (Zeitnah beheben)

### H1. `get_current_user` prüft nicht `is_active`

**Datei**: `backend/app/api/deps.py:89-105`

Ein deaktivierter User mit gültigem JWT kann weiter API-Requests machen. Der API-Key-Pfad prüft `is_active`, der JWT-Pfad nicht.

**Fix**: Nach `user = user_service.get_user(payload.sub, db=db)` prüfen: `if not user.is_active: raise HTTP 401`.

### H2. IDOR bei Mobile Camera/Sync-Endpoints

**Datei**: `backend/app/api/routes/mobile.py:363-454`

`GET/PUT /mobile/camera/settings/{device_id}`, `GET/POST /mobile/sync/folders/{device_id}`, `DELETE /mobile/sync/folders/{folder_id}` — keine Ownership-Prüfung. Jeder authentifizierte User kann Settings fremder Geräte lesen/schreiben.

**Fix**: In jedem betroffenen Handler zuerst `MobileService.get_device(db, device_id, user_id=current_user.id)` aufrufen und 404 zurückgeben falls nicht gefunden.

### H3. Brute-Force-Counter reset nach Alert

**Datei**: `backend/app/api/routes/auth.py:72`

Nach 5 Fehlversuchen wird `_failed_login_attempts[ip] = []` — Counter auf Null. Angreifer bekommt unbegrenzt neue 5-Versuch-Fenster. Keine Blockierung, kein Cooldown.

**Fix**: Counter nicht resetten. TTL-basiertes Expiry natürlich ablaufen lassen. Optional: temporäre IP-Blockierung nach wiederholten Alerts.

### H4. 2FA-Verification nur per IP rate-limitiert

**Datei**: `backend/app/api/routes/auth.py:114`

5/min per IP, aber nicht per User. TOTP = 6 Ziffern = 1M Möglichkeiten. Angreifer mit mehreren IPs oder Multi-Worker-Setup kann TOTP bruteforcen.

**Fix**: Rate-Limit per `user_id` aus dem pending-Token's `sub`-Claim keyen, nicht nur per IP.

### H5. TOTP-Key fällt auf VPN-Encryption-Key zurück

**Datei**: `backend/app/services/totp_service.py:33-34`

```python
key = settings.totp_encryption_key or settings.vpn_encryption_key
```

Ohne `TOTP_ENCRYPTION_KEY` werden TOTP-Secrets mit dem VPN-Key verschlüsselt. Kompromittierung eines Keys kompromittiert beide Systeme.

**Fix**: `TOTP_ENCRYPTION_KEY` als eigenen Key erzwingen, beim Startup validieren, keinen Fallback erlauben.

### H6. Offene Registrierung in Produktion standardmäßig aktiv

**Datei**: `backend/app/core/config.py:43`

`registration_enabled` defaults `True`, kein Production-Validator. Jeder im Netzwerk kann Accounts erstellen.

**Fix**: Production-Validator analog zu `SECRET_KEY` hinzufügen, der `registration_enabled=True` in Prod ablehnt oder warnt. Default in Prod auf `False`.

### H7. `passlib` ist unmaintained (kein Release seit 2022)

**Datei**: `backend/pyproject.toml:17`

Blockiert auch `bcrypt` Updates (gepinnt auf `<4.1.0`). Keine Sicherheits-Patches.

**Fix**: Migration zu direkter `bcrypt`-Nutzung oder `argon2-cffi`. Bestehende Hashes sind kompatibel.

### H8. VPN-Keys werden bei fehlendem `VPN_ENCRYPTION_KEY` stillschweigend plaintext gespeichert

**Datei**: `backend/app/services/vpn/service.py:43-49`

Dokumentation sagt "fails loudly if missing" — tatsächlich wird nur `logger.warning` ausgegeben und der Key unverschlüsselt in die DB geschrieben.

**Fix**: `ValueError` raisen statt silent Fallback, oder Audit-Log-Entry schreiben.

### H9. SMART-Self-Test: Unvalidierter `device`-Parameter

**Datei**: `backend/app/services/hardware/smart/scheduler.py:76`

```python
result = subprocess.run(["sudo", "-n", smartctl, "-t", test_type, device], ...)
```

`device` wird direkt an `smartctl` übergeben ohne Allowlist-Validierung (kein `shell=True`, aber fehlende Input-Validierung).

**Fix**: Regex-Validierung: `re.fullmatch(r"/dev/(sd[a-z][0-9]?|nvme[0-9]+n[0-9]+|hd[a-z])", device)`, analog zu `_normalize_device()` im RAID-Backend.

### H10. WebSocket-Fallback übergibt vollen Access-Token in URL

**Datei**: `client/src/hooks/useNotificationSocket.ts:82-86`

Wenn der WS-Token-Endpoint fehlschlägt, wird der volle Access-Token als Query-Parameter übergeben — erscheint in Nginx-Logs, Browser-History, Referrer-Headers.

**Fix**: Fallback entfernen. Bei WS-Token-Fehler: Connection-Error statt Token-Leak. Fail closed.

---

## MITTEL (Sollte behoben werden)

| # | Finding | Datei | Fix |
|---|---------|-------|-----|
| M1 | Password-Change revoked keine aktiven Refresh-Tokens | `routes/auth.py:438` | `token_service.revoke_all_user_tokens()` aufrufen |
| M2 | Audit-Logs für alle User zugänglich, nicht admin-only | `routes/logging.py:291` | `get_current_admin` verwenden oder Non-Admin-Sichtbarkeit einschränken |
| M3 | CSP `connect-src https:` erlaubt Exfiltration zu jedem HTTPS-Host | `security_headers.py:43` | Auf `'self'` einschränken |
| M4 | VPN server-config nutzt manuellen Rolle-Check statt `get_current_admin` | `routes/vpn.py:527` | Standard-Dependency verwenden |
| M5 | Chunked Upload: Kein Obergrenze für `total_size`, kein Check `> 0` | `routes/chunked_upload.py:128` | `Field(..., gt=0, le=MAX_UPLOAD)` |
| M6 | Chunked Upload: Race-Condition bei `next_chunk_index` | `files/chunked_upload.py:165` | Session-Lock während Chunk-Write halten |
| M7 | Frontend Passwort-Minimum (6 Zeichen) weicher als Backend (8) | `SettingsPage.tsx:90` | Frontend auf 8 Zeichen + Stärke-Feedback anpassen |
| M8 | Ownership-Check in FileManager nutzt String-Vergleich statt Number | `FileManager.tsx:59` | `Number(ownerId) === Number(user.id)` |
| M9 | Server-Profiles SSH-Hosts ohne Auth sichtbar wenn Flag aktiv | `routes/server_profiles.py:32` | In `LocalOnlyMiddleware`-Prefixes aufnehmen |
| M10 | `psycopg2-binary` statt `psycopg2` in Produktion | `pyproject.toml:16` | Auf `psycopg2` (compiled) oder `psycopg[binary]` migrieren |
| M11 | Samba-Config: Username direkt in INI interpoliert | `samba_service.py:179` | Lokale Re-Validierung: `re.fullmatch(r"^[a-zA-Z0-9_-]+$", username)` |
| M12 | `Pillow` ohne obere Versionsgrenze (häufige CVEs) | `pyproject.toml:38` | Upper bound hinzufügen |
| M13 | Mobile Token + VPN-Config in localStorage gespeichert | `MobileDevicesPage.tsx:90` | In-Memory React State statt localStorage |
| M14 | `debug=True` hat keinen Production-Validator | `config.py:206` | Analog zu `SECRET_KEY` validieren |
| M15 | Rate-Limiter `_is_test_mode` Name-Collision (bool vs function) | `rate_limiter.py:31/161` | Umbenennen, Shadowing eliminieren |

---

## NIEDRIG (Nice to have)

| # | Finding |
|---|---------|
| N1 | JWT in localStorage (dokumentierter Trade-off, Known Gap #7) |
| N2 | Brute-Force-Tracker ephemeral über Worker/Restarts |
| N3 | In-Memory Rate-Limiter reset bei Restart (Known Gap #3) |
| N4 | `package-lock.json` Version out-of-sync mit `package.json` |
| N5 | Avatare ohne Auth served (UUIDs, nicht erratbar) |
| N6 | `firebase-admin` immer installiert (große Attack Surface) |
| N7 | Health/Ping-Endpoints leaken Version-String |
| N8 | `console.error` loggt raw Error-Objekte im Frontend (`FileViewer.tsx:83`) |
| N9 | `GET /api/updates/version` und `/release-notes` ohne Auth (Version-Fingerprinting) |
| N10 | `GET /api/system/info/local` IP-Check wird von Nginx-Proxy umgangen |
| N11 | Desktop-Pairing Device-Code-Flow unauthentifiziert (Rate-Limit-only) |

---

## OWASP Top 10:2025 Mapping

| OWASP Kategorie | BaluHost Status | Kritischste Findings |
|---|---|---|
| **A01 Broken Access Control** | Schwachstellen vorhanden | K4 (Metrics unauth), H2 (IDOR Mobile), H1 (is_active) |
| **A02 Security Misconfiguration** | Teilweise | H6 (Offene Registrierung), K3 (12h Token-TTL), M14 (debug) |
| **A03 Supply Chain** | Risiko | H7 (passlib unmaintained), M10 (psycopg2-binary) |
| **A04 Cryptographic Failures** | Risiko | H5 (TOTP/VPN Key-Sharing), H8 (Plaintext VPN keys) |
| **A05 Injection** | Gut geschützt | H9 (SMART device unvalidiert, aber kein shell=True) |
| **A06 Insecure Design** | Strukturelle Issues | K1-K3 (Token-Lifecycle komplett defekt) |
| **A07 Authentication Failures** | Schwachstellen | H3 (Brute-Force Reset), H4 (2FA bypass), K2 (Logout) |
| **A08 Integrity Failures** | OK | Kein unsicheres Deserialisieren gefunden |
| **A09 Logging Failures** | Gut | Audit-Logging vorhanden, aber M2 (Zugriffsrechte) |
| **A10 Exception Handling** | OK | Keine unsichere Fehlerbehandlung gefunden |

---

## Positiv-Befunde (gut implementiert)

- **Subprocess-Sicherheit**: Alle `subprocess.run()` Aufrufe nutzen List-Args, kein `shell=True` im App-Code
- **Path-Traversal-Schutz**: `_jail_path()` verhindert Traversal korrekt, `..` wird abgelehnt
- **Admin-DB**: Table-Whitelist + REDACT_PATTERN — kein Raw-SQL mit User-Input
- **Rclone**: `asyncio.create_subprocess_exec` (kein Shell)
- **Production-Validatoren**: SECRET_KEY und token_secret werden in Prod validiert
- **CORS**: Origins explizit gelistet (kein Wildcard `*`)
- **Security Headers**: CSP, X-Frame-Options, HSTS, Referrer-Policy, Permissions-Policy vorhanden
- **Frontend**: Kein `dangerouslySetInnerHTML`, `eval`, `exec`, `pickle.load` gefunden
- **Encryption at Rest**: Fernet-Verschlüsselung für VPN/SSH Keys
- **2FA**: TOTP mit Backup-Codes vollständig implementiert
- **Tests**: 1465 Tests in 82 Test-Dateien
- **Timing-Safe Auth**: Dummy-Hash verhindert Username-Enumeration
- **Pydantic**: Request-Validierung auf allen kritischen Endpoints
- **Audit-Logging**: Security-Events werden geloggt (Login, Password-Change, Admin-Ops)

---

## Empfohlene Priorisierung

### Sofort (diese Woche)
1. **Token-Lifecycle fixen**: K1 + K2 + K3 zusammen beheben (decode_token type, JTI mapping, TTL, Logout)
2. **`/api/metrics` hinter Auth setzen** (K4)
3. **`is_active` Check in `get_current_user` ergänzen** (H1)
4. **IDOR bei Mobile Camera/Sync fixen** (H2)

### Kurzfristig (2 Wochen)
5. `registration_enabled` Default auf `False` + Prod-Validator (H6)
6. Brute-Force Counter nicht resetten (H3)
7. 2FA Rate-Limit per User-ID (H4)
8. VPN-Key Encryption bei fehlendem Key abbrechen statt Plaintext (H8)
9. SMART Device Allowlist (H9)
10. WebSocket Token-Fallback entfernen (H10)

### Mittelfristig (1 Monat)
11. `passlib` durch `bcrypt` direkt ersetzen (H7)
12. CSP `connect-src` auf `'self'` einschränken (M3)
13. TOTP-Encryption-Key vom VPN-Key trennen (H5)
14. Übrige MEDIUM-Findings abarbeiten

---

## Known Gaps Update

Die folgenden dokumentierten Known Gaps (aus `security-agent.md`) haben sich verändert:

| # | Dokumentiert | Aktueller Status |
|---|---|---|
| 8 | `change-password` uses raw `dict` | **Behoben** — nutzt jetzt `ChangePasswordRequest` Pydantic-Model |
| 9 | VPN encryption key "fails loudly if missing" | **Ungenau** — tatsächlich silent fallback zu Plaintext (H8) |

---

## Quellen

- [OWASP Top 10:2025](https://owasp.org/Top10/2025/)
- [OWASP Top 10 2025 Changes - GitLab](https://about.gitlab.com/blog/2025-owasp-top-10-whats-changed-and-why-it-matters/)
- [JWT Vulnerabilities 2026 - Red Sentry](https://redsentry.com/resources/blog/jwt-vulnerabilities-list-2026-security-risks-mitigation-guide)
- [FastAPI Security Best Practices 2025](https://toxigon.com/python-fastapi-security-best-practices-2025)
- [FastAPI CVE Database - Snyk](https://security.snyk.io/package/pip/fastapi)
- [Self-hosted Hardening 2026](https://readthemanual.co.uk/secure-your-homelab-2025/)
