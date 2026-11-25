# Security Enforcement Agent

Active security enforcement rule for BaluHost. Applies to all changes in `backend/app/`, `client/src/`, authentication, file operations, and system commands. Claude MUST verify compliance with these invariants before generating or reviewing code.

---

## Security Invariants

### NEVER

- Use `shell=True` in `subprocess.run()` or `subprocess.Popen()` — all 15+ service files use list-args exclusively; the only `shell=True` is in `scripts/setup/setup_postgresql.py` (one-time admin script, not app code)
- Execute raw SQL with user-controlled input — ORM-only; sole exceptions: static
  query strings in `services/audit/admin_db.py`, and `LISTEN`/`pg_notify` in
  `services/ws_bus.py` (the channel name is a module constant asserted to be a
  bare identifier at import; `LISTEN` cannot take a bind parameter, the payload
  always does)
- Log secrets, tokens, passwords, or API keys — not even at DEBUG level
- Return password hashes, internal stack traces, or server internals in API responses
- Disable or bypass the token-type check in `core/security.py:163` (`payload.get("type") != token_type`)
- Bypass `_jail_path()` for user-facing file operations (`api/routes/files.py:38`)
- Use default secrets (`"change-me-in-prod"`) in production — `config.py:206-242` validates this
- Commit `.env` or `.env.production` files
- Expose VPN private keys, SSH keys, or Fernet encryption keys in responses or logs
- Add new endpoints without authentication dependencies (unless explicitly public)

### ALWAYS

- Use `Depends(deps.get_current_user)` or `Depends(deps.get_current_admin)` on protected endpoints
- Use `ensure_owner_or_privileged()` from `services/permissions.py` for ownership checks
- Apply rate-limiting via `@limiter.limit(get_limit("..."))` on new endpoints (`core/rate_limiter.py`) — there is **no global fallback limit**: `default_limits` are empty because `SlowAPIMiddleware` is not installed, so an undecorated route is unlimited at the app layer
- Use Pydantic schemas for request body validation — never accept raw `dict` payloads
- Reject `..` in all user-supplied file paths
- Log security-relevant actions via `get_audit_logger_db()` (login, password change, admin ops, failed auth)
- Use `subprocess.run()` with explicit argument lists (never string commands)
- Ensure new sensitive database columns match `REDACT_PATTERN` in `services/audit/admin_db.py:13`

---

## Auth & Authorization Reference

### Token Types
| Type | TTL | Claim `type` | Features |
|------|-----|---------------|----------|
| Access | admin-configurable via `auth_policy.access_token_minutes`, default 15 min (`ACCESS_TOKEN_EXPIRE_MINUTES` is now only the fallback when the policy is unreadable) | `"access"` | Contains `sub`, `username`, `role`. Issued exclusively through `routes/auth.py:_issue_session_token()` — a route calling `auth_service.create_access_token()` directly would silently ignore the setting, and `tests/api/test_session_token_ttl.py` fails if one does |
| Refresh | 7 days (`REFRESH_TOKEN_EXPIRE_DAYS`) | `"refresh"` | Contains `jti` for revocation |
| SSE | 60 sec | `"sse"` | Scoped to single `upload_id`, safe for query params |
| WS | 60 sec | `"ws"` | WebSocket handshake, contains `sub` + `username` |
| 2FA pending | 5 min | `"2fa_pending"` | Issued between password check and TOTP verify; carries `sub` only |
| Setup | 30 min | `"setup"` | Setup wizard; `role: admin` but only accepted by setup endpoints |

### Dependency Chain
```
get_current_user          — JWT validation, returns UserPublic
  get_current_admin       — Depends on above, checks role == "admin"
get_current_user_optional — Returns None if no token (for optional auth)
verify_mobile_device_token — Validates JWT + X-Device-ID header + device expiry
```

### Role Model
- Roles: `admin`, `user`
- `is_privileged(user)` checks against `settings.privileged_roles` (configurable)
- Admin-only endpoints use `Depends(deps.get_current_admin)`
- `can_unlock_session` (power permission) entsperrt die grafische Desktop-Session
  beim Einschalten der Displays. Doppelt gegated: Recht **und**
  `is_private_or_local_ip(request.client.host)` — die Web-App ist von außen
  erreichbar, und ein gestohlenes Web-Konto darf keinen physischen Desktop
  öffnen. Durchgesetzt ausschließlich in
  `services/power/session_lock.unlock_if_permitted()`, die auch den
  Audit-Eintrag schreibt.
