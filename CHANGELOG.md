# Changelog

All notable changes to BaluHost will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.27.1] - 2026-04-03

### Fixed
- Firebase: accept string device_id without int conversion
- Samba: allow mixed-case usernames in validation regex
- Cloud: improve OAuth redirect handling and error responses
- Tests: update stale imports in logging tests after services reorganization

---

## [1.27.0] - 2026-04-03

### Added
- **Notification Routing** — Admin-configurable notification categories for non-admin users
  - Admins can assign notification categories (RAID, SMART, Backup, Scheduler, System, Security, Sync, VPN) per user
  - New `user_notification_routing` database table with per-category boolean flags
  - Admin endpoints on `/api/users/{id}/notification-routing` for viewing and updating
  - `GET /api/notifications/my-routing` read-only endpoint for users to see assigned categories
  - Routed users receive both push (Firebase) and in-app (WebSocket) notifications
  - User's own NotificationPreferences (quiet hours, channel opt-out) respected after routing
  - Per-user notification copies created for routed users so they appear in notification list
  - Frontend toggle UI in user edit modal with category icons and descriptions
  - Read-only badge display in user's notification settings showing assigned categories
  - Audit logging for routing changes
- **Dependencies** — Audit logger added as FastAPI dependency for cleaner injection

### Fixed
- Sleep: use atomic rtcwake suspend to fix scheduled wake-up failure
- Security: add defense-in-depth username validation for Samba
- Security: harden config defaults and add production validators

### Changed
- Refactor: add `ensure_db()` context manager to deduplicate session boilerplate
- Refactor: remove legacy `sys.modules` backward-compat shims

---

## [1.26.0] - 2026-04-03

### Added
- **Sleep-Aware Sync** — Automatic syncs respect admin sleep schedules
  - `GET /api/sync/preflight` endpoint for clients to check sync availability
  - Server-side guard rejects auto/scheduled syncs during sleep with 503 + Retry-After
  - `X-Sync-Trigger` header distinguishes auto vs manual sync requests
  - Auto-wake middleware skips wake for auto/scheduled syncs during sleep
  - Sync schedule validation prevents creating schedules in planned sleep windows
  - Frontend sleep conflict warnings on schedule form and schedule list
  - Client integration guide for BaluDesk (C++/Electron) and BaluApp (Kotlin/Android)
- **Pi-hole** — Clickable column sorting on all Pi-hole tables

### Fixed
- Auth: log notification emit errors instead of silently swallowing them
- Sync: make `auto_vpn` migration safe when `sync_schedules` table is missing
- Sync: recreate sync tables erroneously dropped by refresh token migration

---

## [1.25.0] - 2026-04-02

### Added
- **Power Permissions** — Granular per-user power action delegation for mobile app users
  - Admins can grant individual permissions: Soft Sleep, Wake, Suspend, Wake-on-LAN
  - New `user_power_permissions` database table with foreign keys to users
  - Implication logic: enabling Soft Sleep auto-enables Wake, enabling Suspend auto-enables WoL (and reverse)
  - `GET /api/system/sleep/my-permissions` endpoint for mobile app permission fetching
  - Admin endpoints on `/api/users/{id}/power-permissions` for viewing and updating
  - Power action endpoints (`/soft`, `/wake`, `/suspend`, `/wol`) now accept delegated users, not just admins
  - Audit logging for permission changes and delegated power actions
  - Frontend toggle UI in user edit modal (Settings > Users) with implied-permission indicators

---

## [1.24.0] - 2026-04-01

### Added
- **Setup Wizard** — First-time configuration wizard for fresh BaluHost installations
  - Admin account creation, user setup, file access configuration
  - Welcome screen with cat logo, progress indicator, security-guarded endpoints
  - Frontend integration with gated routing (blocks app until setup completes)
- **Integrations Tab** — New tab in Settings for managing cloud provider credentials
  - Per-provider cards (Google Drive, OneDrive, iCloud) with configuration status and capability badges (Import/Export)
  - Inline OAuth credential forms for Google Drive and OneDrive
  - Admin overview table showing all users' configured integrations
  - iCloud displays "Import only" hint (login remains in Cloud Import wizard)
- **VPN Page Unification** — Unified VPN management page with profile CRUD
  - VPN profile creation/editing with Modal component
  - Fritz!Box upload UI replaced by profile-based workflow

### Changed
- CloudConnectWizard simplified — inline OAuth configuration removed, redirects to Settings > Integrations for unconfigured providers
- Update service reads version from `pyproject.toml` instead of git tags
- User manual overhauled for v1.23.0

### Fixed
- SQLite race condition on dev startup — stagger worker starts
- Plaintext admin password removed from deployment notes
- Modal rendering via portal to escape ancestor stacking contexts
- VPN profile form and list restyled to dark theme
- Unused toast import removed from VPNProfileForm

---

## [1.23.0] - 2026-03-31

### Added
- **VPN Profile Export** — Export VPN profiles as QR code or file download
  - QR code generation for configs under 1800 bytes (scanner-compatible threshold)
  - Automatic fallback to download mode for large OpenVPN profiles with embedded certs/keys
  - Export dialog with copy-to-clipboard, direct download, and config preview
  - Full audit logging for export operations
- **Release Workflow** — Label-based release automation via PR (`release:patch/minor/major`)

### Changed
- VPN Profiles section added to VPN Management page for admin workflow

### Fixed
- **SQLite Lock Contention** — Added `busy_timeout=30s`, WAL mode, and `commit_with_retry` with exponential backoff for background workers (PiHole collector, scheduler, WebDAV)
- **Mobile Device last_sync** — Device tracking middleware now updates `last_sync` on file upload/download/sync operations; sync folder updates propagate to parent device
- **File Permissions** — Use shareable users endpoint for permission/ownership dialogs

---

## [1.22.0] - 2026-03-30

### Added
- **Storage Permissions & Notifications** — Shared `baluhost` Linux group infrastructure with setgid for safe multi-process file ownership on RAID mounts
  - New `STORAGE_PERMISSION_ERROR` notification event with FCM push to admin mobile devices
  - 5-minute cooldown per path prevents notification spam
  - `_emit_permission_error` helper catches OS PermissionError in all file operations (upload, delete, rename, move, create folder)
  - New `storage_group` config setting (default: `baluhost`)
- **Docs-as-Manual** — Dynamic manual tabs served from backend docs API
  - `/api/docs/index` and `/api/docs/article` endpoints with DocsService
  - `useDocsIndex` and `useDocsArticle` hooks, DocsGroupTab component
  - Multilingual docs with `.de`/`.en` suffix convention and `manual-index.json`
- **HTTPS/SSL** — Nginx HTTPS template and self-signed certificate setup with client trust guide
- **User Home Storage Indicator** — Storage usage display per user in FileManager

### Changed
- Samba `force group` now uses `storage_group` setting instead of service user name
- Samba system users created with `--group baluhost` for storage group membership
- systemd service template uses `Group=baluhost`
- Samba setup script accepts `STORAGE_GROUP` variable

### Fixed
- **PermissionError on RAID mounts** — All file operations now catch OS-level PermissionError and return 403 instead of 500
- **Startup PermissionError** — Handle permission errors on RAID mountpoints during startup gracefully
- **Dependabot** — Patched 5 security vulnerabilities
- **Frontend** — Removed unused title destructuring in ArticleView

### Documentation
- Added CLAUDE.md files for all backend and frontend sub-modules
- Storage permissions design spec and implementation plan

---

## [1.21.0] - 2026-03-29

### Added
- **Cloud Export** — Share files to cloud providers (Google Drive, Dropbox, OneDrive) with OAuth2 integration, upload/share-link adapters, scope checks, and retry support
  - Cloud Shares tab in SharesPage with stats and job list
  - Unified ShareFileModal with internal + cloud export tabs
  - Full i18n support (en + de)
  - Integration tests for export flow
- **User Manual Page** — Three-tab layout (Setup, Wiki, API Reference) with markdown rendering, replacing the old ApiCenterPage
  - ArticleCard, ArticleView, VersionBadge components
  - useManualContent hook with initial cloud-import article
- **Storage Permissions** — Permission constants and helpers applied across upload, folder creation, and home directory operations
- **Sortable Tables** — Reusable SortableHeader component and useSortableTable hook with 3-stage sort cycle (asc → desc → default)
  - Sortable columns in FileListView (Name, Size, Modified, Owner)
  - Sortable columns in SharesPage (all 3 tabs)
  - Sortable columns in PiholeLocalDns (Domain, IP)
  - Sortable columns in UserTable (all columns)
  - Upgraded AdminDataTable to 3-stage sort cycle
- **SSL Setup** — Self-signed SSL setup script for LAN deployments

### Changed
- Removed old ApiCenterPage (replaced by UserManualPage)
- Removed unused Docker and monitoring stack files
- Added `@tailwindcss/typography` and `react-markdown` dependencies

