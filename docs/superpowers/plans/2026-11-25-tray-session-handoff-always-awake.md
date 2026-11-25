# Tray: gleitende Kopplung, Auto-Login, Always Awake — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Das Tray bleibt gekoppelt, solange es läuft; „BaluHost öffnen“ führt eingeloggt in die Web-UI; Always Awake ist im Rechtsklick-Menü umschaltbar; Desktop-Geräte sind widerrufbar.

**Architecture:** Backend bekommt opt-in Refresh-Token-Rotation mit „lazy revoke“ und Reuse-Erkennung (`services/refresh_rotation.py`), eine Route zum Entfernen von Desktop-Geräten und einen Einmal-Code-Handoff (`services/session_handoff.py`, DB-Tabelle). Frontend löst den Code aus dem URL-Fragment ein und bekommt einen Entfernen-Button. Im Tray liegt alle Logik in Qt-freien Modulen (`session.py`, `loop.py`, neu `handoff.py`, `awake.py`); `tray.py` verdrahtet nur.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, pytest; React 18 + TS, vitest, i18next; PyQt6, httpx, asyncio.

**Spec:** `docs/superpowers/specs/2026-11-25-tray-session-handoff-always-awake-design.md`

## Global Constraints

- Hinweis Umgebung: Ein Hook blockiert Shell-Befehle mit `grep`/`rg`; vectorgrep ist auf BaluNode nicht verfügbar → Read-Tool, `awk`, `find`.
- Rotation nur mit `rotate: true` **und** Token-Zeile mit `device_id` **und** Restlaufzeit < 50 % von `settings.REFRESH_TOKEN_EXPIRE_DAYS`. Ohne `rotate` ändert sich an `/auth/refresh` nichts (BaluDesk, BaluApp).
- Widerrufsgründe exakt: `"rotated"` (Vorgänger, sobald Nachfolger benutzt), `"superseded"` (unbenutzter Nachfolger bei erneuter Rotation), `"device_removed"`, `"reuse_detected"`.
- Handoff-Code: `secrets.token_urlsafe(32)`, gültig **30 s**, nur SHA-256-Hash gespeichert, Spalte heißt `token_hash`.
- Rate-Limit-Schlüssel: `auth_handoff` = `"10/minute"`, `auth_handoff_redeem` = `"10/minute"`, eingetragen in `core/rate_limiter.py:RATE_LIMITS` **und** `services/rate_limit_config.py` (Defaults-Liste).
- Jede neue Access-Token-Ausgabe nur über `routes/auth.py:_issue_session_token()`.
- Tokens, Handoff-Codes und PINs werden **nie** geloggt oder auditiert (nur Nutzer, device_id, IP).
- Audit-Aktionen exakt: `refresh_token_rotated`, `refresh_token_reuse_detected`, `desktop_device_removed`, `session_handoff_issued`, `session_handoff_remote_denied`, `session_handoff_redeemed`, `session_handoff_redeem_failed`.
- Tray-Texte (deutsch): Untermenü `"Always Awake"`, Einträge `"Aus"`, `"1 Stunde"`, `"8 Stunden"`, `"Dauerhaft"`; Titel mit Frist `"Always Awake — bis HH:MM"`; Tooltip ungekoppelt `"BaluHost — nicht gekoppelt. Einmalig ausführen: baluhost-tray --pair"`.
- Frontend-Texte in `de` **und** `en`.
- Tests laufen auf BaluNode nur in der Sandbox (siehe Memory „Prod-Box: kein sudo, pytest nur in Sandbox“); Befehl unten als `PYTEST` abgekürzt: `cd backend && python -m pytest`.

## Review Focus

