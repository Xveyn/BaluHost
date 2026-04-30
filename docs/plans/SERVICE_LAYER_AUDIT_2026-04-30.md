# Service Layer Audit — 2026-04-30

Strukturelle/architektonische Code-Quality-Analyse von `backend/app/services/` (alle Top-Level-Files + Subdirectories: `audit/`, `backup/`, `benchmark/`, `cache/`, `cloud/`, `files/`, `hardware/`, `monitoring/`, `notifications/`, `pihole/`, `power/`, `scheduler/`, `setup/`, `sync/`, `update/`, `versioning/`, `vpn/`).

**Zweck:** Status-Quo-Dokumentation mit konkreten Verbesserungsvorschlägen. Keine sofortige Umsetzung — Roadmap-Input.

**Konvention zur Service-Struktur:** siehe `backend/app/services/CLAUDE.md` (Patterns: Dev/Prod-Backends mit `protocol.py`, Singletons via `_instance`, Background Tasks via Lifespan, SHM für Inter-Process-Comms).

---

## Findings nach Impact

| # | Finding | Kategorie | Aufwand |
|---|---------|-----------|---------|
| 1 | Doppelter Backup-Scheduler (APScheduler + zentraler Worker) | Korrektheits-Risiko | medium |
| 2 | `metadata_db.py` Optional-Session verschleiert Transaktionen | Korrektheits-Risiko | medium |
| 3 | `power/sleep.py` 1048 LOC mit Middleware-Concern inline | Wartbarkeit / Layer-Verletzung | medium |
| 4 | `fan_control.py` enthält ABC inline statt `fan_protocol.py` | Pattern-Inkonsistenz | low |
| 5 | `samba_service.py` / `webdav_service.py` ohne Backend-Abstraktion | Pattern-Inkonsistenz / Testbarkeit | medium |
| 6 | VPN: zwei Klassen namens `VPNService` | Naming / Klarheit | low |
| 7 | Duale Metadata-Systeme (JSON + DB) ohne Migration-Guard | Tech Debt | medium |
| 8 | GPU-Code in `monitoring/gpu/` statt `power/gpu_power/` | Konzeptuelle Unklarheit / Doku | low |
| 9 | Plugin-Cluster: 4 Top-Level-Files ohne Subdir | Gruppierung | low |

---

## 1. Doppelter Backup-Scheduler — Korrektheits-Risiko

**Wo**
- `backend/app/services/backup/scheduler.py:23` — `_backup_scheduler: Optional["BackgroundScheduler"] = None`
- `backend/app/services/scheduler/worker.py:44` — `SCHEDULER_POWER_LEVELS` enthält `"backup": "surge"` (zentraler Worker dispatcht Backup bereits)

**Warum problematisch**
Backup unterhält eine eigene APScheduler-Instanz — exakt das Problem, das `sync/background.py` hatte und das im Docstring dokumentiert ist: *"Historically this module ran its own APScheduler... That caused two `sync_check` executions per tick."* Sync wurde migriert, Backup nicht. Risiko: doppelte Backup-Ausführungen in Prod.

**Vorschlag**
1. Verifizieren ob `start_backup_scheduler()` noch aus Lifespan/`main.py` aufgerufen wird.
2. Falls ja: APScheduler-Instanz aus `backup/scheduler.py` entfernen, Job läuft nur noch über zentralen `scheduler/worker.py`.
3. Analog zur Sync-Migration vorgehen — `sync/background.py` als Vorlage nutzen.

**Risiko/Aufwand:** medium — erfordert Verifikation in Prod-Logs ob doppelt läuft.

---

## 2. `metadata_db.py` Optional-Session-Pattern

**Wo**
- `backend/app/services/files/metadata_db.py:42-62` (`get_metadata`)
- Folge-Funktionen: `create_metadata`, `set_owner` etc. — alle mit demselben `should_close`-Boilerplate

