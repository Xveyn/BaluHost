# Plugin „Feste Adresse im Heimnetz“ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein mitgeliefertes, standardmäßig deaktiviertes Plugin `local_tls` hält einen DNS-Namen auf der LAN-IP der Box und holt/erneuert dafür per lego (DNS-01) ein Let's-Encrypt-Zertifikat, das nginx ohne neue Root-Rechte übernimmt.

**Architecture:** Bundled Plugin unter `backend/app/plugins/installed/local_tls/`. Einstellungen über `get_config_schema()` (Core-Config-Routen, generisches Formular); Status und verschlüsselter Anbieter-Token in der Core-Tabelle `local_tls_state`. Je ein Modul kapselt den Kontakt zu lego, zur Netzwerkkonfiguration und zu nginx; DNS-Anbieter sind Adapter in `providers/`. Zwei primary-only Hintergrundaufgaben, eigene Admin-Routen, UI-Karte im Einstellungs-Tab „Integrationen“.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, httpx 0.27, cryptography 48, lego ≥ 4.35 (externes Programm), React 18 + TS, vitest, i18next.

**Spec:** `docs/superpowers/specs/2026-11-25-local-tls-plugin-design.md`

## Global Constraints

- Umgebung: Ein Hook blockiert Shell-Befehle mit `grep`/`rg` → Read-Tool, `awk`, `find`. Diese Maschine ist auch Produktion: kein `sudo`, `/opt/baluhost` und `/var/lib/baluhost` nicht anfassen (Tests nutzen `tmp_path`). Backend-Tests sandboxed aus `backend/`: `bwrap --dev-bind / / --tmpfs /dev/shm --unshare-pid --proc /proc --die-with-parent --chdir "$PWD" -- .venv/bin/python -m pytest <pfade> -v --no-cov`. **Vor jedem Commit zusätzlich `.venv/bin/ruff check .` in `backend/`.**
- Plugin-Name exakt `local_tls`; Routen unter `/api/plugins/local_tls/`; `config` ist reservierter Core-Pfad — keine eigene Route dort.
- Plugin standardmäßig aus; `required_permissions`: `["network:outbound", "system:execute", "db:write", "task:background", "notification:send"]`.
- **Keine neue sudoers-Regel.** nginx-Reload nur über `sudo -n /usr/bin/systemctl reload nginx` (bestehender Eintrag). Kein certbot/lego als root.
- Datenverzeichnis fest `/var/lib/baluhost/plugins/local_tls/` (in Tests über Parameter/Monkeypatch ersetzbar); Verzeichnisse 0700, Schlüssel 0600. nginx-Pfade: `<data>/live/fullchain.pem`, `<data>/live/privkey.pem`; `live` ist Symlink auf `<data>/releases/<UTC-Zeitstempel>/`; die **letzten 3** Releases bleiben.
- lego: Mindestversion **4.35**; `--path <data>/lego`; Erstausstellung `run`, Erneuerung `renew --days 30`; Zugangsdaten nur per `env`; Listen-Args, Timeout 300 s.
- Zeitplan: Adress-Check alle **300 s**, tägliche Bestätigung (86400 s seit letztem Setzen); Zertifikats-Check alle **86400 s**. Datei-Lock `<data>/.lock` gegen parallele lego-Läufe.
- Benachrichtigungen (an Admins): `cert_expiring` (ab **21 Tagen** vor Ablauf, Cooldown 86400 s), `renew_failed`, `dns_update_failed`, `address_changed` (info).
- Token: Fernet über `app.services.vpn.encryption.VPNEncryption.encrypt_key/decrypt_key`; Spalte `provider_secret`; ohne `settings.vpn_encryption_key` → Route lehnt ab (400), nie Klartext speichern. Token nie in Antworten, Logs, Audit, Exceptions.
- Adapter-Regeln: nur HTTPS zum eigenen Anbieter-Host, Timeout ≤ 15 s, kein Shell-Aufruf, keine Dateizugriffe, Domain und IP vor jedem Aufruf validiert, IP privat und IPv4 (v1).
- Neue Routen: `get_current_admin`, `@user_limiter.limit(get_limit("local_tls"))` mit `"local_tls": "30/minute"` in `RATE_LIMITS` + `rate_limit_config.py`, Pydantic-Bodies, Audit-Aktionen exakt `local_tls_credentials_changed`, `local_tls_renew_triggered`, `local_tls_dns_update_triggered`.
- Bundled-Plugin-Datei ohne `from __future__ import annotations` in Modulen mit Routen (siehe Kommentar in `plugins/installed/bluetooth/__init__.py`).
- Texte im Frontend `de` + `en`, eigener Namespace `localTls`.
- Commit-Nachrichten: Conventional Commits auf Deutsch mit `(#…)`-loser Scope-Angabe `tls`, Abschluss `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Box hat mehrere Interfaces (wg0, docker0) bzw. die Default-Route fehlt kurz** → nimmt die IP der Default-Route bzw. das Override-Interface; ohne Route kein Update und kein Löschen des Eintrags, nur Fehlerstatus. Test in Task 3 (`test_no_default_route_is_an_error_not_an_update`).
2. **nginx liefert nach dem Reload weiter das alte Zertifikat** (Site noch nicht umgestellt) → Rückrollen, `renew_failed` mit Grund „nginx liefert anderes Zertifikat“, Status zeigt Umstellungshinweis. Test in Task 4 (`test_rolls_back_when_served_cert_differs`).
3. **lego fehlt oder ist zu alt** → klarer Status, keine Exception im Hintergrund, keine Benachrichtigungsflut (Cooldown). Test in Task 3 (`test_missing_lego_is_reported_not_raised`) und Task 5.
4. **Token fehlt, Plugin aber aktiv** → Hintergrundaufgaben tun nichts außer Status „nicht konfiguriert“, kein `renew_failed` alle 5 Minuten. Test in Task 5 (`test_unconfigured_plugin_stays_quiet`).
5. **Zwei Auslöser gleichzeitig** („Jetzt erneuern“ während des täglichen Laufs) → zweiter wartet nicht ewig, sondern meldet „läuft bereits“ (409). Test in Task 6 (`test_renew_while_running_is_409`).

---

### Task 1: Datentabelle `local_tls_state` und Zugriffsschicht

**Files:**
- Create: `backend/app/models/local_tls_state.py` (+ Export in `backend/app/models/__init__.py`)
- Create: `backend/alembic/versions/local_tls_state_2026_11_25.py` (`down_revision = "d4b7e2c9a610"`, vorher mit `.venv/bin/alembic heads` prüfen)
- Create: `backend/app/plugins/installed/local_tls/__init__.py` (vorerst leer bis Task 5 — nur Paket-Marker mit Docstring), `backend/app/plugins/installed/local_tls/state.py`
- Test: `backend/tests/plugins/local_tls/test_state.py` (+ `__init__.py`)

**Interfaces:**
- Produces:
  - Modell `LocalTlsState` (`__tablename__ = "local_tls_state"`): `id` (int PK), `provider_secret` (Text, nullable), `last_ip` (String(45), nullable), `last_ip_set_at` (DateTime tz, nullable), `last_renew_at` (DateTime tz, nullable), `last_renew_ok` (Boolean, nullable), `last_renew_reason` (String(500), nullable), `cert_fingerprint` (String(64), nullable), `cert_not_after` (DateTime tz, nullable), `updated_at`.
  - In `state.py`: `get_state(db) -> LocalTlsState` (legt die eine Zeile an, falls fehlend), `set_token(db, token: str) -> None` (verschlüsselt; `ValueError("encryption key missing")` ohne Schlüssel), `clear_token(db) -> None`, `get_token(db) -> str | None`, `has_token(db) -> bool`, `record_ip(db, ip: str, now: datetime) -> None`, `record_renew(db, ok: bool, reason: str | None, fingerprint: str | None, not_after: datetime | None, now: datetime) -> None`.

- [ ] **Step 1: Failing tests:** `test_get_state_creates_single_row` (zweimal aufrufen → genau 1 Zeile); `test_token_is_stored_encrypted` (Spaltenwert ≠ Token, `get_token` liefert Token; `settings.vpn_encryption_key` per Monkeypatch auf einen gültigen Fernet-Schlüssel); `test_set_token_without_key_refuses` (Schlüssel leer → `ValueError`, Spalte bleibt `None`); `test_clear_token`; `test_record_ip_and_renew_roundtrip`; `test_provider_secret_matches_redact_pattern` (`REDACT_PATTERN` aus `app.services.audit.admin_db` trifft `"provider_secret"`).
- [ ] **Step 2:** `PYTEST tests/plugins/local_tls/test_state.py` → FAIL (Import).
- [ ] **Step 3:** Modell, Migration (create table / drop table), `state.py` implementieren.
- [ ] **Step 4:** Tests + `PYTEST tests/migrations` → PASS; `ruff check .` sauber.
- [ ] **Step 5:** Commit `feat(tls): Datentabelle local_tls_state mit verschlüsseltem Anbieter-Token`.

---

### Task 2: Adapter-Schnittstelle und DuckDNS

**Files:**
- Create: `backend/app/plugins/installed/local_tls/providers/__init__.py` (Registry), `providers/base.py`, `providers/duckdns.py`
- Test: `backend/tests/plugins/local_tls/test_providers.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class CredentialField: name: str; label_key: str; secret: bool; pattern: str`
  - `class ProviderError(Exception)` (Meldung nie mit Token oder Token-URL)
  - `class DnsProvider(Protocol)`: `id: str`, `display_name: str`, `credential_fields: tuple[CredentialField, ...]`, `lego_provider: str`, `def validate_domain(self, domain: str) -> bool`, `def lego_env(self, credentials: dict[str, str]) -> dict[str, str]`, `def update_address(self, domain: str, ip: str, credentials: dict[str, str], *, client: httpx.Client | None = None) -> None`
  - Registry: `PROVIDERS: dict[str, DnsProvider]`, `get_provider(provider_id: str) -> DnsProvider` (`KeyError` bei unbekannt).
  - `DuckDnsProvider`: `id="duckdns"`, `lego_provider="duckdns"`, ein Feld `token` (secret, Pattern UUID `^[0-9a-f-]{36}$`), `validate_domain` nur `^[a-z0-9-]{1,63}\.duckdns\.org$`, `lego_env` → `{"DUCKDNS_TOKEN": token}`, `update_address` → `GET https://www.duckdns.org/update` mit Params `domains=<sub>`, `token`, `ip`, Timeout 15 s; Antworttext `OK` = Erfolg, sonst `ProviderError("duckdns rejected the update")`.