1. **Backend-Neustart mitten in einer Rotation** (Antwort kommt nie an) → Tray benutzt weiter den alten Token, bekommt beim nächsten Refresh einen neuen Nachfolger, Kopplung bleibt. Test in Task 2 (`test_lost_rotation_response_does_not_cost_the_pairing`).
2. **Zwei Threads refreshen gleichzeitig im Tray** (Loop + Handoff/Neustart) → serialisiert, zweiter liest den frisch gespeicherten Token. Test in Task 6 (`test_concurrent_refreshes_are_serialized`).
3. **Bereits eingeloggter Browser bekommt `/login#handoff=…`** → wird nicht auf `/` umgeleitet, bevor der Code eingelöst ist; Sitzung wird ersetzt. Test in Task 5 (`App.routing` Fall).
4. **Token-Datei halb geschrieben / Prozess stirbt beim Speichern** → alte oder neue Datei, nie leer. Test in Task 6 (`test_save_tokens_is_atomic`).
5. **Handoff-Code doppelt eingelöst** (Doppelklick, zweiter Tab, Browser-Prefetch) → genau ein Erfolg, zweiter 401. Test in Task 4 (`test_code_is_single_use`).

---

### Task 1: Token-Service — Vorgänger-Spalte und Varianten ohne Commit

**Files:**
- Modify: `backend/app/models/refresh_token.py` (Spalte `parent_jti`)
- Create: `backend/alembic/versions/refresh_token_parent_jti_2026_11_25.py` (`down_revision` = Ausgabe von `alembic heads`)
- Modify: `backend/app/services/token_service.py`
- Test: `backend/tests/services/test_token_service.py`

**Interfaces:**
- Produces:
  - `RefreshToken.parent_jti: Mapped[Optional[str]]` (`String(36)`, nullable, index)
  - `token_service.store_refresh_token(..., parent_jti: str | None = None, commit: bool = True) -> RefreshToken`
  - `token_service.revoke_token(db, jti, reason=..., commit: bool = True) -> bool` (bestehende Signatur + `commit`)
  - `token_service.revoke_device_tokens(db, device_id, ..., reason=..., commit: bool = True) -> int`

- [ ] **Step 1: Failing tests** in `test_token_service.py`:
  - `test_store_refresh_token_keeps_parent_jti`: speichert mit `parent_jti="p-1"`, `get_token_by_jti(...).parent_jti == "p-1"`.
  - `test_store_without_commit_is_rolled_back_with_the_session`: `store_refresh_token(..., commit=False)`, dann `db.rollback()` → `get_token_by_jti` ist `None`.
  - `test_revoke_without_commit_is_rolled_back_with_the_session`: analog für `revoke_token(..., commit=False)` → nach Rollback nicht widerrufen.
- [ ] **Step 2:** `PYTEST tests/services/test_token_service.py -v` → FAIL (unexpected keyword `parent_jti`/`commit`).
- [ ] **Step 3:** Spalte, Migration (add column + index, downgrade drop), `commit`-Parameter (bei `False` nur `db.flush()`).
- [ ] **Step 4:** `PYTEST tests/services/test_token_service.py tests/migrations -v` → PASS.
- [ ] **Step 5:** Commit `feat(auth): Vorgänger-Spalte und Commit-freie Varianten im Token-Service (#847)`.

---

### Task 2: Gleitende Rotation in `/auth/refresh`

**Files:**
- Create: `backend/app/services/refresh_rotation.py`
- Modify: `backend/app/schemas/auth.py` (`RefreshTokenRequest.rotate`, `TokenResponse.refresh_token`)
- Modify: `backend/app/api/routes/auth.py:refresh_token()` (nutzt den Service, Docstring „rotiert nicht“ umschreiben)
- Modify: `backend/app/services/desktop_pairing.py:_issue_tokens` → nutzt `issue_device_refresh_token`
- Test: `backend/tests/api/test_refresh_rotation.py`