**Warum problematisch**
Alle Funktionen akzeptieren `db: Optional[Session] = None` und erstellen intern via `SessionLocal()` mit `try/finally: db.close()`. Wenn ein Caller mehrere Operationen atomar machen will (z.B. `create + set_owner` in einer Transaktion), muss er explizit eine Session übergeben. Vergisst er das → mehrere separate Transaktionen ohne Atomizität. Der Boilerplate verbirgt dieses semantische Risiko.

**Vorschlag**
1. Alle Funktionen auf `db: Session` (required) umstellen.
2. Callsites die ohne Session aufrufen → auf `with SessionLocal() as db:` umstellen.
3. Macht Transaktionsgrenzen explizit sichtbar.

**Risiko/Aufwand:** medium — viele Call-Sites in `files/operations.py`, `files/access.py` müssen angepasst werden.

---

## 3. `power/sleep.py` — 1048 LOC mit Layer-Verletzung

**Wo**
- `backend/app/services/power/sleep.py:50-94` — `SleepBackend` ABC + Re-Import der Backends
- `backend/app/services/power/sleep.py:101-116` — HTTP-Request-Counter (`record_http_request`, `get_http_requests_per_minute`)
- `backend/app/services/power/sleep.py:118-994` — `SleepManagerService`
- `backend/app/services/power/sleep.py:999-1048` — Modul-Level-Wiring

**Warum problematisch**
Die Datei mischt vier Concerns: ABC-Definition, Cross-Cutting HTTP-Counter, Service-Implementierung, Wiring. Der HTTP-Counter ist Cross-Cutting: er wird von Middleware geschrieben (`record_http_request`) und vom Service gelesen — d.h. `sleep.py` wird heimlich aus `app/middleware/` importiert. Layer-Verletzung analog zu `telemetry.py`.

**Vorschlag**
1. HTTP-Counter extrahieren → `power/activity_tracker.py` (wird von Middleware UND `SleepManagerService` importiert).
2. ABC extrahieren → `power/sleep_protocol.py`.
3. Backend-Re-Imports entfernen (Backends importieren aus `sleep_protocol.py`).
4. Verbleibende `sleep.py` < 400 LOC, nur Service + Wiring.

**Risiko/Aufwand:** medium — alle Import-Stellen für `record_http_request` (Middleware) und `SleepBackend` (Backends) müssen angepasst werden.

---

## 4. `fan_control.py` enthält Protocol/Backends inline

**Wo**
- `backend/app/services/power/fan_control.py:72-112` — `FanControlBackend` (ABC), `FanData`, `HysteresisState`, `TempSensorData`
- `backend/app/services/power/fan_backend_dev.py:12` — `from app.services.power.fan_control import FanControlBackend, FanData, TempSensorData`

**Warum problematisch**
Etabliertes Muster im Projekt: `cpu_protocol.py` + `cpu_dev_backend.py` + `cpu_linux_backend.py`. Fan-Control weicht davon ab: ABC steht im Service, Backends importieren zurück → leichte Zirkularität. Jedes Mal wenn ein Backend importiert wird, wird der Service-Modul-Konstruktor evaluiert.

**Vorschlag**
1. `fan_protocol.py` extrahieren mit `FanControlBackend`, `FanData`, `HysteresisState`, `TempSensorData`.
2. `fan_backend_dev.py` und `fan_backend_linux.py` importieren aus `fan_protocol.py`.
3. `fan_control.py` importiert aus `fan_protocol.py`.
4. Analog zu `cpu_protocol.py` — keine Logikänderung.

**Risiko/Aufwand:** low — reine Verschiebung.

---

## 5. `samba_service.py` / `webdav_service.py` ohne Backend-Abstraktion

**Wo**
- `backend/app/services/samba_service.py` (~342 LOC)
- `backend/app/services/webdav_service.py`