- [ ] **Step 1: Failing tests** (mit `httpx.MockTransport`): `test_duckdns_update_sends_subdomain_and_ip` (Request-URL-Host `www.duckdns.org`, Param `domains == "baluhost"`, `ip == "192.168.178.53"`); `test_duckdns_ko_raises_without_token_in_message`; `test_duckdns_validate_domain` (gültig `baluhost.duckdns.org`; ungültig `evil.com`, `a.b.duckdns.org`, `BALUHOST.duckdns.org.`); `test_update_rejects_public_or_v6_ip` (`8.8.8.8`, `fe80::1` → `ProviderError`, kein Request); `test_every_registered_provider_is_complete` (alle Registry-Einträge haben alle Attribute, `id` passt `^[a-z0-9_]+$`, `credential_fields` nicht leer).
- [ ] **Step 2:** FAIL. **Step 3:** implementieren; Adapter-Regeln aus den Global Constraints als Modul-Docstring in `providers/base.py`.
- [ ] **Step 4:** PASS, ruff sauber. **Step 5:** Commit `feat(tls): Adapter-Schnittstelle für DNS-Anbieter mit DuckDNS`.

---

### Task 3: LAN-IP, lego-Aufruf, Lock

**Files:**
- Create: `backend/app/plugins/installed/local_tls/address.py`, `lego.py`, `paths.py`
- Test: `backend/tests/plugins/local_tls/test_address.py`, `test_lego.py`