**Interfaces:**
- Consumes: Task 1.
- Produces (in `services/refresh_rotation.py`):
  - `class RefreshTokenInvalid(Exception)` — generisch 401
  - `class RefreshTokenReused(Exception)` — trägt `device_id: str | None`, `user_id: int`
  - `def issue_device_refresh_token(db, user: User, device_id: str, parent_jti: str | None = None, commit: bool = True) -> str`
  - `def use_refresh_token(db, raw_token: str, ip_address: str | None) -> tuple[User, RefreshToken]` — decodiert (`token_type="refresh"`), Reuse-Check (**vor** dem generischen Widerrufs-Check: Zeile widerrufen mit Grund `"rotated"` → alle Tokens des `device_id` mit Grund `"reuse_detected"` widerrufen, `RefreshTokenReused`), sonstiger Widerruf/unbekannt/inaktiver Nutzer → `RefreshTokenInvalid`; bei gültigem Token: hat die Zeile `parent_jti` und ist der Vorgänger nicht widerrufen → Vorgänger mit `"rotated"` widerrufen; `update_token_usage`; ein Commit am Ende.
  - `def rotate_if_due(db, row: RefreshToken, user: User, now: datetime) -> str | None` — nur bei `row.device_id` und `row.expires_at - now < timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS) / 2`; widerruft unwiderrufene Zeilen mit `parent_jti == row.jti` (`"superseded"`), stellt neuen Token mit `parent_jti=row.jti` aus; ein Commit.
- Route: Reuse → Audit `refresh_token_reuse_detected` + 401; Invalid → bestehende Audit-Aktionen + 401 wie heute; Erfolg und `payload.rotate` → `rotate_if_due`, bei Rückgabe Audit `refresh_token_rotated` und `TokenResponse(refresh_token=...)`.

- [ ] **Step 1: Failing tests** in `test_refresh_rotation.py` (Hilfsfunktion `_paired_token(db, user, device_id, age_days)` legt via `issue_device_refresh_token` an und setzt `expires_at` passend zurück):
  - `test_without_rotate_flag_nothing_changes`: frischer und alter Token, ohne `rotate` → 200, `refresh_token` ist `None`.
  - `test_rotate_in_first_half_returns_no_new_token`: Alter 1 Tag (bei 7) → `refresh_token is None`.
  - `test_rotate_in_second_half_returns_successor`: Alter 4 Tage → neuer Token, neue Zeile hat `parent_jti == alter jti`, `expires_at ≈ now + 7 Tage`.
  - `test_token_without_device_id_is_never_rotated` (z. B. via `store_refresh_token` ohne device_id).
  - `test_old_token_stays_valid_until_successor_is_used`: nach Rotation alter Token → weiter 200.
  - `test_first_use_of_successor_revokes_predecessor`: Nachfolger benutzen → Vorgängerzeile `revoked`, Grund `"rotated"`.
  - `test_lost_rotation_response_does_not_cost_the_pairing`: rotieren, Antwort verwerfen, alten Token erneut mit `rotate` → 200 mit neuem Nachfolger; erster Nachfolger jetzt `"superseded"`; neuer Nachfolger funktioniert.
  - `test_reuse_of_rotated_token_revokes_the_device`: rotieren, Nachfolger benutzen, alten erneut vorlegen → 401; alle Zeilen dieses `device_id` widerrufen; Audit-Zeile `refresh_token_reuse_detected` existiert und enthält keinen Token-String.
  - `test_pairing_still_issues_a_storable_token` (bestehender `test_desktop_pairing_refresh.py` muss grün bleiben).
- [ ] **Step 2:** `PYTEST tests/api/test_refresh_rotation.py -v` → FAIL.
- [ ] **Step 3:** Service + Schema + Route + `_issue_tokens` umstellen.
- [ ] **Step 4:** `PYTEST tests/api/test_refresh_rotation.py tests/api/test_desktop_pairing_refresh.py tests/api/test_session_token_ttl.py tests/auth -v` → PASS.
- [ ] **Step 5:** Commit `feat(auth): gleitende Rotation für Geräte-Refresh-Tokens mit Reuse-Erkennung (#847)`.

---

### Task 3: Desktop-Gerät entfernen (Backend)

**Files:**
- Modify: `backend/app/services/mobile.py` (neben `update_desktop_device_name`)
- Modify: `backend/app/api/routes/devices.py`
- Test: `backend/tests/api/test_desktop_device_remove.py`