### Fixed
- **FileManager** — Owner name display for non-admin users now resolved correctly
- **TypeScript** — Relaxed useSortableTable generic constraint, fixing 157 TS errors
- **Pi-hole** — Handle naive datetimes from SQLite in ad discovery background poll
- **Cloud Export** — Type safety fixes and added delete_file to adapter base class
- **Manual** — TypeScript error in lucide icon resolution
- **Storage** — Permissions applied consistently across upload, folder creation, and home dirs

### Performance
- Stabilized getValueForSort reference to avoid unnecessary re-sorts in sortable tables

---

## [1.20.5] - 2026-03-29

### Added
- **Sync Folder Update** — PUT endpoint for updating sync folder configuration (remote path, sync type, auto-sync, status)
- **File Checksum** — Expose file checksum in directory listing response for client-side change detection

### Fixed
- **Smart Device** — Use `anyio.from_thread.run` for async calls from sync worker threads, preventing event-loop errors

---

## [1.20.4] - 2026-03-28

### Fixed
- **Mobile Device Naming** — User-chosen device name from QR generation is now persisted and applied when the device registers, instead of being replaced by the auto-detected app name
- **Energy Dashboard** — Fixed power_monitor reading using wrong key (`current_power` → `watts`), causing dashboards to always show 0W
- **File Upload Rate Limits** — Increased from 20 to 1000 requests/min to prevent throttling during bulk uploads
- **Fan Control UI** — Hide backend badge in production mode
- **Power Manager** — Handle race condition when power demands register before backend initialization

---

## [1.20.3] - 2026-03-27

### Added
- **Centralized Version Bumping** — `scripts/bump_version.py` syncs version across pyproject.toml, package.json, and CLAUDE.md from a single source of truth
  - Supports `patch`, `minor`, `major` keywords or explicit version numbers

### Fixed
- **VPN Endpoint Parsing** — Strip port and URI scheme from `public_endpoint` before building WireGuard config, preventing malformed endpoints like `http://example.com:51820:51820`

### Changed
- Release command now uses `bump_version.py` instead of manual multi-file edits

---

## [1.20.2] - 2026-03-26

### Added
- **Push Notification Wiring** — Event emitters now called by RAID, scheduler, and monitoring services
  - RAID: degraded/rebuilt notifications for both dev and production backends
  - Scheduler: failure notifications for periodic APScheduler job callbacks
  - Monitoring: CPU temperature alerts (≥80°C warning, ≥90°C critical) and disk space alerts (≤15% low, ≤5% critical)
  - New `emit_disk_space_critical_sync` convenience function
- **Login UX** — Password visibility toggle on login screen
- **Uptime Monitoring** — Sleep state tracking in uptime visualization

### Changed
- Added `backend/data/` to gitignore

---

## [1.20.1] - 2026-03-25

### Added
- **VPN Mode Clarity** — Clearly distinguish Router-VPN (FritzBox) from NAS-VPN (WireGuard) in the UI
  - Backend: `vpn_fallback` boolean in mobile token response — `true` when auto-mode silently fell back to NAS-VPN
  - MobileDevicesPage: VPN type buttons relabeled to "Router-VPN (FritzBox)" / "NAS-VPN (WireGuard)", amber WoL warnings when NAS-VPN is selected or is the only available option, fallback notice in QR dialog
  - VpnManagement: New NAS-VPN info card with server initialization status, active client count, and permanent WoL warning
  - i18n: German and English translations for VPN management section

---

## [1.20.0] - 2026-03-25

### Added
- **Ad Discovery** — New Pi-hole feature that identifies unblocked ad-serving domains via heuristic pattern-matching and community blocklist cross-referencing
  - Heuristic scorer with substring and regex pattern matching (ReDoS-protected via ThreadPoolExecutor timeout)
  - Community matcher: downloads, caches (gzip), and cross-references domains against 5 default community blocklists (OISD, Hagezi, Steven Black, EasyList, AdGuard)
  - SSRF protection on all blocklist download URLs (HTTPS-only, private/loopback IP rejection)
  - Custom blocklist builder: create lists, add/remove domains, deploy as Pi-hole adlists with per-list token auth
  - Analyzer orchestrator combining heuristic + community scoring with configurable weights
  - Background task (DnsQueryCollector pattern) for periodic automatic analysis
  - 29 API endpoints under `/api/pihole/ad-discovery/` with rate limiting and audit logging
  - Full frontend UI: Ad Discovery tab with suspects table, patterns panel, reference lists panel, custom lists panel
  - Dev mode support: hardcoded ad domains for testing without network access, 5-minute background interval
  - 6 new database tables with Alembic migration and default seed data (27 patterns, 5 reference lists)
- **Plugin Capability Contracts** — Runtime validation of poll data against capability contracts at startup
- **Plugin SDK Design Spec** — Design documentation for hooks, registry, and CLI

### Fixed
- Ad Discovery bulk-action: use correct `backend` property on PiholeService (was `_backend`)

---

## [1.19.1] - 2026-03-24

### Fixed
- **Sleep schedule stuck state** — When `suspend_system()` failed, state stayed on TRUE_SUSPEND permanently, blocking schedule re-triggers, manual wake, and auto-wake middleware. Now reverts to SOFT_SLEEP on failure.
- **Sleep resume path** — After successful suspend resume, state transition was rejected by `_exit_soft_sleep()` guard. Fixed by setting state to SOFT_SLEEP before calling exit.

---

## [1.19.0] - 2026-03-22

### Added
- **Fritz!Box Wake-on-LAN** — TR-064 SOAP integration for remote WoL via Fritz!Box router
  - FritzBoxConfig model, migration, API routes with auth and audit logging
  - Fritz!Box config UI and API client in frontend
  - WolRequest extended with `method` field for Fritz!Box delegation
  - Sleep panel button integrates Fritz!Box WoL
- **Remote Server WoL** — Wake-on-LAN support for remote server profiles
  - `wol_mac_address` column on ServerProfile with schemas and migration
  - SSH-fail-to-WoL fallback in server start endpoint
  - WoL badge and fallback result display in server profile UI
  - MAC address field in server profile form
- **WoL Improvements** — MAC address auto-detection and validation
  - `get_own_mac()` via `/proc/net/route` (Linux) with dev-mode fallback
  - Detected MAC shown as suggestion in SleepConfigPanel
  - Shared MAC address validator with tests
  - MAC validation wired into WolRequest and SleepConfigUpdate
- **Multi-worker sleep init** — Sleep service supports multi-worker initialization

### Changed
- Refactored file service: extracted virtual directory listings from route to service layer
- Refactored fan control: extracted schedule and profile logic into separate modules
- Models use `TYPE_CHECKING` for relationship type imports (cleaner circular import handling)
- Added `Mapped` type annotations across models (server_profile, vpn_profile, vcl, etc.)
- Fixed Pydantic field definitions to use `Field(default=)` instead of positional defaults

### Fixed
- VPN profile config validation: pass enum directly instead of `.value`
- Energy sample parser now supports plugin PowerReading format
- Correct RAID import path and worker return type
- Smart service import path in jobs.py
- Sync schedule calculation handles nullable `time_of_day`
- SleepConfigUpdate field ordering after validator insertion
- Type annotations and SQLAlchemy usage fixes across power, update, versioning, and schema modules
- pytest-cov pin updated from `<5.0.0` to `>=7.0.0,<8.0.0`

### Dependencies
- FastAPI 0.115.6 → 0.135.1 (+ Starlette 1.0.0)
- plugp100 5.1.5 → 5.1.7
- coverage 7.13.4 → 7.13.5
- pytest-cov 7.0.0 → 7.1.0

---

## [1.18.0] - 2026-03-22

### Added
- **Plugin Badge System** — purple "Plugin" badge on plugin-contributed pages, nav items, and sections (like AdminBadge but for plugins)
- **Plugin Settings UI** — dynamic settings form in plugin detail sidebar, rendered from plugin's JSON Schema config
- **Tapo Plugin Config** — `panel_devices` setting to select which devices appear in dashboard panel, third-party compatibility hint
- **Power Graph Device Tabs** — switch between "Total" (aggregated) and individual device views in System Monitor Power tab
- **Aggregated Energy Endpoint** — `GET /api/energy/cumulative/total` sums energy data across all power-monitoring devices
- **Conditional PowerTab** — Power tab in System Monitor only visible when a plugin with `power_monitor` capability is active
- **Dashboard Panel Navigation** — clicking the Tapo power panel navigates to System Monitor Power tab
- **plugp100 Monkey-Patch** — workaround for `InvalidAuthentication` super() bug in plugp100 v5.x

### Changed
- Plugin documentation rewritten for hobby developers (friendlier tone, clearer explanations, EN + DE)
- Smart device auth errors now show "Authentication failed" instead of cryptic "Library error: super() argument 1 must be a type, not str"