**Interfaces:**
- Produces:
  - `paths.DATA_DIR = Path("/var/lib/baluhost/plugins/local_tls")`; `paths.ensure_dirs(data_dir: Path) -> None` (0700); `paths.lock(data_dir: Path) -> ContextManager[None]` — nicht blockierender `fcntl.flock` auf `<data>/.lock`, wirft `AlreadyRunning`.
  - `class AddressError(Exception)`; `address.current_lan_ip(interface: str | None = None, *, run=subprocess.run) -> str` — ohne Interface `["ip", "-j", "route", "get", "1.1.1.1"]` → `prefsrc`; mit Interface `["ip", "-j", "-4", "addr", "show", "dev", <iface>]` → erste `inet`-Adresse; Interface-Name gegen `^[a-zA-Z0-9_.-]{1,15}$` prüfen; Ergebnis muss privat sein (`is_private_or_local_ip`), sonst `AddressError`; Timeout 5 s.
  - `class LegoError(Exception)`, `class LegoMissing(LegoError)`, `class LegoTooOld(LegoError)`; `MIN_VERSION = (4, 35, 0)`
  - `lego.version(*, run=subprocess.run) -> tuple[int, int, int]` (`["lego", "--version"]`; `FileNotFoundError` → `LegoMissing`)
  - `lego.obtain_or_renew(domain: str, provider_lego_name: str, env: dict[str, str], data_dir: Path, *, email: str | None, staging: bool, run=subprocess.run) -> bool` — True, wenn ein neues Zertifikat entstanden ist (Vergleich mtime/Fingerabdruck der Zertifikatsdatei vor/nach). Args: `["lego", "--accept-tos", "--path", str(data_dir/"lego"), "--dns", provider, "--domains", domain]` + `["--email", email]` falls gesetzt + `["--server", "https://acme-staging-v02.api.letsencrypt.org/directory"]` bei Staging + `["run"]` wenn noch kein Zertifikat, sonst `["renew", "--days", "30"]`. `env` = `os.environ` ohne fremde Secrets + Adapter-env. Timeout 300 s. Nicht-null Exit → `LegoError(<letzte stderr-Zeile ohne env-Werte>)`.
  - `lego.cert_paths(domain: str, data_dir: Path) -> tuple[Path, Path]` (`<data>/lego/certificates/<domain>.crt|.key`).