**Interfaces:**
- Produces:
  - `def remove_desktop_device(db, device_id: str, user_id: int, is_admin: bool) -> bool | None` — `None` = nicht gefunden, `ValueError` = fremdes Gerät ohne Admin; widerruft per `token_service.revoke_device_tokens(..., reason="device_removed")` und löscht die `SyncState`-Zeile. Abhängige Zeilen, die per FK an `SyncState`/`device_id` hängen, prüfen und mit entfernen (Test deckt das ab, falls vorhanden).
  - Route `DELETE /api/devices/desktop/{device_id}` → 204; 404/403 wie bei der Rename-Route; `@user_limiter.limit(get_limit("admin_operations"))`; Audit `desktop_device_removed` (Nutzer, device_id, IP).

- [ ] **Step 1: Failing tests:**
  - `test_owner_removes_own_desktop_device_and_its_tokens_die`: Gerät + `issue_device_refresh_token` für `regular_user`; DELETE mit `user_headers` → 204; `/auth/refresh` mit dem Token → 401; Gerät fehlt in `GET /api/devices`.
  - `test_user_cannot_remove_foreign_device` → 403, Tokens weiter gültig.
  - `test_admin_can_remove_foreign_device` → 204.
  - `test_unknown_device_is_404`.
  - `test_removal_is_audited`.
- [ ] **Step 2:** FAIL. **Step 3:** implementieren. **Step 4:** `PYTEST tests/api/test_desktop_device_remove.py -v` → PASS.
- [ ] **Step 5:** Commit `feat(devices): Desktop-Geräte entfernen widerruft ihre Kopplung (#847)`.

---

### Task 4: Session-Handoff (Backend)

**Files:**
- Create: `backend/app/models/session_handoff.py` (+ Export in `models/__init__.py`)
- Create: `backend/alembic/versions/session_handoff_codes_2026_11_25.py` (nach Task 1)
- Create: `backend/app/services/session_handoff.py`
- Modify: `backend/app/schemas/auth.py`, `backend/app/api/routes/auth.py`, `backend/app/core/rate_limiter.py`, `backend/app/services/rate_limit_config.py`
- Test: `backend/tests/api/test_session_handoff.py`

**Interfaces:**
- Consumes: `use_refresh_token` (Task 2), `pin_service.is_pin_locked / verify_pin / register_pin_failure / reset_pin_failures`, `core/network_utils.is_private_or_local_ip`.
- Produces:
  - Modell `SessionHandoffCode` (`session_handoff_codes`): `id`, `user_id` FK users, `token_hash String(64) unique index`, `expires_at`, `used_at` nullable, `created_at`, `created_ip String(45)`.
  - `session_handoff.HANDOFF_TTL_SECONDS = 30`
  - `def issue_code(db, user: User, ip: str | None) -> str` (löscht dabei Zeilen mit `expires_at < now - 1 Tag`)
  - `def redeem_code(db, code: str) -> User | None` — atomares `UPDATE … WHERE token_hash=:h AND used_at IS NULL AND expires_at > now`, `rowcount == 1`; Nutzer aktiv, sonst `None`.
  - Schemas: `HandoffRequest(refresh_token: str, pin: Optional[str] = None)`, `HandoffResponse(code: str, expires_in: int)`, `HandoffRedeemRequest(code: str)`.
  - `POST /api/auth/handoff` → 200 `HandoffResponse`; 403 `{"error": "local_network_required"}` außerhalb LAN (+ Audit `session_handoff_remote_denied` mit IP); 401 bei ungültigem/Browser-losem Token; PIN: 401 `{"error": "pin_required" | "pin_invalid" | "pin_locked"}`.
  - `POST /api/auth/handoff/redeem` → 200 `TokenResponse` via `_issue_session_token`; sonst 401 generisch.