- `can_manage_bluetooth` (power permission) verbindet, entfernt und koppelt
  Bluetooth-Geräte. Koppeln und Bestätigen sind doppelt gegated: Recht **und**
  `is_private_or_local_ip(request.client.host)` — für alle Rollen, VPN zählt als
  lokal. Ein gekoppeltes Eingabegerät tippt in die Desktop-Session; ein
  gestohlenes Web-Konto plus Funkreichweite darf dafür nicht reichen.
  Durchgesetzt in `plugins/installed/bluetooth/service.py` (`start_pairing`,
  `answer`); abgelehnte Versuche von außen werden auditiert.
- `can_launch_games` (power permission) startet installierte Steam-Spiele über
  `/api/plugins/steam_gaming/games/{app_id}/launch` und schaltet dabei **faktisch
  auch die Displays ein und öffnet Big Picture** — ohne `can_toggle_desktop`; das
  ist der Zweck des Rechts. Entsperren bleibt bei `can_unlock_session`. Start nur
  bei `is_private_or_local_ip(request.client.host)` für alle Rollen; abgelehnte
  Versuche werden mit IP auditiert. API-Keys erreichen die Route wie alle
  `require_power_*`-Routen (bewusst akzeptiert). Die App-ID muss
  `re.fullmatch("[0-9]{1,10}")` erfüllen und als Manifest installiert sein; die
  URL wird aus dem Bibliothekseintrag gebaut. Durchgesetzt in
  `plugins/installed/steam_gaming/routes.py`.
- `GET /api/plugins/steam_gaming/session-state` liefert dem Desktop-Tray einen
  einzelnen Boolean ("läuft gerade eine Spielsitzung"), damit es Popups
  zurückhält. Bewusst **kein** `require_power_launch_games` — das Recht zu
  fragen würde dem Tray zugleich die Fähigkeit geben, Spiele zu starten;
  stattdessen `get_current_user`. Aber **dasselbe LAN-Gate wie `launch`**:
  `is_private_or_local_ip(request.client.host)` für alle Rollen. Der Boolean
  ist ein Anwesenheitsorakel — "sitzt gerade jemand physisch an der
  Maschine" —, und das ist eine Auskunft über den Besitzer, nicht über den
  NAS. Das Tray läuft laut Entwurf ohnehin in der Desktop-Sitzung, das Gate
  kostet es also nichts. Abgelehnte Zugriffe werden mit IP auditiert,
  erfolgreiche **nicht**: das Tray fragt alle 30 Sekunden, ein Eintrag je
  Abfrage würde die Spur zuschütten statt eine zu sein. Durchgesetzt in
  `plugins/installed/steam_gaming/routes.py`.