- [ ] **Step 1: Failing tests** (Fake-`run`): `test_ip_from_default_route` (JSON `[{"prefsrc":"192.168.178.53","dev":"enp12s0"}]`); `test_ip_from_interface_override`; `test_public_ip_is_rejected`; `test_no_default_route_is_an_error_not_an_update` (Exit 2 / leeres JSON → `AddressError`); `test_interface_name_is_validated` (`"eth0; rm"` → `AddressError`, kein Aufruf); `test_missing_lego_is_reported_not_raised` → hier: `version()` wirft `LegoMissing` bei `FileNotFoundError`; `test_old_lego_detected` (`lego version 4.9.1` → `(4,9,1)` < `MIN_VERSION`); `test_first_run_uses_run_then_renew` (Args-Listen exakt, `DUCKDNS_TOKEN` nur in `env`, nicht in Args); `test_staging_and_email_flags`; `test_error_message_never_contains_token` (stderr enthält Token → Exception-Text nicht); `test_lock_is_exclusive` (zweiter `lock()` → `AlreadyRunning`).
- [ ] **Step 2:** FAIL. **Step 3:** implementieren (`subprocess.run` mit Liste, `capture_output=True`, `text=True`, kein `shell`).
- [ ] **Step 4:** PASS, ruff. **Step 5:** Commit `feat(tls): LAN-IP-Erkennung und lego-Aufruf ohne Root`.

---

### Task 4: Zertifikat prüfen, tauschen, nginx neu laden, verifizieren