- [ ] **Step 1: Failing tests** (LAN: `TestClient` meldet `testclient` als Host — Test-Helfer patcht `is_private_or_local_ip` in `app.api.routes.auth` auf True/False):
  - `test_paired_device_gets_a_code_and_browser_redeems_it`: redeem → 200, `access_token` gültig für `/auth/me`.
  - `test_access_token_alone_is_not_enough`: Body mit einem Access-Token statt Refresh-Token → 401.
  - `test_refresh_token_without_device_id_is_refused` → 401.
  - `test_outside_lan_is_refused_and_audited` → 403 + Audit.
  - `test_code_is_single_use`: zweites redeem → 401.
  - `test_code_expires_after_30_seconds`: Zeit per `freezegun`/Patch von `now` um 31 s vorstellen → 401.
  - `test_pin_required_when_account_has_pin` / `test_wrong_pin_counts_towards_lock` / `test_locked_pin_is_reported` / `test_correct_pin_gets_code` / `test_pin_ignored_without_account_pin`.
  - `test_redeemed_session_honours_auth_policy_ttl`: Policy auf 90 min → Token-TTL 90 (Helfer `_ttl_minutes` aus `test_session_token_ttl.py`).
  - `test_code_is_never_stored_in_clear`: DB-Zeile `token_hash != code`.
  - Bestehender `test_auth_routes_issue_tokens_only_through_the_helper` bleibt grün.
- [ ] **Step 2:** FAIL. **Step 3:** implementieren. **Step 4:** `PYTEST tests/api/test_session_handoff.py tests/api/test_session_token_ttl.py tests/test_admin_db.py -v` → PASS (`token_hash` wird von `REDACT_PATTERN` erfasst).
- [ ] **Step 5:** Commit `feat(auth): Einmal-Code-Handoff vom Tray in die Web-UI (#847)`.

---

### Task 5: Frontend — Handoff einlösen, Desktop-Gerät entfernen

**Files:**
- Create: `client/src/lib/sessionHandoff.ts`, Test `client/src/__tests__/lib/sessionHandoff.test.ts`
- Modify: `client/src/App.tsx` (Route `/login`), `client/src/pages/Login.tsx`
- Modify: Login-API-Modul (dort, wo `Login.tsx` heute den Login aufruft): `redeemHandoff(code: string): Promise<{ access_token: string; user: User }>`
- Modify: `client/src/api/devices.ts` (`removeDesktopDevice(deviceId: string): Promise<void>`), `client/src/pages/DevicesPage.tsx` bzw. die Komponente mit dem Umbenennen-Knopf
- Modify: `client/src/i18n/locales/{de,en}/login.json` (`handoff.failed`), `{de,en}/devices.json` (`remove`, `removeConfirmTitle`, `removeConfirmText`)
- Test: `client/src/__tests__/App.routing.test.tsx`

**Interfaces:**
- Produces: `hasHandoffFragment(hash: string): boolean`, `takeHandoffCode(loc: Pick<Location, 'hash' | 'pathname' | 'search'>, hist: Pick<History, 'replaceState'>): string | null` (liest `handoff=` aus dem Fragment, ruft `replaceState(null, '', pathname + search)` auf, gibt den Code zurück).

- [ ] **Step 1: Failing tests:**
  - `takeHandoffCode` gibt Code zurück und ruft `replaceState` ohne Fragment auf; ohne Fragment `null` und kein `replaceState`.
  - `App.routing`: eingeloggt + `/login#handoff=abc` rendert Login (kein Redirect); eingeloggt ohne Fragment → Redirect wie bisher.
- [ ] **Step 2:** `cd client && npx vitest run src/__tests__/lib/sessionHandoff.test.ts src/__tests__/App.routing.test.tsx` → FAIL.
- [ ] **Step 3:** Implementieren: Route `/login` leitet nur um, wenn `user && !hasHandoffFragment(location.hash)`. `Login.tsx` beim Mount: `takeHandoffCode` → `redeemHandoff` → `login(user, token)` → `navigate('/', { replace: true })`; Fehler → Maske mit `t('login:handoff.failed')` („Automatische Anmeldung fehlgeschlagen — bitte normal anmelden.“ / „Automatic sign-in failed — please sign in normally.“). Entfernen-Button für `type === 'desktop'` mit `ConfirmDialog`/`useConfirmDialog`, danach Liste neu laden.
- [ ] **Step 4:** vitest grün; `npm run build` grün.
- [ ] **Step 5:** Commit `feat(client): Tray-Handoff einlösen und Desktop-Geräte entfernen (#847)`.

---

### Task 6: Tray-Session — Rotation speichern, atomar schreiben, Lock

**Files:**
- Modify: `backend/baluhost_tray/config.py`, `backend/baluhost_tray/session.py`
- Test: `backend/tests/tray/test_config.py`, `backend/tests/tray/test_session.py`