### Fixed
- PowerTab field name alignment with SmartDevice state format (`watts`/`current`/`energy_today_kwh`)
- PostgreSQL RETURNING clause compatibility in migration
- Multi-worker plugin registration (lazy-sync across Uvicorn workers, catch duplicate Pluggy registration)
- Capabilities JSON string deserialization from some DB drivers
- plugp100 `InvalidAuthentication` auth error handling across poll, turn_on, turn_off, get_power

---

## [1.17.0] - 2026-03-19

### Added

- **Smart Device Plugin Framework** — generic IoT device management with capabilities system (Switch, PowerMonitor, Dimmer, ColorLight, etc.)
- **Tapo Smart Plug Plugin** — TP-Link Tapo integration rebuilt as plugin with Switch + PowerMonitor capabilities
- **Dashboard Plugin Panels** — plugins can provide dashboard widgets with gauge/stat/status/chart renderers via WebSocket + REST
- **Plugin i18n** — translation support for plugin UI (en/de)
- **SHM-to-WebSocket bridge** — shared memory based real-time device state updates
- **Smart Device test suite** — 159 tests for the new plugin framework

### Changed

- **Tapo → SmartDevice migration** — all Tapo-specific models, schemas, routes replaced by generic SmartDevice API (`/api/smart-devices/`)
- **Energy service** — migrated from PowerSample/TapoDevice to SmartDeviceSample with JSON data storage
- **Frontend PowerTab/EnergyMonitor** — rewritten to use SmartDevice API
- **Alembic migrations** — data migration from legacy tables + drop of `tapo_devices`/`power_samples` tables

### Fixed

- Broken import paths after service refactoring into subpackages
- Type safety issues found by pyright across backend
- Notification service null safety checks
- File service type annotations, closure capture, SQLAlchemy expressions
- Monitoring collector import and type signature issues
- Frontend icon lookup and chart gradient uniqueness
- Mock session factory and dashboard panel translations in tests

### Documentation

- Plugin system README and architecture docs
- Smart device plugin research and design specs
- Dashboard Plugin Panel System design spec

---

## [1.16.4] - 2026-03-17

### Added

- **Mobile QR dialog** — auto-close on successful device registration

### Fixed

- **Import paths** — correct all broken module references after service reorganization into subpackages (power/, hardware/, sync/, versioning/, scheduler/)
- **Runtime crashes** — fix wrong attribute access in RAID status and audit log routes
- **Sync schedule management** — fix weekday mapping, add edit/delete support, resolve device name display
- **Type safety** — add null checks, input validation, SQLAlchemy `Mapped[]` annotations, and proper type casts across 46 backend files
- **Token validation** — reject tokens missing `sub` claim in JWT and WebSocket auth
- **Sleep/service endpoints** — make request bodies optional to prevent 422 errors on empty requests
- **Relative time formatter** — display future dates correctly in device list
- Deprecated patterns and name collisions removed

### Documentation

- Security audit report (2026-03-16)
- Static analysis report (ruff + mypy)

---

## [1.16.3] - 2026-03-16

### Added

- **Plugin permission enforcement** — runtime middleware validates plugin permissions before execution

### Fixed

- **Security: inactive user rejection** — JWT authentication now rejects users with inactive accounts
- **Security: metrics endpoint auth** — Prometheus `/metrics` endpoint requires admin authentication
- **Security: token lifecycle** — enforce 15min access token TTL, type-safe refresh tokens, revoke on logout
- SMART device type override cached to reduce noisy retries
- Frontend notification socket consolidated into single effect to prevent duplicate connections
- Version now read from installed package metadata at runtime

### Changed

- TTL cache added for aggregated storage info, telemetry poll interval reduced

### Removed

- Obsolete plan files and PGP key

---

## [1.16.2] - 2026-03-16

### Fixed

- Monitoring uptime bars showing no data for short time ranges
- Update service using actual version in changelog instead of literal "latest"

### Tests

- Test coverage for pure-logic and DB-CRUD services (Batch 1)
- Test coverage for async services and dev-mode stubs (Batch 2)
- Test coverage for plugin manager and cloud scheduler (Batch 3)

---

## [1.16.1] - 2026-03-15

### Fixed

- Update service reads version from pyproject.toml instead of installed package metadata
- Readable permissions on update status files for deploy script
- Storage tab capacity values and SSD cache filtering corrected
- v1.16.0 changelog corrected to only include changes since v1.15.6

---

## [1.16.0] - 2026-03-15

### Added

- **Per-device storage API** — `GET /api/system/storage/devices` endpoint for individual disk breakdown
- **Storage tab redesign** — Multi-segment donut chart with clickable panels per device
- **Uptime tab redesign** — Status-page-style visualization with improved layout
- **Client unit tests** — Tests for API modules, hooks, and lib utilities (Vitest)

### Changed

- **Backend refactoring** — Extracted FritzBox VPN, VCL admin/tracking, RAID routes, optical drive, sleep/fan backends into dedicated modules
- **Client refactoring** — Extracted UpdatePage tabs, TwoFactorCard, StorageTab, mobile/admin-db/files APIs into standalone modules

### Fixed

- ESLint errors in PluginPage, UploadProgressBar, and catch blocks
- Pre-existing TypeScript errors and test mock data alignment
- SSD cache filter to only show arrays with actual cache devices
- Distinct colors for storage donut chart segments
- Live fallback for uptime history endpoint

### Documentation

- Audit report updated with resolution status review (64→78/100)
- Project stats and outdated documentation refreshed
- Dynamic GitHub release badge in README

---

## [1.15.6] - 2026-03-15

### Added

- **Uptime tracking** — New UptimeSample model with server + system uptime, historical DB persistence, 30-day retention
- **Uptime API endpoints** — `GET /api/monitoring/uptime/current` and `/history` with live fallback computation
- **Uptime tab** — System Monitor > System > Uptime with live counters, restart detection, and area chart
- **Dashboard dual uptime** — Server uptime as main value, system uptime as subtitle, clickable to uptime tab
- **BaluPi setup** — Admin route, setup component, and API client for Pi device management
- **Pi mode guards** — Disable notifications and plugins in Pi mode to avoid unnecessary requests

### Changed

- **SystemInfo schema** — Added `system_uptime` field to `/api/system/info` response

---

## [1.15.5] - 2026-03-15

### Refactoring, Performance & Code Quality

Großflächiges Refactoring: DB-Calls aus Routes in Service-Layer extrahiert,
SQLAlchemy 2.0 Mapped-Style Migration und Frontend Error-Handling vereinheitlicht.

### Changed

- **Routes → Services** — DB-Calls aus 10+ Route-Modulen (user, device, mobile, samba, monitoring, sync, shares, cache, pihole, firebase) in Service-Layer extrahiert
- **SQLAlchemy models** — Mobile und rate_limit_config auf SQLAlchemy 2.0 Mapped-Style migriert
- **Frontend error handling** — Shared `getApiErrorMessage` in 18 Components eingesetzt
- **Logging** — print-Statements durch Logger ersetzt, Validator dedupliziert, Cache gebunden

### Fixed

- **Import paths** — Import-Pfade und kleinere Issues über mehrere Services korrigiert
- **Notifications** — FCM High Priority und Sound für zuverlässige Push-Delivery
- **Update version label** — Version-Label auf stable vs dev build vereinfacht

### Performance

- **Sync heartbeat** — DB-Writes in Thread-Pool ausgelagert

### Tests

- **Firebase push delivery** — 30 neue Tests für Push-Notification-Delivery

---

## [1.15.4] - 2026-03-14

### Settings Redesign, API Center & Notification Cleanup

Redesign der Settings-Seite, dynamische API-Dokumentation und Entfernung
des nie genutzten Email-Notification-Features.

### Added

- **Settings storage tab** — Neuer Storage-Tab mit System Storage Ring, VCL Quota und SSD Cache Sektionen
- **API Center docs** — Endpoint-Dokumentation wird dynamisch aus dem OpenAPI-Schema generiert
- **FCM push notifications** — Event-driven und Admin-Notifications via Firebase Cloud Messaging
- **Power sample retention** — Power Samples werden jetzt vom Retention Management erfasst

### Changed

- **Settings profile tab** — Vereinfacht, Avatar-Upload und Email-Sektion entfernt
- **Audit logger paths** — Import-Pfade nach Modul-Restrukturierung korrigiert

### Fixed

- **API Center rate limits** — Rate Limits Management mit dynamischem Endpoint-Matching wiederhergestellt

### Removed

- **Email notifications** — Komplettes SMTP-Email-Feature entfernt (war nie in Produktion aktiv)

---

## [1.15.3] - 2026-03-14

### Update System Fix & Cancel Support

Fix für hängendes Update-Progress und neuer Cancel-Mechanismus für laufende Updates.

### Added