**Files:**
- Create: `backend/app/plugins/installed/local_tls/deploy_cert.py`
- Test: `backend/tests/plugins/local_tls/test_deploy_cert.py` (Zertifikate mit `cryptography` im Test erzeugen)

**Interfaces:**
- Consumes: `paths.DATA_DIR` (Task 3).
- Produces:
  - `class CertInvalid(Exception)`, `class DeployFailed(Exception)` (mit `.reason: str`)
  - `@dataclass(frozen=True) class CertInfo: fingerprint: str  # sha256 hex; not_after: datetime; sans: tuple[str, ...]`
  - `inspect(cert_pem: bytes, key_pem: bytes, domain: str, now: datetime) -> CertInfo` — wirft `CertInvalid`, wenn PEM kaputt, Schlüssel nicht passt, `domain` nicht in SAN, abgelaufen.
  - `deploy(cert_path: Path, key_path: Path, domain: str, data_dir: Path, now: datetime, *, reload=reload_nginx, served_fingerprint=served_fingerprint) -> CertInfo` — prüft, legt `releases/<now:%Y%m%dT%H%M%SZ>/fullchain.pem|privkey.pem` an (0600), biegt `live` atomar um (temporärer Symlink + `os.replace`), ruft `reload()`, vergleicht `served_fingerprint(domain)` mit dem neuen; bei Abweichung oder Reload-Fehler: `live` zurück auf die vorige Version, erneut `reload()`, `DeployFailed(reason)`; behält die letzten 3 Releases.
  - `reload_nginx(*, run=subprocess.run) -> None` — `["sudo", "-n", "/usr/bin/systemctl", "reload", "nginx"]`, Timeout 30 s; Fehler → `DeployFailed("nginx reload not permitted or failed")`.
  - `served_fingerprint(domain: str, host: str = "127.0.0.1", port: int = 443) -> str | None` — TLS-Handshake mit SNI=`domain`, ohne Zertifikatsprüfung, sha256 des DER-Zertifikats; Netzfehler → `None`.

- [ ] **Step 1: Failing tests:** `test_inspect_accepts_matching_pair`; `test_inspect_rejects_mismatched_key`; `test_inspect_rejects_wrong_domain`; `test_inspect_rejects_expired`; `test_deploy_switches_live_atomically` (Fakes für `reload`/`served_fingerprint`; `live` zeigt auf neuen Release, Dateimodi 0600); `test_rolls_back_when_served_cert_differs` (served ≠ neu → `live` wieder auf alten Release, `reload` zweimal, `DeployFailed`, Grund enthält „served“); `test_rolls_back_when_reload_fails`; `test_first_deploy_without_previous_release_fails_cleanly` (kein Rückziel → `live` entfernt bzw. unverändert nicht vorhanden, `DeployFailed`); `test_keeps_last_three_releases`; `test_reload_uses_existing_sudo_rule_only` (Args exakt `["sudo","-n","/usr/bin/systemctl","reload","nginx"]`).
- [ ] **Step 2:** FAIL. **Step 3:** implementieren. **Step 4:** PASS, ruff.
- [ ] **Step 5:** Commit `feat(tls): Zertifikat prüfen, atomar tauschen und nginx-Auslieferung verifizieren`.

---

### Task 5: Plugin-Klasse, Konfiguration, Abläufe, Benachrichtigungen