**Interfaces:**
- Produces:
  - `config.save_tokens(tokens)` atomar: temporäre Datei `TOKEN_DIR / f".tray-tokens.{os.getpid()}.tmp"` mit `O_CREAT|O_EXCL|O_WRONLY`, Modus `0o600`, `fsync`, `os.replace`.
  - `Session` hält `self._lock = threading.RLock()`; `refresh_access()` unter Lock, liest Tokens frisch, sendet `{"refresh_token": ..., "rotate": True}`, speichert `data.get("refresh_token") or tokens.refresh`.
  - `Session.reload() -> bool` — lädt Tokens neu, setzt/entfernt den Header, `True` wenn vorhanden.
  - `Session.current_refresh_token() -> str | None` (unter Lock).

- [ ] **Step 1: Failing tests:**
  - `test_save_tokens_is_atomic`: `os.replace` auf Exception patchen → alte Datei unverändert lesbar, keine `.tmp` zurück (aufräumen im `except`).
  - `test_saved_file_is_0600` (bestehend, muss grün bleiben).
  - `test_refresh_sends_rotate_flag`; `test_rotated_refresh_token_is_stored`; `test_missing_refresh_token_keeps_the_old_one`.
  - `test_concurrent_refreshes_are_serialized`: zwei Threads, Fake-Client zählt gleichzeitige Aufrufe → max. 1; zweiter Aufruf sendet den vom ersten gespeicherten Token.
  - `test_reload_picks_up_a_new_pairing`.