- Das Plugin `local_tls` (standardmäßig aus) hält einen DuckDNS-Namen auf der
  LAN-IP und holt per `lego` (DNS-01) ein Let's-Encrypt-Zertifikat. Alle Routen
  unter `/api/plugins/local_tls/` sind `get_current_admin`, Audit-Aktionen
  `local_tls_credentials_changed`, `local_tls_renew_triggered`,
  `local_tls_dns_update_triggered`. **Keine neue sudoers-Regel:** nginx wird nur
  über das bestehende `sudo -n /usr/bin/systemctl reload nginx` neu geladen; lego
  und certbot laufen nie als root, Zertifikate liegen unter
  `/var/lib/baluhost/plugins/local_tls/` (Verzeichnisse 0700, Schlüssel 0600).
  *Ehrliche Grenze:* der Dienstnutzer kann die nginx-Site ohnehin selbst
  umschreiben (#862) — das Plugin erweitert diese Fähigkeit nicht, es schließt
  sie aber auch nicht. *Token:* Fernet (`VPN_ENCRYPTION_KEY`) in
  `local_tls_state.provider_secret` (passt auf `REDACT_PATTERN`), eigene
  Schreib-Route (nie in Antworten, Logs, Audit oder Fehlertexten); ohne Schlüssel
  lehnt sie mit 400 ab statt Klartext zu speichern. Die übrigen Einstellungen
  laufen über die generische Plugin-Konfiguration (Core-Routen, nur Admin); echte
  Secret-Felder im Core sind #863. *Adapter-Regeln:* nur HTTPS zum Host des
  Anbieters, Timeout ≤ 15 s, kein Shell-Aufruf, keine Dateizugriffe, Domain und
  IP vor jedem Aufruf validiert, nur private IPv4. Durchgesetzt in
  `plugins/installed/local_tls/`.
- `POST /api/system/restart-all` startet alle fünf BaluHost-Units neu. Dreifach
  gegated: `get_current_admin`, `is_private_or_local_ip(request.client.host)`
  und ein Step-up (`services/step_up.verify_step_up`) — Code bei aktivem 2FA,
  sonst Passwort. **API-Keys werden abgelehnt** (`auth_method == "api_key"` →
  403): ein Step-up soll Anwesenheit belegen, und ein Key-Aufrufer fiele in
  `get_user_identifier` auf den IP-Schlüssel zurück und könnte das Rate-Limit
  über beliebige Quell-IPs aufweichen. Ein gescheiterter Step-up antwortet 401
  mit `{"error": "step_up_failed", "totp_required": …}`; die Unterscheidung zum
  abgelaufenen Token ist Teil des Vertrags, der Client reagiert auf beides
  anders. Rate-Limit `system_restart` (5/minute). Durchgesetzt in
  `api/routes/system.py`.

  **Was der Step-up nicht deckt:** `POST /api/system/restart` startet
  `baluhost-backend` weiterhin allein mit dem Admin-Token, ohne zweiten
  Nachweis und ohne LAN-Gate (Issue #699). Wer ein Tray-Token hat, erreicht die
  Fähigkeit „Backend neu starten" also auch ohne Step-up. Geschützt ist der
  *Sammel*neustart, nicht die Fähigkeit als solche.

- **Tray-Auto-Login (Handoff) und Token-Rotation (#847).** „BaluHost öffnen"
  im Tray meldet den Browser ohne Passwort an. Ablauf: das Tray schickt sein
  Geräte-Refresh-Token an `POST /api/auth/handoff`, bekommt einen 30 s gültigen
  Einmal-Code und öffnet `…/login#handoff=<code>`; die Web-UI löst ihn über
  `POST /api/auth/handoff/redeem` gegen eine normale Sitzung ein
  (`_issue_session_token`, also mit der `auth_policy`-Laufzeit).
  - *Nachweis ist das Refresh-Token einer Desktop-/Geräte-Kopplung*, kein
    Access-Token. Es zählt als **Benutzung** (Lazy-Revoke, siehe unten) und
    wird vor der PIN-Prüfung verbraucht. Ein Token ohne `device_id` wird
    abgelehnt (`session_handoff_failed`).
  - *LAN-Gate nur beim Ausstellen* (`is_private_or_local_ip(request.client.host)`,
    alle Rollen). Abgelehnt → `session_handoff_remote_denied`. Beim Einlösen
    **bewusst kein** Gate: der Browser erreicht die Web-UI womöglich über eine
    öffentliche `--web-url` per Hairpin-NAT und käme sonst nicht durch; der
    Code ist ohnehin nur 30 s gültig und einmalig.
  - *Code*: nur SHA-256 gespeichert (Spalte `token_hash`), Einlösen ist ein
    einziges atomares `UPDATE` (auch über Worker hinweg einmalig). Codes landen
    nie in Logs oder Audit-Einträgen.
  - *PIN*: Hat das Konto eine PIN, ist sie Pflicht (bestehende Sperre,
    unabhängig von `pin_login_enabled`); Fehlversuch → `session_handoff_pin_failed`.
  - *Bewusst kein Passwort und kein 2FA* — vom Besitzer am 2026-11-25 so
    entschieden. Vertrauensmodell: der Aufrufer sitzt auf der BaluHost-Maschine
    selbst, hält eine Kopplung, die aus einer angemeldeten Sitzung heraus
    freigegeben wurde, und die Desktop-Sitzung ist entsperrt. LAN-Gate und PIN
    schützen den **Klick am Desktop**, nicht das Token: wer das Kopplungs-Token
    stiehlt, holt sich über `POST /api/auth/refresh` von überall ein volles
    Access-Token, ganz ohne LAN und PIN. Der Handoff gibt nichts her, was das
    Token über `/auth/refresh` nicht ohnehin schon hat — er ist kein
    zusätzlicher Schutz des Tokens, sondern nur kein zusätzliches Risiko.
  - Audit: `session_handoff_issued`, `session_handoff_remote_denied`,
    `session_handoff_failed`, `session_handoff_pin_failed`,
    `session_handoff_redeemed`, `session_handoff_redeem_failed`.
    Rate-Limits `auth_handoff` und `auth_handoff_redeem` (je 10/minute).
  - *Web-UI* (`client/src/pages/Login.tsx`): der Code steht im URL-Fragment
    (erscheint nie in Server-Logs) und wird vor dem Einlösen per
    `history.replaceState` entfernt. Existiert eine Sitzung eines **anderen**
    Kontos, verlangt die UI eine Bestätigung („Konto wechseln?") — Schutz gegen
    Session-Swap per Login-CSRF; ohne Sitzung oder bei gleichem Konto läuft es
    automatisch.
  - **Rotation** (`services/refresh_rotation.py`): opt-in über `rotate: true`
    in `/auth/refresh`, nur für Desktop-Kopplungen — es muss eine
    `SyncState(user_id, device_id)`-Zeile geben **und** darf keine
    `MobileDevice` mit dieser ID für den Nutzer existieren (Mobile-Tokens
    behalten ihre vom Admin gesetzte Laufzeit). Rotiert wird nur in der zweiten
    Hälfte von `REFRESH_TOKEN_EXPIRE_DAYS`. *Lazy Revoke*: der Vorgänger wird
    erst beim ersten Gebrauch des Nachfolgers widerrufen (`rotated`); ein
    unbenutzter Nachfolger wird bei erneuter Rotation `superseded`. Wer ein
    `rotated`- **oder** `superseded`-Token vorlegt, löst Reuse-Erkennung aus:
    alle Tokens dieses Nutzers für dieses Gerät werden widerrufen
    (`reuse_detected`, Audit `refresh_token_reuse_detected`). Der Widerruf ist
    immer auf `user_id` **und** `device_id` begrenzt, weil die `device_id`
    clientseitig gewählt ist. Liefern zwei gleichzeitige Rotationen desselben
    Vorgängers je einen Nachfolger, widerruft die erste Nutzung eines davon
    die unbenutzten Geschwister als `superseded`.
  - **Neukopplung widerruft die alte Kette:** Eine freigegebene Desktop-Kopplung
    widerruft vor dem Ausstellen alle Tokens desselben Nutzers auf derselben
    `device_id` (`repaired`, `services/desktop_pairing.py:_issue_tokens`). Das
    Tray nimmt die machine-id als `device_id`, jedes `--pair` verwendet sie
    wieder; mit gleitender Rotation lebte die alte Kette sonst ewig.
  - **Nur Token-Fehler sind 401:** `/auth/refresh` und `/auth/handoff`
    antworten 401 ausschließlich bei `RefreshTokenReused`/`RefreshTokenInvalid`.
    Ein anderer Fehler (z. B. DB nicht erreichbar) endet als 5xx — das Tray
    wertet 401 als Widerruf und vergisst seine Kopplung.
  - **Desktop-Geräte sind widerrufbar:** `DELETE /api/devices/desktop/{device_id}`
    (Besitzer oder Admin) widerruft die Tokens (`device_removed`), löscht die
    `SyncState`-Zeile und schreibt `desktop_device_removed` ins Audit.
  - **Akzeptierte Restrisiken** (hier statt in „Known Gaps", weil sie Teil des
    Vertrags dieses Features sind): (1) *Lazy-Revoke-Lücke* — ein Dieb, der
    das Token in der zweiten Lebenshälfte mit `rotate: true` vorlegt, bekommt
    einen eigenen Nachfolger. Benutzt er ihn, wird das Token des Trays
    `rotated`; rotiert stattdessen das Tray erneut, wird der Nachfolger des
    Diebs `superseded`. Die Erkennung schlägt erst an, wenn die jeweils andere
    Seite danach ihr nun `rotated`/`superseded` gewordenes Token vorlegt —
    dann widerruft sie alle Tokens des Geräts; im ersten Fall ist das der
    nächste Refresh des Trays. Bis dahin läuft die Sitzung des Diebs. Legt er
    das Token nur ohne `rotate` vor (oder nur am Handoff), entsteht gar kein
    Signal — er teilt sich die Kette dann unbemerkt mit dem Tray. (2) *Login-CSRF ohne bestehende Sitzung* braucht ein
    eigenes gekoppeltes Gerät des Angreifers, LAN-Zugang und einen Klick des
    Opfers innerhalb von 30 s. (3) Der Code steht bis zum Einlösen (~1 s) in
    den Prozessargumenten des Browsers (`/proc/<pid>/cmdline`); ausnutzbar nur
    mit einem zweiten lokalen Konto auf der Maschine — der Besitzer ist der
    einzige Nutzer. (4) *Entfernen widerruft keine Access-Tokens:* nach
    `DELETE /api/devices/desktop/{device_id}` (oder einer Neukopplung) bleibt
    ein schon ausgestelltes Access-Token gültig, bis es abläuft — die
    `auth_policy`-Laufzeit, höchstens 24 h (`MAX_TOKEN_MINUTES` = 1440). Es
    gibt keine serverseitige Sperrliste für Access-Tokens.

### Password Policy (`schemas/auth.py:20-59`)
- Length: 8-128 characters
- Required: uppercase + lowercase + digit
- Blacklist: 11 common passwords (case-insensitive comparison)
- Enforced via Pydantic `field_validator` on `RegisterRequest`

### Key Files
- `core/security.py` — Token creation/verification (HS256)
- `api/deps.py` — FastAPI dependency injection for auth
- `schemas/auth.py` — Login/Register schemas, password validation
- `services/permissions.py` — `is_privileged()`, `ensure_owner_or_privileged()`

---

## Input Validation & Path Safety

### `_jail_path()` (`api/routes/files.py:38-80`)
- **Admin**: path returned unchanged (via `is_privileged()`)
- **User**: restricted to own home dir, `Shared/`, `Shared with me`, or FileShare-validated paths
- **Always**: rejects `..` components, normalizes path via `PurePosixPath`
- Used in: `files.py` (8 call sites), `chunked_upload.py` (1 call site)

### System Directories
- `.system` — internal metadata, avatars, thumbnails
- `lost+found` — filesystem recovery, hidden from users
- `.Trash-*` — trash directories, hidden from users

### Subprocess Safety
- 15+ service files use `subprocess.run()` — all with list arguments
- Zero `shell=True` usage in application code
- User input must never be interpolated into command strings

### Frontend
- React JSX auto-escapes output — do not use React's raw-HTML escape hatch
- No dynamic code evaluation in source
- API responses rendered through typed React components

---

## Data Protection

### Secrets Validation
- `SECRET_KEY`: production validator requires 32+ chars, rejects default (`config.py:206-223`)
- `token_secret`: same validation (`config.py:225-242`)
- Both use `field_validator` — app refuses to start with weak secrets in prod

### Encryption at Rest
- VPN/SSH keys: Fernet (AES-128-CBC) via `services/vpn/encryption.py`
- `VPNEncryption.encrypt_key()` / `decrypt_key()` — requires `VPN_ENCRYPTION_KEY` env var
- Key validated at use-time (raises `ValueError` if missing)

### Admin Database Inspection
- `REDACT_PATTERN = password|secret|token|private_key|api_key` (`services/audit/admin_db.py:13`)
- Applied to all column values before returning in admin-db API responses

### Token Storage (Frontend)
- JWT stored in `localStorage` — accepted trade-off (see Known Gaps)
- Mitigated by CSP headers restricting script sources

---

## OWASP Threat Categories for NAS

### 1. Broken Authentication
- **Mitigations**: Rate-limiting on login/register/password-change, JWT type claims prevent token confusion, short access TTL (15min), JTI on refresh tokens
- **Watch for**: New auth endpoints without rate limits, token handling that skips type verification

### 2. Broken Access Control
- **Mitigations**: `_jail_path()` enforces per-user file isolation, `ensure_owner_or_privileged()` for resource ownership, admin-only routes via `get_current_admin`
- **Watch for**: New file operations bypassing `_jail_path()`, endpoints missing auth dependencies, ownership checks using string comparison instead of int

### 3. Injection
- **Mitigations**: SQLAlchemy ORM-only (no raw SQL with user input), subprocess with list-args, path normalization via `PurePosixPath`
- **Watch for**: String interpolation in subprocess commands, raw SQL queries, `os.path.join` with unsanitized user paths

### 4. Security Misconfiguration
- **Mitigations**: Production secret validators refuse weak defaults, security headers middleware (CSP, X-Frame-Options, HSTS, X-Content-Type-Options), structured JSON error responses hide internals
- **Watch for**: Debug/verbose error messages leaking to API responses, new config values without prod validation

### 5. Sensitive Data Exposure
- **Mitigations**: Fernet encryption for VPN/SSH keys, `REDACT_PATTERN` in admin-db, audit log filtering
- **Watch for**: New API responses exposing hashed passwords, private keys, or internal tokens; logging sensitive data

### 6. SSRF
- **Attack surfaces**: Cloud import (rclone with user-specified remotes), remote server SSH connections, Tapo smart plug communication
- **Watch for**: User-controlled URLs passed to server-side HTTP clients without validation, new external service integrations

---

## Security Review Checklist

### New API Endpoints
- [ ] Auth dependency present? (`get_current_user` / `get_current_admin`)
- [ ] Rate-limiting configured? (`@limiter.limit(get_limit("..."))`)
- [ ] Pydantic schema for request body? (not raw `dict`)
- [ ] Audit logging for security-relevant events?
- [ ] Response contains only data the requester is authorized to see?
- [ ] Added to `@requires_power()` if applicable?

### File Operations
- [ ] Path validated through `_jail_path()`?
- [ ] Ownership checked via `ensure_owner_or_privileged()`?
- [ ] System directories (`.system`, `lost+found`, `.Trash-*`) protected?

### Subprocess / System Commands
- [ ] `subprocess.run()` with list arguments? (no string commands)
- [ ] No `shell=True`?
- [ ] User input sanitized before inclusion in command args?
- [ ] Timeout set to prevent hangs?

### Database
- [ ] ORM-only queries? (no raw SQL with user input)
- [ ] New sensitive columns match `REDACT_PATTERN`?
- [ ] No sensitive data in query logs?

### Frontend
- [ ] No raw-HTML rendering bypass? (use React JSX auto-escaping)
- [ ] User input sanitized before display?
- [ ] API error messages don't leak server internals?

### Config & Secrets
- [ ] New secrets have production validation? (32+ chars, no defaults)
- [ ] `.env` variables documented in `.env.example`, not committed?
- [ ] No hardcoded secrets in source code?

---

## Known Gaps & Accepted Risks

Do NOT attempt to fix these without explicit discussion — they are documented trade-offs.

**Scope note:** this list covers gaps in *our own* code. Dispositions for
third-party **advisories** (Dependabot / Code Scanning) that are deliberately not
fixed live in `docs/security/DEPENDENCY_ADVISORIES.md` — deliberately outside the
auto-loaded rules, because that register grows with every dismissal and would
otherwise cost context in every session. Before proposing a dependency bump to
close an alert, check whether that file already rules on it.

1. **CSP `unsafe-inline` / `unsafe-eval`** — Required by Vite dev server; production build could tighten this but currently uses same policy (`middleware/security_headers.py:29-30`)
2. **CORS `allow_methods=["*"]` / `allow_headers=["*"]`** — Scoped to configured `cors_origins` list (`main.py:558-564`), not a wildcard origin
3. **In-memory rate limiter** — Resets on service restart; acceptable for single-instance deployment
4. **JTI without universal revocation check** — Refresh tokens have JTI but no server-side revocation store; rotation is the primary defense
5. **No CSRF protection** — Mitigated by JWT Bearer auth (not cookie-based); no state-changing cookie auth exists
6. **Plain HTTP remains on the backend port (8000)** — The web UI is HTTPS-only: nginx terminates TLS on 443, answers port 80 with a 301 and sets HSTS (`deploy/nginx/baluhost-https.conf`; observed on the production box 2026-11-16: `:80` → 301, `:443` → 200 with `strict-transport-security`). What is left of the old "HTTPS not enforced" entry is the Uvicorn port: `baluhost-backend.service` binds `--host 0.0.0.0 --port 8000`, so a client on the LAN can still reach the API unencrypted by going around nginx. The desktop tray and the TUI use that port from the box itself. `--forwarded-allow-ips=127.0.0.1` keeps such a client from forging its source address, so the LAN gates hold. Accepted under the same reasoning as before — HTTP on the trusted LAN, remote access through the WireGuard tunnel — but it now covers one port instead of the whole UI. Whether a host firewall closes 8000 is not recorded here
7. **Token in localStorage** — XSS risk mitigated by CSP headers; HttpOnly cookies would require significant auth refactor
8. **`change-password` uses raw `dict`** — `api/routes/auth.py:121` accepts `payload: dict` instead of Pydantic model, meaning new passwords bypass the `RegisterRequest` password strength validator
9. **VPN encryption key empty default** — Validated at use-time in `VPNEncryption` methods, not at startup; fails loudly if missing
10. **Der Tray-Notweg schreibt keinen Audit-Eintrag, und sein Rate-Limit ist
    zurücksetzbar** — Zwei getrennte Einschränkungen desselben Features
    (`docs/superpowers/specs/2026-09-22-tray-service-restart-design.md`):

    *Audit:* Antwortet das Backend nicht, startet `baluhost_tray/restart.py`
    die Units selbst über einen einzigen `systemctl restart`-Aufruf; systemd
    fragt polkit (`org.freedesktop.systemd1.manage-units`, `auth_admin_keep`),
    KDE zeigt den Dialog. Ein App-Audit ist dann unmöglich — die Datenbank ist
    so unerreichbar wie die API. Im Journal steht die polkitd-Zeile mit Nutzer,
    Aktion und Zeit; die systemd-Zeile nennt **keinen** Urheber, und ein
    abgebrochener Dialog hinterlässt **gar nichts**. Ein Nachtrag-Endpunkt
    wurde verworfen: ein vom Client behaupteter Audit-Eintrag ist schwächeres
    Beweismaterial als die Zeile, die polkitd selbst geschrieben hat.

    *Rate-Limit:* `system_restart` (5/minute) liegt im Prozessspeicher, gilt
    also pro uvicorn-Worker (vier, ohne `ip_hash` im nginx-Upstream) — und der
    Endpunkt startet genau diese Prozesse neu. Ein Angreifer mit Admin-Token
    kann seine Zähler über `/api/system/restart` zurücksetzen und den Step-up
    damit schneller raten, als die Zahl vermuten lässt. Belastbar wäre ein
    persistenter Fehlversuchszähler am Konto (wie `pin_failed_attempts`); das
    ist bewusst nicht gebaut.

    Der Notweg braucht **kein** neues Recht: kein polkit-Policy-File, keine
    sudoers-Zeile für den Desktop-Nutzer, `NoNewPrivileges=yes` bleibt.
    `systemctl` eskaliert nichts im eigenen Prozess. **Wichtig:** Er muss ein
    kurzlebiger Subprozess bleiben. Ein D-Bus-Aufruf von
    `Manager.RestartUnit` aus dem langlebigen Tray-Prozess würde die
    Autorisierung fünf Minuten an diesem Prozess halten, und `manage-units`
    deckt auch `StartTransientUnit` ab — also beliebige Codeausführung als root.
    Der API-Weg nutzt die bestehenden NOPASSWD-Einträge aus
    `baluhost-deploy-sudoers` (in der Vorlage jetzt fünf statt vier Units).
    Diese fünfte Zeile (`baluhost-backend-local`) erreicht eine bereits
    installierte Box aber nicht von selbst: `ci-deploy.sh` kann
    `/etc/sudoers.d/baluhost-deploy` nicht neu rendern — sie ist die eine
    sudoers-Datei, deren Erlaubnis erst die anderen drei installiert —, und
    `install-deploy-sudoers.sh` steht auch nicht in dessen
    `SYNC_PERMISSIONS=1`-Liste. Bis ein Operator es einmalig von Hand ausführt,
    bekommt `restart_unit("baluhost-backend-local")` `sudo: a password is
    required` zurück — fail-closed und laut: die Antwort meldet diese Unit als
    fehlgeschlagen, und der Companion-Kanal läuft mit altem Code weiter.

Entry 10 ("SECURITY.md outdated") was removed on 2026-07-21: the file had already
been rewritten, and its one remaining stale item — the supported-versions table —
is now maintained by `scripts/bump_version.py` (#349). It was never a gap in the
security posture, only in version metadata. The number was reassigned on
2026-09-22 to the tray-restart gap above — the two are unrelated entries, not
a duplicate.