**Warum problematisch**
Beide sind System-Dienste mit Dev/Prod-Unterschieden, verwenden aber Inline-`if settings.is_dev_mode`-Branches statt protocol/dev_backend/linux_backend. Inkonsistent mit RAID/Power/Benchmark/PiHole. WebDAV-Docstring erkennt sich selbst als Worker-Service ("analogous to scheduler_worker_service.py"), hat aber kein Backend-Pattern. Schwer testbar ohne Mock-Injection.

**Vorschlag**
1. `samba/` Subdir: `samba/service.py`, `samba/protocol.py`, `samba/dev_backend.py`, `samba/linux_backend.py`.
2. `webdav/` Subdir analog (komplexer wegen eigenem Worker-Prozess).
3. Imports in Routes/Lifespan anpassen.

**Risiko/Aufwand:** medium — Refactoring-Größe ähnlich PiHole-Subdir.

---

## 6. VPN: zwei Klassen namens `VPNService`

**Wo**
- `backend/app/services/vpn/__init__.py:13` — `from app.services.vpn.profiles import VPNService as VPNProfileService`
- `backend/app/services/vpn/service.py` — `class VPNService` (Lifecycle/Config)
- `backend/app/services/vpn/profiles.py:16` — `class VPNService` (Profile-Renderer mit QR-Code)

**Warum problematisch**
Namenskollision. `profiles.py` ist eigentlich ein Config-Renderer/Exporter, keine Service-Klasse. Wer `from app.services.vpn import VPNService` schreibt, bekommt nicht offensichtlich die richtige Klasse.

**Vorschlag**
1. Klasse in `profiles.py` umbenennen → `VPNProfileExporter` (oder `VPNConfigRenderer`).
2. `__init__.py`-Alias entsprechend anpassen.
3. Imports in `api/routes/vpn.py` aktualisieren.

**Risiko/Aufwand:** low — pure Umbenennung.

---

## 7. Duale Metadata-Systeme (JSON + DB)

**Wo**
- `backend/app/services/files/__init__.py:52-68` — beide werden parallel als `get_owner_legacy` / `get_owner` exportiert
- `backend/app/services/files/metadata.py` (JSON-basiert, `.metadata.json`-Dateien)
- `backend/app/services/files/metadata_db.py` (SQLAlchemy auf `file_metadata`-Tabelle)
- `_normalize_path` ist in beiden Dateien identisch → DRY-Verletzung

**Warum problematisch**
Halbfertiger Migrationszustand in einem 99% prod-ready System. Callsites müssen wissen, ob sie Legacy- oder DB-Backend rufen. Ohne Migration-Guard / Löschdatum / klare Strategie wächst die Schuld weiter.

**Vorschlag**
1. **Sofort (low):** `_normalize_path` zentral nach `path_utils.py` (existiert bereits) verschieben — aus beiden Dateien importieren.
2. **Entscheidung treffen:** Wenn DB-Backend die kanonische Implementierung ist:
   - `metadata.py` auf read-only/migration-only beschränken
   - Klares `_legacy`-Suffix
   - FIXME-Marker mit Löschzieldatum (z.B. v1.32.0)
3. Wenn beide weiterhin parallel aktiv: dokumentieren wann welches verwendet wird.

**Risiko/Aufwand:** low (DRY-Fix) bis medium (vollständige Migrations-Entscheidung).

---

## 8. GPU-Code in `monitoring/gpu/` statt `power/gpu_power/`

**Wo**
- `backend/app/services/monitoring/gpu/backend.py`, `amd_backend.py`, `nvidia_backend.py`, `dev_backend.py`
- Letzte Commits sagen `feat(gpu-power): …` — Verzeichnis aber unter `monitoring/`

**Warum problematisch**
`read_sample()` liefert sowohl Clocks (`core_clock_mhz`, `memory_clock_mhz`) als auch Usage-Daten (`usage_percent`, VRAM) gemischt. Konzeptuell ist GPU-Power-Management (Takt, Leistungsaufnahme) ein `power/`-Concern, GPU-Monitoring ein `monitoring/`-Concern. Wer GPU-Frequenzskalierung addieren will, muss in `monitoring/` eingreifen.