- **Update cancel** — Laufende Updates können jetzt über die UI abgebrochen werden (dev: asyncio cancel, prod: systemd stop)
- **Update progress i18n** — Fehlende Übersetzungen für die Update-Progress-Anzeige (DE+EN)
- **Unified test runner** — Neues Test-Runner-Script für kombinierte Backend/Frontend-Tests

### Fixed

- **Update progress stuck at 5%** — Dev-Mode-Updates crashten durch geschlossene DB-Session in _notify_progress()
- **Prod update staleness** — Status-File wird jetzt in die DB synchronisiert, gestoppte systemd-Units werden erkannt
- **Update cancel timezone** — UpdateHistory.cancel() nutzt jetzt konsistent UTC statt lokale Zeitzone

### Changed

- **CI workflows** — Redundante Workflows entfernt

---

## [1.15.2] - 2026-03-13

### Firebase Configuration, Test Notifications & Stability

Admin-UI für Firebase-Credential-Verwaltung, Test-Notifications aus dem Admin-Panel,
verbesserte Notification-Zuverlässigkeit und Backend-Refactoring.

### Added

- **Firebase config UI** — Neuer Firebase-Tab unter System Control > Network zum Hochladen, Anzeigen und Löschen von Firebase-Credentials mit Hot-Reload
- **Firebase test notifications** — Test-Benachrichtigungen aus der Admin-UI senden, inkl. manuellem FCM Token
- **Development branch updates** — Update-Support für den Development-Branch

### Changed

- **Backend modularisierung** — Lifespan und Service Registry in eigene Module extrahiert
- **Pillow dependency** — Upper-Version-Constraint entfernt

### Fixed

- **FCM push delivery** — Push-Benachrichtigungen an mobile Geräte korrigiert
- **Test notifications** — Verbesserte Behandlung für Geräte ohne Push-Token
- **Update service** — repo_path Traversal in ProdUpdateBackend korrigiert
- **Notification retry** — Retry-Logik und Scheduler Grace Period erweitert
- **Device removal push** — Push-Benachrichtigung bei Geräte-Entfernung + Import-Pfad Fix
- **Idle detection** — Mobile Browser Timer-Freeze im Background behandelt

---

## [1.15.0] - 2026-03-11

### File Activity, Sync Auto-VPN & VPN Config Improvements

Neues File-Activity-Tracking-System mit Recent-Files-API, Auto-VPN-Option für
Sync-Schedules und verbesserte VPN-Konfigurationsgenerierung mit konfigurierbarem
DDNS-Endpoint.

### Added

- **File activity tracking** — Neues System zur Erfassung von Dateiaktivitäten mit Recent Files API
- **Sync auto-VPN** — `auto_vpn` Feld für Sync-Schedules mit UI-Toggle zum Aktivieren/Deaktivieren
- **Dev build flag** — `is_dev_build` Flag in Version-Info für bessere Build-Erkennung

### Fixed

- **VPN config generation** — Konfigurierbarer DDNS-Endpoint und Server Public Key in generierten Configs
- **VPN server key** — Server Public Key wird von laufendem wg0 Interface gelesen statt neu generiert
- **Files routes** — Pylance Static-Analysis-Warnungen in Files-Routes behoben
- **Worker imports** — sys.path korrigiert für App-Module-Imports in Workern
- **CI** — Development-Branch wird nach PR-Merge zu main synchronisiert

### Tests

- **Sync tests** — Sync-Scheduler-Service und Route-Tests hinzugefügt

---

## [1.14.0] - 2026-03-10

### Notification Settings & Stability Fixes

Notification-Einstellungen in die Settings-Seite integriert, verbesserte
Rate-Limiter-Konfiguration und mehrere Bugfixes für Notifications und Pi-hole.

### Added

- **Notification Settings tab** — Benachrichtigungseinstellungen als neuen Tab in die Settings-Seite verschoben

### Fixed

- **Rate-Limiter** — File/Sync-Limits erhöht und neue `mobile_sync`-Kategorie hinzugefügt
- **Notifications** — Naive datetime in `time_ago`-Berechnung korrekt behandelt
- **Notifications** — System-Benachrichtigungen (user_id=NULL) für Admin-Benutzer eingeschlossen
- **Pi-hole** — 127.0.0.1 statt localhost verwenden um ConnectError nach Deploy zu vermeiden
- **i18n** — Fehlende Notification-Center-Übersetzungsschlüssel ergänzt
- **Frontend** — Unbenutzte eta-Variable im Layout.tsx Restart-Handler entfernt

---

## [1.13.9] - 2026-03-10

### Backend Logs, Power Menu & API Documentation

Neues Backend-Log-Monitoring mit Echtzeit-Streaming, überarbeitetes Power-Menü
in der Header-Leiste und umfassende API-Dokumentation im API Center.

### Added

- **Backend Logs monitoring** — Neuer Backend Logs Tab im System Monitor mit REST + SSE Endpoints und Log-Buffer-Service mit Subscriber-Support
- **PowerMenu dropdown** — Header-Buttons für Shutdown/Logout durch kompaktes Dropdown-Menü ersetzt
- **Restart API endpoint** — Neuer System-Restart-Endpoint
- **API Center documentation** — ~115 fehlende API-Endpoints dokumentiert

---

## [1.13.8] - 2026-03-10

### Energy Dashboard Fix & Version History

Kritischer Bugfix für das Energy Dashboard auf PostgreSQL (Production),
plus neue Features für Versionsverfolgung und Mobile Sync.

### Added

- **Version history tracking** — Erfasst jede gestartete Version+Commit in der DB mit Startzähler
- **Version history UI** — Neue Sektion im Verlauf-Tab zeigt alle jemals gelaufenen Versionen
- **Delete sync folder endpoint** — Mobile Sync-Ordner können jetzt gelöscht werden
- **Dev commit messages** — Dev-Version-Sektion zeigt Commit-Messages und Dev Build Badge

### Fixed

- **Energy dashboard 500 on PostgreSQL** — `get_hourly_samples()` nutzte SQLite-spezifisches `func.strftime()`, jetzt cross-database kompatibel mit `date_trunc()` für PostgreSQL
- **Dashboard error handling** — `get_current_power()` ValueError wird jetzt im Dashboard-Handler abgefangen
- **CI auto-tag** — Globale Git-Config für auto-tag im geklonten Repo

---

## [1.13.6] - 2026-03-09

### Mobile Upload Queue & Update-UI

Upload-Queue für Mobile-Geräte und Verbesserungen an der Update-Seite
(Dev-Branch-Indikator, Versions-Tab jetzt auch in Production sichtbar).
Speicher-Anzeige nutzt jetzt verfügbaren statt freien Speicher.

### Added

- **Upload queue endpoint** — Neuer API-Endpoint und Schemas für Mobile-Upload-Queue
- **Dev branch indicator** — Update-Seite zeigt aktiven Branch im Dev-Modus
- **Versions tab in production** — Versions-Tab jetzt auch in Production sichtbar

### Fixed

- **Memory info** — Verfügbarer Speicher statt freiem Speicher für akkurate Anzeige
- **Version sync** — Korrekte Version in `__init__.py` und `package-lock.json`
- **CI auto-tag** — Git-Identität für auto-tag im Merge-Workflow

### Changed

- **pytest-cov** — Coverage-Reporting zu Test-Dependencies hinzugefügt

---

## [1.13.5] - 2026-03-08

### System Variables & VPN Improvements

Admin-UI zum Bearbeiten von .env-Konfigurationsdateien direkt aus der
Web-Oberfläche. VPN-Typ-Auswahl (Full Tunnel / Split Tunnel) bei der
Mobilgeräte-Registrierung und mehrere VPN-Bugfixes.

### Added

- **System Variables page** — Admin-UI für .env-Bearbeitung mit Kategorie-Gruppierung und Sensitive-Value-Masking
- **VPN type selection** — Full/Split Tunnel Auswahl bei Mobile-Registrierung
- **VPN config type endpoints** — Backend-Unterstützung für vpn_type Parameter

### Fixed

- **VPN FORWARD rule** — Fehlende iptables FORWARD-Regel für VPN-Return-Traffic
- **VPN encryption** — Sichere Encryption-Wrapper und Endpoint-URL-Bereinigung
- **QR code loading** — Verbesserte Resilienz beim Laden von VPN-QR-Codes

### Documentation

- VPN Server Troubleshooting Guide

---

## [1.13.4] - 2026-03-08

### Scheduler Dashboard & Mobile API

Worker Health Status im Scheduler Dashboard zeigt jetzt den Zustand aller
Worker-Prozesse an. Stale Executions werden korrekt als CANCELLED markiert,
und ein neuer Mobile Power Summary Endpoint erweitert die Mobile-API.

### Added

- **Worker health status** — Scheduler Dashboard zeigt Worker-Prozess-Status
- **Mobile power summary** — Neuer API-Endpoint für mobile Energieübersicht

### Fixed