**Files:**
- Modify: `backend/app/plugins/installed/local_tls/__init__.py` (PluginBase-Klasse)
- Create: `backend/app/plugins/installed/local_tls/config.py` (Pydantic `LocalTlsConfig`), `service.py` (Abläufe), `CLAUDE.md`
- Modify: `backend/app/plugins/CLAUDE.md` (Baum + Liste der bundled Plugins), `backend/app/models/CLAUDE.md` (Tabelle)
- Test: `backend/tests/plugins/local_tls/test_service.py`, `test_plugin.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `LocalTlsConfig`: `domain: str = ""`, `provider: str = "duckdns"` (muss in `PROVIDERS`), `interface: str | None = None`, `email: str | None = None`, `staging: bool = False`. Validator: `domain` leer oder `get_provider(provider).validate_domain(domain)`.
  - `@dataclass class Status: configured: bool; lego: str  # "ok"|"missing"|"too_old"; lego_version: str | None; current_ip: str | None; last_ip: str | None; last_ip_set_at: datetime | None; cert_not_after: datetime | None; cert_fingerprint: str | None; served_matches: bool | None; last_renew_at: datetime | None; last_renew_ok: bool | None; last_renew_reason: str | None; running: bool`
  - `service.run_address_check(db, config: LocalTlsConfig, now: datetime, *, force: bool = False) -> None` — nicht konfiguriert → nichts; IP bestimmen; Update, wenn IP ≠ `last_ip` oder `force` oder letztes Setzen ≥ 86400 s her; Erfolg → `record_ip`, bei geänderter IP Event `address_changed`; `ProviderError`/`AddressError` → Event `dns_update_failed` (Cooldown 3600 s).
  - `service.run_cert_check(db, config, now, *, force: bool = False) -> None` — nicht konfiguriert → nichts; lego fehlt/zu alt → `record_renew(ok=False, reason=…)` + `renew_failed` (Cooldown 86400 s); unter `paths.lock`: `obtain_or_renew`; neues Zertifikat oder `force` → `deploy`; Ergebnis per `record_renew`; Fehler → `renew_failed`; danach unabhängig: `cert_not_after - now ≤ 21 Tage` → `cert_expiring`.
  - `service.get_status(db, config, now) -> Status`.
  - Events (`get_notification_events`): `cert_expiring` (warning, Cooldown 86400), `renew_failed` (critical, Cooldown 86400), `dns_update_failed` (warning, Cooldown 3600), `address_changed` (info, Cooldown 0); Texte deutsch, mit Platzhaltern `{domain}`, `{days}`, `{reason}`, `{ip}`; `action_url="/settings?tab=integrations"`.
  - Plugin-Klasse `LocalTlsPlugin`: `metadata.name="local_tls"`, `display_name="Feste Adresse im Heimnetz"`, Permissions aus Global Constraints; `get_config_schema() -> LocalTlsConfig`; `get_background_tasks()` → `address_check` (300 s, `run_on_startup=True`), `cert_check` (86400 s, `run_on_startup=True`), beide in `asyncio.to_thread` mit eigener DB-Session, jede Exception geloggt (ohne Token), nie propagiert; `get_router()` → Router aus Task 6 (Import lazy).

- [ ] **Step 1: Failing tests** (alle Fremdkontakte per Monkeypatch: `current_lan_ip`, Provider, `lego.*`, `deploy`, `emit`-Funktion als Fake, die Aufrufe sammelt): `test_unconfigured_plugin_stays_quiet` (kein Token oder keine Domain → keine Aufrufe, keine Events); `test_address_unchanged_no_update_within_day`; `test_address_changed_updates_and_notifies`; `test_daily_reconfirm`; `test_dns_failure_notifies`; `test_cert_renewed_is_deployed_and_recorded`; `test_no_new_cert_no_deploy`; `test_deploy_failure_records_reason_and_notifies`; `test_lego_missing_records_status_once_per_day` (Cooldown greift über `emit_plugin_event`); `test_expiry_warning_at_21_days` (20 Tage → Event, 22 Tage → keins); `test_config_rejects_foreign_domain_for_duckdns`; `test_plugin_metadata_and_tasks` (Name, Intervalle 300/86400, Permissions-Liste exakt, Plugin ist nicht standardmäßig aktiv — prüfen, wie andere bundled Plugins das ausdrücken, und analog testen).
- [ ] **Step 2:** FAIL. **Step 3:** implementieren; `CLAUDE.md` des Plugins mit Layout, Invarianten (keine neue sudoers-Regel, Token-Regeln, Adapter-Regeln, nginx-Pfad) anlegen; `plugins/CLAUDE.md`/`models/CLAUDE.md` ergänzen.
- [ ] **Step 4:** `PYTEST tests/plugins/local_tls tests/plugins` → PASS, ruff.
- [ ] **Step 5:** Commit `feat(tls): Plugin local_tls mit Adress- und Zertifikats-Check`.