**Vorschlag (zwei Optionen)**
- **Option A (low, Doku):** Bei `monitoring/gpu/` belassen, klar als "monitoring-only" deklarieren (Clocks als reine Observability), CLAUDE.md-Eintrag in `monitoring/gpu/`.
- **Option B (high, splitten):** `power/gpu/` für Frequenz/Limits, `monitoring/gpu/` nur für Read-Only-Sampling. Erst nötig wenn echte GPU-Frequenzskalierung kommt.

**Risiko/Aufwand:** low (Option A, jetzt) bis high (Option B, später).

---

## 9. Plugin-Cluster ohne Subdirectory

**Wo**
- `backend/app/services/plugin_service.py` (CRUD für `InstalledPlugin`)
- `backend/app/services/plugin_marketplace.py` (Index-Fetch, Install-Driver)
- `backend/app/services/plugin_update_check.py` (Background-Update-Scanner)
- `backend/app/services/dashboard_panel_bridge.py` (SHM→WS für Plugin-Dashboard, ruft `plugin_service.get_dashboard_panel_plugin`)

**Warum problematisch**
Vier Files mit klar zusammenhängender Verantwortung liegen lose im Top-Level. Pattern wie `audit/`, `notifications/`, `cloud/` würde passen. Kein Konflikt mit `app/plugins/` (das ist Runtime/SDK: `manager.py`, `installer.py`, `hooks.py`, `sdk/`).

**Vorschlag**
1. `services/plugins/` anlegen.
2. 4 Files verschieben: `service.py`, `marketplace.py`, `update_check.py`, `dashboard_bridge.py` (oder Original-Namen behalten).
3. Imports anpassen (~10–20 Stellen in Routes, Lifespan, Tests).
4. CLAUDE.md im Service-Layer aktualisieren.

**Risiko/Aufwand:** low — klar abgegrenzt, geringes Risiko.

---

## Empfohlene Reihenfolge bei Umsetzung

1. **Finding 1 (Backup-Scheduler verifizieren)** — potentieller Korrektheits-Bug, Prio
2. **Findings 4 + 9 (fan_protocol + Plugin-Cluster)** — low risk, sofort sichtbarer Pattern-Cleanup
3. **Findings 6 + 8 (VPN-Naming + GPU-Doku)** — kosmetisch, einmal anfassen
4. **Finding 3 (sleep.py-Split)** — mittel, gewinnt viel Klarheit
5. **Findings 5 + 2 (Samba/WebDAV + metadata_db Sessions)** — größere Eingriffe, separate PRs
6. **Finding 7 (Metadata-Migration)** — strategische Entscheidung erforderlich

---

## Was NICHT in diesem Audit ist

Bewusst ausgeklammert (= Style/Tests/Doku, nicht strukturell):
- Fehlende Tests einzelner Services
- Fehlende Type Hints
- Docstring-Abdeckung
- Performance-Optimierungen
- Konkrete Bug-Fixes (außer #1, da Korrektheits-Risiko)

## Referenz-Files

Wichtigste Files für tieferes Lesen je Finding:

- **#1**: `backup/scheduler.py`, `scheduler/worker.py`, `sync/background.py`
- **#2**: `files/metadata_db.py`, `files/operations.py`
- **#3**: `power/sleep.py`, `app/middleware/`
- **#4**: `power/fan_control.py`, `power/cpu_protocol.py` (Vorlage)
- **#5**: `samba_service.py`, `webdav_service.py`, `pihole/` (Vorlage)
- **#6**: `vpn/__init__.py`, `vpn/service.py`, `vpn/profiles.py`
- **#7**: `files/__init__.py`, `files/metadata.py`, `files/metadata_db.py`, `files/path_utils.py`
- **#8**: `monitoring/gpu/`, letzte Git-Commits auf `development`
- **#9**: `plugin_service.py`, `plugin_marketplace.py`, `plugin_update_check.py`, `dashboard_panel_bridge.py`, `app/plugins/` (zur Abgrenzung)