- **Stale execution recovery** — CANCELLED statt FAILED für abgebrochene Executions
- **WebSocket StrictMode** — Verzögerter Connect verhindert ECONNRESET
- **Frontend API URLs** — Korrekte URLs in allen API-Clients
- **Scheduler heartbeat** — Timezone-naive Heartbeat-Behandlung

### Changed

- **CI release workflow** — Liest Version aus pyproject.toml statt PR-Titel

---

## [1.13.3] - 2026-03-07

### Dev-Mode Stabilität & Architektur

Umfangreiche Bugfixes für den Windows Dev-Mode: QR-Codes werden jetzt korrekt
als SVG gerendert, WebSocket-Notifications funktionieren über den Vite-Proxy,
und die Monitoring-Architektur nutzt einheitlich den monitoring_worker-Prozess.

### Added

- **API versioning headers** — Infrastructure for API version negotiation
- **Token display in QR dialog** — Reveal/copy registration token manually
- **DEV_FAST mode** — `DEV_FAST=1` disables hot-reload and uses 2 workers

### Changed

- **Unified monitoring architecture** — Dev and prod both use monitoring_worker process via SHM IPC
- **Windows SHM support** — Shared-memory IPC falls back to `%TEMP%/baluhost-shm` on Windows
- **Dynamic dev update versioning** — Mock versions derived from installed package version
- **Dev sampling intervals** — Reduced frequencies for better dev performance
- **Reorganized service imports** — Updated to match new service package structure

### Fixed

- **QR code SVG fallback** — Manual SVG generation when Pillow is unavailable
- **QR code MIME type** — Auto-detect PNG vs SVG from base64 prefix
- **WebSocket URL** — Use Vite proxy instead of hardcoded `127.0.0.1:3001`
- **Scheduler timezone** — Handle naive `started_at` timestamps in duration calculation
- **psutil sensors** — Handle missing temperature sensors on Windows
- **DNS query collector** — Cross-database compatibility fix
- **DateTime arithmetic** — SQLite compatibility for timezone-aware datetimes

### Dependencies

- **bcrypt** bumped to 4.x
- **cryptography** upper bound widened to <47.0.0

---

## [1.13.2] - 2026-03-04

### WireGuard Server Config & VPN-Erreichbarkeit

### Added

- **WireGuard server config generation** — `generate_server_config()` builds `wg0.conf` from DB state (server keys + active client peers)
- **Live config sync** — `apply_server_config()` writes config and runs `wg syncconf` for seamless reload without disconnecting clients
- **Auto-sync on client changes** — Server config automatically updates when clients are created, revoked, or deleted
- **LAN routing via VPN** — Client AllowedIPs now include LAN subnet (`192.168.178.0/24`) for webapp access over VPN
- **`POST /api/vpn/sync-server`** — Admin-only endpoint to manually trigger server config regeneration
- **WireGuard setup script** (`deploy/scripts/setup-wireguard.sh`) — One-time server setup: `/etc/wireguard/`, IP forwarding, sudoers, systemd service, optional Pi-hole DNS
- **Sudoers template** (`deploy/install/templates/baluhost-wireguard-sudoers`) — Scoped sudo rules for WireGuard management
- **VPN config settings** — `vpn_lan_network`, `vpn_lan_interface`, `vpn_include_lan`, `vpn_config_path`

### Fixed

- **Deploy scripts** — Fixed `PGPASSWORD` extraction and `.env.production` sourcing for Alembic migrations
- **CI workflow** — Added `workflow_dispatch` trigger, fixed `DEPLOY_PAT` for auto-merge

---

## [1.13.1] - 2026-03-03

### Deployment Professionalisierung

Native Systemd-Deployment mit CI/CD-Pipeline: automatisierter Deploy bei Push auf main,
Datenbank-Backups vor jedem Deploy, atomisches Rollback, und Nginx für statisches Frontend.

### Added

- **CI/CD pipeline** — GitHub Actions CI Check workflow (backend tests + frontend build)
- **Auto-deploy** — Production deploy workflow triggered on push to main via self-hosted runner
- **Auto-merge** — PRs to main automatically merge when CI checks pass
- **Deploy script** (`ci-deploy.sh`) — Atomic deploys with pre-deploy DB backup, Alembic migration, health checks, and automatic rollback
- **DB backup/restore scripts** — `db-backup-daily.sh` (14-day retention cron) and `db-restore.sh` for manual recovery
- **Migration script** (`migrate-to-opt.sh`) — One-time migration from `/home/sven/projects/BaluHost` to `/opt/baluhost`
- **Systemd monitoring template** — Templated `baluhost-monitoring.service` with placeholder system
- **Deploy sudoers template** — Passwordless systemctl for deploy user
- **Self-hosted runner** — Setup docs and health check script (`deploy/runner/`)
- **Emergency runbook** — Step-by-step rollback and DB restore procedures
- **Infrastructure docs** — Production architecture overview

### Changed

- **Backend service template** — Updated to 4 workers, added primary lock cleanup and PostgreSQL dependency
- **Systemd module** — Extended to include monitoring service
- **Nginx config** — Verified SPA fallback and API proxy for static frontend serving

### Fixed

- **CI test compatibility** — Patched SessionLocal at all import sites for CI environment
- **62 CI test failures** — Resolved missing .env, SQLite advisory lock compat, SessionLocal bypass
- **Move endpoint** — Corrected variable name and SQLite advisory lock compatibility
- **qrcode dependency** — Moved from dev to core dependencies
- **Deploy scripts** — Fixed npm build and manual uvicorn handling
- **Hardware commands** — Added sudo for mdadm, smartctl, fan PWM in deploy scripts

---

## [1.13.0] - 2026-03-02

### Security Audit Remediation & Pi-hole Enhancements

Comprehensive security hardening from audit remediation (20 fixes), new Pi-hole features
(analytics dashboard, stored query log, DNS query collector), and mobile responsiveness
improvements across the Pi-hole UI.

### Added

- **Pi-hole analytics dashboard** — DNS query statistics with period selector, summary cards, and timeline charts
- **DNS query collector** — Background service collecting Pi-hole queries into local database for historical analysis
- **Stored DNS query API** — Endpoints for searching and filtering collected DNS queries
- **DNS query database models** — New tables and Alembic migration for query storage
- **Registration restriction** — Configurable `registration_enabled` setting to disable public user registration
- **Nginx Pi-hole proxy** — Reverse proxy config for Pi-hole web UI at baluhole.local
- **Auto .local DNS registration** — Automatically register local DNS records in Pi-hole on startup
- **CI workflows** — Added pytest and Vitest to GitHub Actions CI pipeline

### Changed

- **VPN key encryption** — Server and preshared keys now encrypted at rest with Fernet (AES-128-CBC)
- **WebSocket auth** — Uses scoped short-lived tokens instead of long-lived access tokens
- **CSP headers** — Strict `script-src 'self'` in production, relaxed only in dev mode
- **CORS policy** — Restricted methods and headers to required set instead of wildcards
- **TOTP encryption** — Dedicated `TOTP_ENCRYPTION_KEY` separate from VPN key
- **Brute-force tracking** — Bounded with TTLCache instead of unbounded dict
- **Monitoring buffer** — Replaced `list.pop(0)` with `deque(maxlen)` for O(1) performance
- **Notification queries** — Optimized with COUNT and GROUP BY instead of fetching all rows
- **Directory listing** — Fixed N+1 query pattern with bulk metadata fetches
- **README** — Complete rewrite reflecting current project state

### Fixed

- **Pi-hole mobile responsiveness** — Scrollable tabs, wrapping forms, responsive grids across 9 components
- **Change password validation** — Now uses Pydantic schema with password strength enforcement
- **Refresh token validation** — Added Pydantic schema for token request body
- **Admin password in production** — Rejects default password on startup
- **Timing-safe auth** — Dummy hash comparison on failed user lookup prevents timing attacks
- **`datetime.utcnow()` deprecation** — Replaced with `datetime.now(timezone.utc)` across codebase
- **CI test failures** — Resolved 68 test failures across 11 test files
- **`list_files` blocking** — Converted to sync def to prevent event loop blocking
- **`debug=False` default** — Only enabled in dev mode, preventing debug leaks in production

### Removed

- **Obsolete artifacts** — Removed generated HTML reports, backup files, and stale data from git tracking

---

## [1.12.0] - 2026-03-01

### BaluPi Groundwork, Pi-hole DNS & Performance

Stable release laying the groundwork for BaluPi companion device support (handshake protocol,
snapshot export, Pi frontend build pipeline), adding Pi-hole DNS integration for VPN, and
several backend/frontend improvements.

### Added