- [ ] **Step 2:** `PYTEST tests/tray/test_config.py tests/tray/test_session.py -v` → FAIL.
- [ ] **Step 3:** Implementieren; Docstring von `refresh_access` („server does not rotate“) umschreiben.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat(tray): rotierte Refresh-Tokens atomar speichern (#847)`.

---

### Task 7: Tray — Warten auf Kopplung statt Aufgeben, Start ohne Kopplung

**Files:**
- Modify: `backend/baluhost_tray/loop.py`, `backend/baluhost_tray/state.py` (Tooltip), `backend/baluhost_tray/main.py`, `backend/baluhost_tray/tray.py` (`on_paired`)
- Modify: `deploy/install/templates/baluhost-tray.service` (`ConditionPathExists` + Kommentar weg)
- Test: `backend/tests/tray/test_loop.py`, `test_state.py`, `test_main_wiring.py`, `test_unit_template.py`

**Interfaces:**
- Consumes: `Session.reload()` (Task 6).
- Produces:
  - `loop.PAIRING_POLL_SECONDS = 10.0`
  - `async def wait_for_pairing(ctx: LoopContext) -> None` — `set_paired(False)`, publish, dann alle `PAIRING_POLL_SECONDS` `await asyncio.to_thread(ctx.session.reload)` bis True; dann `set_paired(True)`, `ctx.on_paired()` (Fehler darin geloggt, nicht fatal).
  - `LoopContext.on_paired: Callable[[], None] = lambda: None`
  - `run_loop`: ohne Tokens beim Start → `wait_for_pairing`; nach `PairingLost` → `_give_up_pairing` dann `wait_for_pairing`, `attempt = 0`, `refreshed_at = None`, weiter (kein `return` mehr).
  - `main.run()`: ohne Tokens wird die Qt-App trotzdem gestartet.

- [ ] **Step 1: Failing tests:**
  - `test_pairing_lost_waits_and_resumes`: Fake-Session wirft `PairingLost`, `reload()` liefert erst False, dann True → Schleife verbindet erneut, `on_paired` einmal aufgerufen.
  - `test_start_without_tokens_waits_for_pairing`.
  - `test_tooltip_when_unpaired` → exakter Text aus Global Constraints.
  - `test_main_starts_tray_without_tokens` (ersetzt den alten EXIT_DONE-Test).
  - `test_unit_template_has_no_condition_on_token_file`.
- [ ] **Step 2:** FAIL. **Step 3:** implementieren; Kommentare zu `EXIT_DONE` in `main.py` umschreiben. In `tray.py` `on_paired` = Kontofakten neu holen und `restart_visible`/Always-Awake-Sichtbarkeit neu senden.
- [ ] **Step 4:** `PYTEST tests/tray -v` → PASS.
- [ ] **Step 5:** Commit `fix(tray): nach Kopplungsverlust warten statt aufgeben, Start ohne Kopplung (#847)`.

---

### Task 8: Tray — „BaluHost öffnen“ mit Auto-Login

**Files:**
- Create: `backend/baluhost_tray/handoff.py`
- Modify: `backend/baluhost_tray/restart.py` (`AccountFacts.pin_enabled`, `fetch_account_facts` holt `GET /api/auth/pin`)
- Modify: `backend/baluhost_tray/tray.py` (Menü + Linksklick)
- Test: `backend/tests/tray/test_handoff.py`, `test_restart.py`, `test_tray_wiring.py`

**Interfaces:**
- Consumes: `Session.current_refresh_token()` (Task 6), Backend-Verträge aus Task 4.
- Produces:
  - `HANDOFF_PATH = "/api/auth/handoff"`
  - `@dataclass(frozen=True) class HandoffResult: url: str; notice: str | None = None`
  - `def open_url_for(session, web_url: str, pin_enabled: bool, ask_pin: Callable[[bool], str | None]) -> HandoffResult` — `ask_pin(retry)` liefert PIN oder `None` (Abbruch). Erfolg → `f"{web_url.rstrip('/')}/login#handoff={code}"`. `pin_invalid` → einmal `ask_pin(True)` und neu; erneut falsch → Klartext-URL + `notice="PIN stimmt nicht — bitte normal anmelden."`. `pin_locked` → Klartext-URL + `notice="PIN gesperrt — bitte mit Passwort anmelden."`. `pin_required` bei `pin_enabled=False` → einmal `ask_pin(False)`. Abbruch/jede andere Antwort/Exception → `HandoffResult(url=web_url)`. Loggt nie den Code.
  - `AccountFacts.pin_enabled: bool = False`.

- [ ] **Step 1: Failing tests** (Fake-Client mit vorgegebenen Antworten):
  - `test_success_opens_login_with_fragment`; `test_no_pin_dialog_without_account_pin`; `test_cancelled_pin_opens_plain_url`; `test_wrong_pin_asks_once_more`; `test_wrong_pin_twice_opens_plain_with_notice`; `test_locked_pin_opens_plain_with_notice`; `test_server_error_opens_plain_url`; `test_network_error_opens_plain_url`; `test_code_never_logged` (`caplog` enthält den Code nicht).
  - `test_account_facts_include_pin_state`.
  - `test_tray_wiring`: „BaluHost öffnen“ und Linksklick laufen über denselben Handler; zweiter Klick während laufendem Ablauf wird ignoriert.
- [ ] **Step 2:** FAIL. **Step 3:** implementieren; in `tray.py` Ablauf in einem `threading.Thread`, PIN-Dialog über die bestehende Prompt-Brücke (`QInputDialog`, `EchoMode.Password`, Titel `"BaluHost öffnen"`, Text `"PIN für BaluHost:"` bzw. `"PIN stimmt nicht. Noch einmal:"`), URL über ein neues Signal `open_url(str)` im GUI-Thread öffnen, `notice` über `notifier.show_summary("BaluHost", notice)`.
- [ ] **Step 4:** `PYTEST tests/tray -v` → PASS.
- [ ] **Step 5:** Commit `feat(tray): BaluHost öffnen meldet automatisch an (#847)`.

---

### Task 9: Tray — Always Awake im Menü

**Files:**
- Create: `backend/baluhost_tray/awake.py`
- Modify: `backend/baluhost_tray/tray.py`
- Test: `backend/tests/tray/test_awake.py`, `test_tray_wiring.py`

**Interfaces:**
- Produces:
  - `SLEEP_CONFIG_PATH = "/api/sleep/config"`
  - `class AwakeChoice(Enum): OFF, HOUR, EIGHT_HOURS, PERMANENT`
  - `@dataclass(frozen=True) class AwakeState: enabled: bool; until: datetime | None`
  - `class AwakeError(Exception)`
  - `def payload_for(choice: AwakeChoice, now_utc: datetime) -> dict` — Werte exakt aus der Spec (OFF: `{"always_awake_enabled": False, "always_awake_until": None}`, HOUR/EIGHT_HOURS: `True` + `(now_utc + 1h|8h).isoformat()`, PERMANENT: `True` + `None`).
  - `def parse_state(data: dict) -> AwakeState` (Felder `always_awake_enabled`, `always_awake_until`).
  - `def checked_choice(state: AwakeState) -> AwakeChoice | None` — nicht aktiv → OFF; aktiv ohne Frist → PERMANENT; aktiv mit Frist → `None`.
  - `def submenu_title(state: AwakeState) -> str` — mit Frist `"Always Awake — bis HH:MM"` (lokale Zeit), sonst `"Always Awake"`.
  - `def fetch_state(client, on_auth_expired) -> AwakeState` und `def apply(client, choice, now_utc, on_auth_expired) -> AwakeState` — je einmal Refresh bei 401, sonst Nicht-200/Netzfehler → `AwakeError`.

- [ ] **Step 1: Failing tests:** Payloads aller vier Wahlen (feste `now_utc`); `checked_choice` für alle drei Zustände; Titel mit/ohne Frist; `apply` nutzt die PUT-Antwort, nicht die Annahme (Backend kürzt Frist → Rückgabe trägt gekürzte Frist); 401 → ein Refresh, dann Erfolg; 403/500/Netzfehler → `AwakeError`. `test_tray_wiring`: Untermenü nur bei `is_admin is True` sichtbar, bei `None` ausgeblendet.
- [ ] **Step 2:** FAIL. **Step 3:** implementieren; in `tray.py` `QMenu("Always Awake")` mit `QActionGroup(exclusive)`, `aboutToShow` → Thread `fetch_state` → Signal `awake_state(object)` setzt Haken + Titel; Klick → Thread `apply` → Signal; `AwakeError` → `notifier.show_summary("BaluHost", "Always Awake konnte nicht gesetzt werden")`, Haken auf letzten bekannten Stand.
- [ ] **Step 4:** `PYTEST tests/tray -v` → PASS.
- [ ] **Step 5:** Commit `feat(tray): Always Awake direkt im Menü umschalten (#847)`.

---

### Task 10: Dokumentation und Regeln

**Files:**
- Modify: `docs/features/desktop-tray.de.md` (+ `.en.md` falls vorhanden), `.claude/rules/security-agent.md`, `.claude/rules/architecture.md`, `backend/app/api/CLAUDE.md`, `backend/app/models/CLAUDE.md`, `client/src/api/CLAUDE.md` falls Module gelistet

- [ ] **Step 1:** Tray-Doku: Auto-Login (inkl. PIN), Always Awake, kein Neustart nach `--pair`, einmalige Neuinstallation der User-Unit, Gerät entfernen.
- [ ] **Step 2:** `security-agent.md`: neuer Abschnitt unter *Role Model* zum Handoff (Gerätetoken als Nachweis, LAN-Gate nur beim Ausstellen und warum, PIN, bewusst ohne Passwort/2FA mit Vertrauensmodell, Besitzerbestätigung 2026-11-25) und zur Rotation („lazy revoke“, Reuse → Gerät widerrufen); Desktop-Geräte widerrufbar.
- [ ] **Step 3:** `architecture.md` API-Liste: `/api/auth/handoff`, `/api/auth/handoff/redeem`, `DELETE /api/devices/desktop/{id}`.
- [ ] **Step 4:** Volle Suite: `PYTEST` und `cd client && npm run build && npx vitest run` → grün.
- [ ] **Step 5:** Commit `docs(tray): Auto-Login, Always Awake und Gerätewiderruf dokumentieren (#847)`.

## Nach dem Merge (Betrieb, kein Code)

- Deploy läuft die Migrationen.
- `systemctl --user restart baluhost-tray`; User-Unit einmal neu installieren (Condition entfernen).
- Auf BaluNode einmalig `baluhost-tray --pair` (Kopplung seit 23.11. verloren).