---

### Task 6: Admin-Routen

**Files:**
- Create: `backend/app/plugins/installed/local_tls/routes.py`, `models.py` (Pydantic-API-Modelle)
- Modify: `backend/app/core/rate_limiter.py`, `backend/app/services/rate_limit_config.py` (`local_tls`)
- Test: `backend/tests/plugins/local_tls/test_routes.py`

**Interfaces:**
- Consumes: `service.*`, `state.*`, `paths.AlreadyRunning`.
- Produces (alle `get_current_admin`, Rate-Limit `local_tls`):
  - `GET /api/plugins/local_tls/status` → `StatusResponse` (Felder wie `Status`, plus `token_set: bool`, `nginx_hint: str | None` — das Konfig-Snippet aus der Spec, nur wenn `served_matches is False`)
  - `PUT /api/plugins/local_tls/credentials` Body `CredentialsRequest { token: str }` (Länge 1–200, Pattern des Provider-Felds) → 204; ohne Schlüssel 400 `{"error": "encryption_key_missing"}`; Audit `local_tls_credentials_changed` (`details={"action": "set"}`).
  - `DELETE /api/plugins/local_tls/credentials` → 204; Audit mit `{"action": "cleared"}`.
  - `POST /api/plugins/local_tls/renew` → 202 nach synchronem Lauf in `asyncio.to_thread` (`force=True`), Antwort = Status; läuft bereits → 409 `{"error": "already_running"}`; Audit `local_tls_renew_triggered`.
  - `POST /api/plugins/local_tls/update-dns` → 200 Status; Audit `local_tls_dns_update_triggered`.

- [ ] **Step 1: Failing tests:** `test_routes_require_admin` (User → 403 für alle fünf); `test_status_never_contains_token`; `test_put_credentials_encrypts_and_audits` (Audit-Zeile ohne Token-Wert); `test_put_credentials_without_key_is_400`; `test_put_credentials_validates_pattern` (422); `test_delete_credentials`; `test_renew_while_running_is_409` (Lock von außen halten); `test_update_dns_triggers_forced_check`; `test_rate_limit_key_registered` (beide Registrierungsorte).
- [ ] **Step 2:** FAIL. **Step 3:** implementieren (Muster `plugins/installed/bluetooth/__init__.py` für Router/Limiter/Audit; Plugin-Routen werden beim Start einmal gemountet — in Tests wie bei bestehenden Plugin-Routen-Tests einbinden, z. B. `tests/plugins/` nachsehen).
- [ ] **Step 4:** PASS, ruff. **Step 5:** Commit `feat(tls): Admin-Routen für Status, Token und manuelle Läufe`.

---

### Task 7: Web-UI-Karte

**Files:**
- Create: `client/src/api/localTls.ts`, `client/src/components/settings/LocalTlsCard.tsx`, `client/src/i18n/locales/{de,en}/localTls.json` (+ Namespace-Registrierung laut `client/src/i18n/CLAUDE.md`)
- Modify: `client/src/pages/SettingsPage.tsx` (Tab `integrations`: Karte nur für Admins und nur, wenn das Plugin aktiv ist — Aktiv-Status wie andere plugin-abhängige UI-Teile ermitteln)
- Test: `client/src/__tests__/components/settings/LocalTlsCard.test.tsx`