- **BaluPi handshake groundwork** — HMAC-SHA256 signed notification service and snapshot export for future Pi integration
- **Pi build pipeline** — Separate frontend build target for Raspberry Pi with tree-shaken desktop-only pages
- **PiDashboard page** — View-only dashboard skeleton for Pi (NAS status, energy, storage, Pi health)
- **Pi-hole DNS integration** — Backend service + frontend page for managing Pi-hole from BaluHost
- **VPN DNS via Pi-hole** — Use Pi-hole as DNS server for VPN clients when active
- **VCL tracking mode** — Automatic/manual mode with per-file tracking rules
- **VCL ownership reconciliation** — Admin tool to scan and fix version ownership mismatches
- **Dedicated monitoring worker** — Offloads CPU/RAM/network sampling to separate process in production
- **GitHub Actions workflow** — Auto-deploy Pi frontend to BaluPi on release

### Changed

- **Chunked upload** — Increased chunk size to 32MB and concurrent writes to 16
- **Vendor chunk splitting** — Better browser caching via separate vendor bundles
- **Update channel** — Renamed "beta" to "unstable" for clarity

### Fixed

- **UpdatePage** — Show actual version stability instead of update channel name
- **Plugin loading** — Add token dependency to prevent stale closure
- **Monitoring API** — SHM fallback to serve fresh data in multi-worker production
- **Scheduler timeline** — Improved mobile responsiveness
- **Fan control** — Use round() instead of int() for PWM-percent conversion
- **Prerelease tags** — Mark unstable and rc tags as prerelease in GitHub Actions
- **E2E tests** — Fix StrictMode auth race condition causing navigation redirect; fix mock data schemas and missing mock routes
- **Release workflow** — Handle existing releases on tag force-push instead of failing with 422

### Refactored

- Split UserManagement.tsx into hook + 5 sub-components
- Split SyncSettings.tsx into hook + 5 sub-components
- Split DeviceManagement.tsx into hook + 6 sub-components
- Split scheduler_service.py into scheduler/ sub-package with 3 modules
- Split benchmark_service.py into benchmark/ sub-package with 7 modules
- Split smart.py into smart/ sub-package with 7 modules

---

## [1.11.0-unstable] - 2026-02-26

### VCL Tracking, Monitoring Worker & Frontend Refactoring

Prerelease with VCL per-file tracking mode, a dedicated monitoring worker process for production, and several major frontend/backend refactors.

### Added

- **VCL tracking mode** — Automatic/manual mode with per-file tracking rules; users control which files are versioned
- **VCL ownership reconciliation** — Admin tool to scan and fix version ownership mismatches after file transfers
- **VCL tracking panel** — New Settings → VCL tab for managing tracking rules and exclusions
- **File-level VCL toggle** — Shield icon in FileManager to enable/disable versioning per file
- **Monitoring worker process** — Dedicated process for telemetry, disk I/O, power monitor, and orchestrator in production (SHM-based IPC)
- **Shared `formatRelativeTime`** — Reusable relative time formatter in `lib/formatters.ts`
- **Vendor chunk splitting** — Manual Rollup chunks for react, recharts, i18n, and lucide-react

### Fixed

- **SchedulerTimeline mobile** — Responsive bar widths, conditional hour labels, tighter spacing on small screens
- **PWM percent conversion** — Use `round()` instead of `int()` to prevent truncation loss

### Changed

- **Refactored DeviceManagement** — Split 997-line monolith into hook + 6 sub-components (133 LOC page)
- **Refactored scheduler service** — Split `scheduler_service.py` into `scheduler/` sub-package with 3 modules
- **Refactored benchmark service** — Split `benchmark_service.py` into `benchmark/` sub-package with 7 modules
- **Refactored SMART service** — Split `smart.py` into `smart/` sub-package with 7 modules
- **Renamed update channel** — "beta" → "unstable" for clarity
- **Production monitoring** — Web workers read from SHM with DB fallback instead of running monitoring in-process

---

## [1.10.1] - 2026-02-24

### Refactoring, Bug Fixes & i18n

### Added

- **i18n for Tapo smart devices** — DE/EN translations for all Tapo device settings strings
- **Apple/iOS SMB compatibility** — SMB settings for Apple device compatibility

### Fixed

- **Production process manager** — start_prod.py no longer kills backend when non-critical worker crashes
- **Fan control temperature sensor** — Read CPU temp sensor instead of board sensor (~26°C)

### Changed

- **Refactored power manager** — Split power/manager.py into 5 sibling modules
- **Refactored update service** — Split update_service.py into update/ sub-package with 7 modules
- **Refactored RAID service** — Split raid.py into raid/ sub-package with 7 modules
- **Refactored file operations** — Split files/operations.py into path_utils, access, and storage modules

---

## [1.10.0] - 2026-02-24

### Notifications, VCL Storage, File Sharing & Multi-Worker Stability

Feature-rich release adding a notification event system, VCL blob storage, improved file sharing, and extensive multi-worker production fixes.

### Added

- **Notification event system** — Backend event emitters with cooldowns, snooze, and sync notifications across services
- **Notification UI** — Grouping, snooze controls, and archive page
- **VCL blob migration** — Migration service with admin UI for VCL storage
- **Configurable VCL storage path** — Dedicated storage path with info endpoint
- **File sharing permissions** — Granular per-user permissions and user list endpoint for shares
- **Storage breakdown** — Cache/VCL-aware storage usage visualization
- **ByteSizeInput component** — Unit-aware byte size editing in forms
- **Binary/decimal byte units** — User setting to toggle between binary (GiB) and decimal (GB) display
- **Persistent fan curve profiles** — DB-backed fan curve presets
- **Releases list** — Show available releases on the update page
- **Ownership transfer** — Cascade VCL versions and quota on file ownership transfer

### Fixed

- **Disk I/O on secondary workers** — Add DB fallback for `/disk-io/current` and derive `available_disks` from DB data when memory is empty
- **RAID member disks in monitoring** — Filter RAID member disks from disk I/O monitoring
- **Multi-worker deployment** — Stabilize with sticky sessions and DB fallbacks for all monitoring endpoints
- **Fan control on secondary workers** — Initialize read-only, detect write permission at startup
- **Fan disappearance** — Prevent fan data loss on transient hwmon scan failures
- **Server uptime** — Initialize start time at module import for consistent multi-worker uptime
- **Disk I/O detection** — Improve initial detection and polling speed
- **CPU/memory endpoints** — Add DB fallback on secondary workers
- **Settings page** — Fix slow load and broken quota display

### Changed

- **Cache system** — Replace bcache SSD cache with file-level cache system
- **Public share links** — Removed public share link UI and backend in favor of granular user-based sharing

---

## [1.9.0] - 2026-02-22

### Multi-Worker Production Support & Security Hardening

Major release adding robust multi-worker support, security fixes, and frontend architecture improvements.

### Added

- **Primary worker guard** — File-lock-based primary election for multi-Uvicorn-worker deployments; background services only run on the primary worker
- **Service heartbeat system** — Primary worker writes service status to DB every 15s; secondary workers read from DB for accurate dashboard data
- **DB fallback for Network & Power widgets** — Secondary workers fall back to database when in-memory buffers are empty (fixes intermittent "Offline" on dashboard)
- **Folder sizes in file manager** — Display cumulative folder sizes in the file listing
- **Desktop sync folder tracking** — Track and display sync badges on synced folders
- **Modular installation system** — Script-based installer with security fixes
- **Detached update runner** — Updates run via `systemd-run` to survive service restarts
- **NotificationContext** — WebSocket connection lives above route level, survives navigation
- **Global 401 interceptor** — Axios + raw fetch handlers trigger centralized auth expiration

### Fixed

- **Privilege escalation via /register** — Hardcode `role="user"` in registration; remove `role` field from `RegisterRequest` schema
- **User list access control** — Restrict `GET /api/users/` to admin-only (was any authenticated user)
- **Sort field enumeration** — Whitelist sortable fields in user list endpoint
- **HSTS over HTTP** — Only send `Strict-Transport-Security` header when request arrived over HTTPS
- **Primary lock race condition** — Open lock file in append mode without unlinking (prevents dual-lock on separate inodes)
- **Stale lock file** — Clean up via `ExecStartPre` / `start_prod.py` instead of in-process unlink
- **Blob URL memory leak** — FileViewer uses ref for proper cleanup on unmount
- **useAsyncData loading state** — Set `loading=true` on reload
- **Mixed timezone datetimes** — Handle tz-aware/naive datetime comparison in device sorting
- **Real disk space checks** — Use actual disk space in production instead of quota-only

### Changed

- **Streaming uploads** — Write chunks directly to disk (non-blocking I/O via `asyncio.to_thread`)
- **Upload rate limits** — Increased to 50,000/min (effectively unlimited)
- **Non-blocking upload metadata** — Nginx upload tuning for large files
- **Stampede protection** — `calculate_used_bytes()` prevents concurrent filesystem scans
- **Search debounce** — 300ms debounce on UserManagement search input
- **AuthContext** — AbortController for `/me` fetch, cleanup on unmount
- **useNotificationSocket** — Stabilized with refs, token from AuthContext (not localStorage)
- **alert() → toast** — Replaced browser alerts with `react-hot-toast` in Settings, MobileDevices pages

### Removed

- **useMemoizedApi hook** — Deleted unused hook
- **RegisterRequest.role field** — Removed to prevent client-side role assignment

---

## [1.8.2] - 2026-02-20

### Desktop Pairing (Device Code Flow)

Adds 6-digit code-based pairing for BaluDesk desktop clients.

### Added

- **Desktop Pairing Backend** — DB model, service, API routes (`/api/desktop-pairing/*`), rate limits, and Alembic migration for code-based desktop client authentication
- **Desktop Pairing Dialog** — Frontend component with 6-digit code input, device confirmation/deny flow, and auto-open via `?pair=1` URL parameter
- **i18n** — Pairing translations for EN and DE

### Fixed

- **Pairing Dialog integration** — Moved button and dialog from unused `SyncPrototype.tsx` to `DeviceManagement.tsx` where `/devices` route actually renders

### Changed

- **Root directory cleanup** — Deleted obsolete scripts, moved utilities to `tools/`

---

## [1.8.1] - 2026-02-20

### Test & CI Fixes

Patch release with test infrastructure fixes and CI pipeline simplification.

### Fixed

- **Raid API tests** — Mock `apiClient` (axios) instead of `globalThis.fetch`, fixing `AxiosError: Network Error`
- **ErrorBoundary test** — Correct `ThrowingComponent` return type to `never`
- **Test setup** — Use `globalThis.ResizeObserver` instead of deprecated `global`
- **Test TypeScript config** — Add dedicated `tsconfig.test.json` for test files

### Changed

- **Playwright CI** — Mocked E2E tests no longer require backend; Playwright `webServer` config handles dev server automatically
- **Playwright CI** — Bump Node.js from 18 to 20 to fix Vite `crypto.hash` error
- **Live E2E CI** — Moved secret check earlier, removed redundant frontend server, simplified service wait logic

---

## [1.8.0] - 2026-02-20

### API Keys, Mobile UX & CI Improvements

Feature release adding API key management for programmatic access and comprehensive mobile responsiveness fixes.

### Added

- **API Key Management** — Generate and manage API keys for programmatic access
  - Create, revoke, and list API keys from Settings page
  - Scoped permissions and expiration support
  - Admin-only feature in Settings tab

### Fixed

- **Mobile sidebar scrolling** — Admin users can now scroll all 14 nav items on small screens
- **Mobile responsiveness** — Improved layouts across multiple pages:
  - AdminDataTable: CSS breakpoints replace JS-based mobile detection
  - AdminDatabase: Stacked toolbar layout with proper touch targets
  - AdminHealth: Disk info grid adapts to screen size
  - ApiCenterPage: Endpoint headers stack on mobile
  - FileManager: Path breadcrumb always visible with tooltip
  - MobileDevicesPage: Notification status wraps properly
  - PowerManagement: Grid breakpoints adjusted for small screens
  - SettingsPage: Tab bar with scroll fade indicator

### Changed

- **CI**: Automatic GitHub Release creation on tag push

---

## [1.7.0] - 2026-02-19

### Sleep Mode, Ownership Transfer & 2FA for All Users

Major feature release adding intelligent sleep management, file ownership transfer, and universal two-factor authentication.

### Added

- **Sleep Mode** — Full soft-sleep and true-suspend (S3) support
  - Auto-idle detection with configurable CPU, disk I/O, and HTTP thresholds
  - Scheduled sleep/wake windows with rtcwake integration
  - Wake-on-LAN configuration per interface
  - Disk spindown via hdparm for data disks during sleep
  - Auto-escalation from soft sleep to true suspend
  - Auto-wake middleware: incoming HTTP requests wake the system from soft sleep
  - Service registration for admin dashboard monitoring
  - Collapsible setup help for missing capabilities (hdparm, rtcwake, WoL, suspend)
  - Sleep history table with state transitions
- **File Ownership Transfer** — Transfer file/folder ownership between users
  - Backend service with residency enforcement migration
  - API endpoints with admin and owner authorization
  - Frontend modal with user selector and residency panel
- **2FA for all users** — Two-factor authentication no longer limited to admins
- **E2E test suite** — Comprehensive Playwright end-to-end tests
- **Performance**: `calculate_used_bytes()` cached with 30s TTL

### Fixed

- Frontend `goBack` navigation simplified to avoid edge cases

### Changed

- Repaired and expanded existing backend test suite

### Status

- **Production Readiness**: Stable
- **Version**: 1.7.0

---

## [1.6.1] - 2026-02-18

### 📚 Documentation Restructure & Code Quality Release

This release focuses on improved documentation organization and significant client-side refactoring.

### ✨ Added

#### Documentation
- **Structured documentation directory** with logical subdirectories:
  - `docs/api/` - API documentation
  - `docs/deployment/` - Deployment, SSL, reverse proxy, production guides
  - `docs/features/` - Feature documentation
  - `docs/getting-started/` - User guide and dev checklist
  - `docs/monitoring/` - Monitoring and telemetry
  - `docs/network/` - VPN, WebDAV, mDNS setup
  - `docs/security/` - Security, audit logging, rate limiting
  - `docs/storage/` - RAID and backup documentation
- **Updated navigation** in docs/README.md with table-based quick links

#### Features
- **Time-based fan schedules** (scheduled mode) for fan control
- **Collapsible LiveActivities section** on dashboard below panels

### 🔧 Changed

#### Client Refactoring
- **Decomposed FileManager and RaidManagement** into smaller, focused components
- **Consolidated API layer** from raw fetch calls to unified `apiClient`
- **Added barrel exports** for all component directories
- **Activated AuthContext** with proper error handling
- **Stabilized idle-timeout hook** to prevent unnecessary re-renders

#### UI Improvements
- **SharesPage and modals** aligned with SystemMonitor design language
- **PluginsPage** aligned with SystemMonitor design language
- **UpdatePage** aligned with SystemMonitor design language
- **Admin Database page** redesigned with sidebar and browse/analytics split
- **Improved analytics tabs** with skeletons and shared UI components
- **Simplified 2FA step** in login page

### 🐛 Fixed

- **RAID 1 disk capacity display** corrected on dashboard
- **Auth idle-timeout** re-render issues resolved

### 📊 Status

- **Production Readiness**: ✅ Stable
- **Version**: 1.6.1

---

## [1.4.2] - 2026-01-29

### 🗓️ Unified Scheduler Dashboard

This release introduces a comprehensive scheduler management system for all background jobs.

### ✨ Added

#### Scheduler Dashboard
- **Unified Scheduler Dashboard** with 5 tabs for complete scheduler management
- **Timeline view** for visual execution history across all schedulers
- **Retry mechanism** for failed executions with one-click re-run
- **Execution history tracking** with status, duration, and error details
- **Real-time status monitoring** for all 6 system schedulers

#### Managed Schedulers
- **RAID Scrub** - Data integrity checks (configurable interval, default: weekly)
- **SMART Scan** - Disk health monitoring (default: hourly)
- **Auto Backup** - Automated system backups (default: daily)
- **Sync Check** - Sync schedule trigger checks (every 5 minutes)
- **Notification Check** - Device expiration warnings (hourly)
- **Upload Cleanup** - Chunked upload cleanup (daily at 3 AM)

#### New API Endpoints (`/api/schedulers/*`)
- `GET /api/schedulers` - List all schedulers with status
- `GET /api/schedulers/{name}` - Get specific scheduler details
- `POST /api/schedulers/{name}/run-now` - Trigger immediate execution
- `GET /api/schedulers/{name}/history` - Get execution history
- `GET /api/schedulers/history/all` - Get combined execution timeline
- `POST /api/schedulers/{name}/toggle` - Enable/disable scheduler

#### Database Models
- `SchedulerExecution` - Tracks individual execution runs with timing, status, and error info
- `SchedulerConfig` - Stores per-scheduler configuration and enabled state

### 🔧 Changed

- Integrated RAID scrub and SMART scan schedulers with service status monitoring
- Enhanced SyncSettings UI with device dropdown and day pickers
- Added execution logging to all scheduler services

### 📊 Status

- **Production Readiness**: 100% (DEPLOYED)
- **Version**: 1.4.2

---

## [1.4.1] - 2026-01-28

### 🚀 Production Deployment Release

This release marks the production deployment of BaluHost on January 25, 2026.

### ✨ Added

#### Production Deployment
- **Live production deployment** on Debian 13 server (Ryzen 5 5600GT, 16GB RAM)
- **PostgreSQL 17.7 migration** complete and verified
- **Nginx reverse proxy** with rate limiting (100 req/s API, 10 req/s auth)
- **Systemd services** for backend (4 Uvicorn workers)
- **Auto-start on reboot** configured

#### Per-Thread CPU Monitoring
- **Task Manager-style display** showing individual thread usage
- **CPU thread breakdown** in monitoring dashboard
- **Historical per-thread data** with retention policies