**Interfaces:**
- Consumes: Routen aus Task 6.
- Produces: `getLocalTlsStatus()`, `setLocalTlsToken(token)`, `clearLocalTlsToken()`, `renewLocalTls()`, `updateLocalTlsDns()` in `api/localTls.ts`.
- Karte zeigt: Domain, aktuelle LAN-IP / zuletzt gesetzte IP + Zeitpunkt, Zertifikat gültig bis (rot < 7 Tage, gelb < 21), letzte Erneuerung + Ergebnis + Grund, lego-Status mit Installationsbefehl `sudo apt install -t trixie-backports lego` bei `missing`/`too_old`, Token „gesetzt/nicht gesetzt“ + Passwortfeld zum Setzen + Entfernen-Knopf, Knöpfe „Jetzt erneuern“ (409 → Hinweis „läuft bereits“) und „DNS jetzt aktualisieren“, bei `nginx_hint` ein kopierbarer Block mit Hinweistext. Einstellungen selbst: Link „Einstellungen“ auf die Plugin-Seite (generisches Formular).

- [ ] **Step 1: Failing tests:** rendert Status (Ablaufdatum, Farben an den Grenzen 6/7/20/21 Tage); Token-Feld leert sich nach dem Speichern und zeigt den Wert nie an; 409 bei „Jetzt erneuern“ zeigt den Hinweis; lego fehlt → Befehl sichtbar; `nginx_hint` → Block sichtbar.
- [ ] **Step 2:** `cd client && npx vitest run src/__tests__/components/settings/LocalTlsCard.test.tsx` → FAIL.
- [ ] **Step 3:** implementieren. **Step 4:** Test + i18n-Tests + `npm run build` grün.
- [ ] **Step 5:** Commit `feat(tls): Statuskarte im Einstellungs-Tab Integrationen`.

---

### Task 8: Installation, Doku, Sicherheitsregeln

**Files:**
- Modify: `deploy/install/modules/14-optional-features.sh` (optionaler Schritt „lego aus trixie-backports“, nur auf Nachfrage/Flag wie die anderen optionalen Features; Backports-Quelle nur ergänzen, wenn nicht vorhanden)
- Modify: `deploy/ssl/setup-letsencrypt.sh` (Kopfkommentar: Altlast, HTTP-01; für lokale Namen das Plugin `local_tls` verwenden)
- Create: `docs/features/local-tls.de.md`, `docs/features/local-tls.en.md`
- Modify: `.claude/rules/security-agent.md` (Eintrag), `.claude/rules/architecture.md` (API-Liste), `CLAUDE.md` Quick Reference (eine Zeile)
- Test: `backend/tests/test_optional_features_lego.py` (Muster der bestehenden Deploy-Skript-Tests, z. B. `tests/test_deploy_*.py`: Skripttext enthält den Backports-Befehl und ist `bash -n`-sauber)

- [ ] **Step 1:** Failing Test für das Installer-Modul (Skript enthält `-t trixie-backports lego`, `bash -n` ok).
- [ ] **Step 2:** FAIL. **Step 3:** Modul ändern; Doku schreiben: Zweck, Voraussetzungen (Domain bei DuckDNS, Token, lego ≥ 4.35), Einrichtung, nginx-Umstellung (Snippet für beide TLS-Blöcke inkl. :8443 und `server_name`), Ablösung auf BaluNode (lego installieren → Plugin einrichten → „Jetzt erneuern“ → nginx umstellen → alte certbot-Erneuerung stilllegen und pipx-certbot entfernen), DNS-Rebind-Hinweis (Fritz!Box ohne Pi-hole), Fehlerbilder. `security-agent.md`: keine neue sudoers-Regel, nur bestehendes Reload-Recht; ehrliche Grenze mit Verweis auf #862; Token-Speicherung; Adapter-Regeln; Verweis auf #863.
- [ ] **Step 4:** Volle Verifikation: `cd backend && .venv/bin/ruff check .` und volle Suite sandboxed `-n 6 --no-cov`; `cd client && npx vitest run && npm run build`.
- [ ] **Step 5:** Commit `docs(tls): Einrichtung, Ablösung auf BaluNode und Sicherheitsregeln für local_tls`.

## Nach dem Merge (Betrieb, kein Code)

Siehe Doku-Abschnitt „Ablösung auf BaluNode“; das alte Zertifikat gilt bis 2027-02-23, es ist also Zeit.