#### AdminDatabase Page Enhancements
- **Stats tab** with database statistics and table counts
- **Storage tab** with storage breakdown visualization
- **History tab** for query history tracking
- **Maintenance tab** for database maintenance tools

#### Fan Control UI
- **Fan curve chart editor** with drag-to-edit functionality
- **Visual temperature-to-PWM mapping**
- **Real-time RPM and PWM display**
- **Mode switching** (auto/manual/emergency)

#### Network Discovery
- **mDNS/Bonjour integration** for local network discovery
- **Zero-configuration networking** support
- **Service announcement** for web interface and API
- **Device discovery** for other BaluHost instances

#### Service Status Monitoring
- **Health check dashboard** for all services
- **Service registry** with real-time status
- **Admin controls** for service restart/stop/start

### 🔧 Changed

- Updated documentation to reflect production deployment status
- Unified version numbers across all components to 1.4.0
- Enhanced monitoring orchestrator with per-thread CPU support
- Improved fan control service with better curve interpolation

### 🐛 Fixed

- Email validation regex pattern in user registration
- Frontend routing issues with nested routes
- Memory leak in disk I/O monitoring long-running sessions

### 📝 Documentation

- Updated `TODO.md` with completed features and production status
- Updated `README.md` with production deployment information
- Updated `PRODUCTION_READINESS.md` with deployment confirmation
- Updated `TECHNICAL_DOCUMENTATION.md` with new features (Power Management, Fan Control, etc.)
- Updated `ARCHITECTURE.md` with production deployment architecture
- Documented known issues (integer overflow in monitoring tables)

### 📊 Status

- **Production Readiness**: 100% (DEPLOYED)
- **Server**: Debian 13, Ryzen 5 5600GT, 16GB RAM
- **Database**: PostgreSQL 17.7
- **Version**: 1.4.1

---

## [1.4.0] - 2026-01-14

### 🎯 Production Readiness Release

This release makes BaluHost fully production-ready with automated backup system, structured logging, and comprehensive deployment documentation.

### ✨ Added

#### Backup Automation
- **Automated backup scheduler** using APScheduler for periodic backups
- **PostgreSQL pg_dump support** for production database backups
- **Configurable backup intervals** (hourly, daily, weekly, custom)
- **Multiple backup types**: full, incremental, database_only, files_only
- **Retention policies**: max count and age-based cleanup
- **Manual backup script** (`deploy/scripts/backup.sh`) for on-demand backups
- **Backup configuration** via environment variables (`BACKUP_AUTO_ENABLED`, `BACKUP_AUTO_INTERVAL_HOURS`, `BACKUP_AUTO_TYPE`)

#### Production Logging
- **Structured JSON logging** using python-json-logger for log aggregation
- **Environment-based log format**: JSON for production, human-readable for development
- **Configurable log levels** via `LOG_LEVEL` environment variable (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **Log format configuration** via `LOG_FORMAT` environment variable (json, text)
- **Logging initialization** in application startup for consistent configuration

#### Documentation
- **Comprehensive deployment guide** (`docs/DEPLOYMENT.md`) with:
  - 5-minute quick start guide
  - Detailed Docker Compose deployment steps
  - SSL/TLS configuration with Let's Encrypt
  - Monitoring setup instructions
  - Backup configuration guide
  - Troubleshooting section
  - Maintenance procedures
- **Updated `.env.production.example`** with backup and logging configuration
- **Production readiness status** updated to ~98% complete

### 🔧 Changed

#### Backend
- `backend/app/core/config.py`:
  - Added backup automation settings (`backup_auto_enabled`, `backup_auto_interval_hours`, `backup_auto_type`)
  - Added logging configuration settings (`log_level`, `log_format`)
- `backend/app/services/backup.py`:
  - Enhanced with PostgreSQL pg_dump/psql support
  - Added `_backup_postgres_database()` method for PostgreSQL backups
  - Added `_restore_postgres_database()` method for PostgreSQL restores
  - Modified `_get_database_info()` to detect database type (SQLite/PostgreSQL)
- `backend/app/main.py`:
  - Integrated backup scheduler startup/shutdown
  - Added structured logging initialization on app startup
- `backend/pyproject.toml`:
  - Added `python-json-logger>=2.0.0,<3.0.0` dependency

#### Documentation
- `PRODUCTION_READINESS.md`:
  - Updated executive summary to ~98% production-ready
  - Marked backup automation as ✅ COMPLETED
  - Marked error handling & logging as ✅ COMPLETED
  - Marked deployment documentation as ✅ COMPLETED
  - Updated production checklist
  - Changed status to "READY FOR PRODUCTION DEPLOYMENT"

### 📦 Dependencies

- Added: `python-json-logger` (^2.0.0) for structured JSON logging

### 🚀 Deployment

#### New Environment Variables
```bash
# Logging
LOG_LEVEL=INFO              # DEBUG|INFO|WARNING|ERROR|CRITICAL
LOG_FORMAT=json             # json|text

# Backup Automation
BACKUP_AUTO_ENABLED=true    # Enable automated backups
BACKUP_AUTO_INTERVAL_HOURS=24  # Backup interval (hours)
BACKUP_AUTO_TYPE=full       # full|incremental|database_only|files_only
```

#### Backup Script Usage
```bash
# Full backup (default)
./deploy/scripts/backup.sh

# Database-only backup
./deploy/scripts/backup.sh --type database_only

# Files-only backup
./deploy/scripts/backup.sh --type files_only

# Without Docker
./deploy/scripts/backup.sh --no-docker
```

### 🔒 Security

- No security changes in this release
- Existing security hardening from v1.3.0 remains active (8/8 critical vulnerabilities fixed)

### 📊 Status

- **Production Readiness**: ~98% (up from ~95%)
- **Critical Blockers**: None
- **Optional Enhancements**: Print statement cleanup, load testing, PWA

### 📝 Notes

This release focuses on operational excellence and production deployment readiness. BaluHost is now suitable for production deployment with:
- Automated backup system
- Production-grade logging
- Comprehensive deployment documentation
- Full PostgreSQL support

---

## [1.3.0] - 2025-12-20

### 🎯 Feature Complete Release

Major features implemented: Monitoring, Security Hardening, Testing Infrastructure.

### ✨ Added

#### Monitoring & Alerting
- **Prometheus metrics endpoint** (`/api/metrics`) with 40+ custom metrics
- **Grafana dashboards**: System Overview, RAID Health
- **20+ alert rules** across 6 groups (Critical, Warning, Info severity)
- **Docker Compose monitoring profile** for easy deployment
- System metrics: CPU, memory, disk, network monitoring
- RAID metrics: array status, disk count, sync progress
- SMART metrics: disk health, temperature, power-on hours
- Application metrics: HTTP requests, file operations, database connections

#### Security Hardening
- Refresh token revocation with JTI tracking
- Password policy enforcement (8+ chars, uppercase, lowercase, number)
- Consolidated auth system (single secret key)
- Security headers middleware activated
- Rate limiting on all critical endpoints (login, register, password change)
- Secret key validation in production mode
- Deprecated code removal (datetime.utcnow)

#### Testing Infrastructure
- 40 test files with 364 test functions
- Security tests (critical vulnerabilities, headers, JWT, input validation)
- Integration tests (files API, sync, mobile, remote server)
- RAID tests (9 files: parsing, dry-run, scrubbing, scheduling)
- Feature tests (audit logging, database, upload progress)
- 3 GitHub Actions workflows (RAID tests, Playwright E2E, mdadm tests)

#### Deployment Infrastructure
- Docker Compose with multi-stage Dockerfiles (backend + frontend + PostgreSQL)
- Nginx reverse proxy with SSL/TLS (Let's Encrypt automation)
- Security headers configuration (OWASP best practices)
- Rate limiting zones (API, auth, file uploads)
- `.env.production.example` template

### 🔧 Changed

- PostgreSQL fully supported with docker-compose.postgres.yml
- Database session management improved
- File metadata service migrated to database
- Alembic migrations configured
- Audit logs moved from JSON files to database

### 📦 Dependencies

- Added: `prometheus-client` for metrics collection
- Added: `slowapi` for rate limiting

### 🚀 Deployment

- Docker: `docker-compose up -d`
- Monitoring: `docker-compose --profile monitoring up -d`
- SSL: `./deploy/ssl/setup-letsencrypt.sh domain.com email@example.com`

---

## [1.2.0] - 2025-11-XX

### Previous Release

_(Add details from previous releases as they become available)_

---

## Legend

- ✨ Added: New features
- 🔧 Changed: Changes to existing functionality
- 🗑️ Deprecated: Soon-to-be removed features
- 🔒 Security: Security improvements
- 🐛 Fixed: Bug fixes
- 📦 Dependencies: Dependency updates
- 🚀 Deployment: Deployment-related changes
- 📝 Notes: Additional information

---

**Maintained by**: Xveyn
**License**: MIT
**Repository**: https://github.com/your-org/baluhost
