# BaluHost TUI — Feature Audit & Roadmap

**Stand:** 2026-04-30
**Zweck:** Alternativ-Zugang im LAN (kein VPN-Tunnel-Start aus der TUI)
**Letzte echte Änderung:** Commit `b1b7698` — seither nur Import-Refactors (`cc2bb2c`, `364d74a`)

---

## Aktueller Stand

### Vorhandene Features

| Bereich | Screen / Datei | Status |
|---|---|---|
| Login (admin-only) | `screens/login.py` | HTTP-Health-Check + lokaler DB-Fallback |
| Dashboard | `screens/dashboard.py` | CPU/RAM/Storage/Network, RAID, User-Counts, Audit-Snippets |
| User-Management | `screens/users.py` | Volles CRUD (Create/Edit/Reset-PW/Delete) |
| File-Browser | `screens/files.py` | Lokal + Remote, Download, Upload, Preview |
| RAID-Controls | `screens/raid.py` | RAID-Screen vorhanden |
| Audit-Logs | `screens/logs.py` | Recent Activity Viewer |
| CLI-Commands | `main.py` | `dashboard`, `reset-password`, `status`, `users`, `files-download/upload` |

### Connection Modes (`main.py`)

- `auto` — detect (default)
- `local` — direct DB access
- `remote` — HTTP-API mit Bearer-Token

---

## Architektur-Befund

Die TUI mischt aktuell **Direkt-DB-Zugriffe** (`SessionLocal()` in `login.py`, `users.py`, `dashboard.py`) mit **HTTP-Calls** (in `files.py` via `get_context()`).

**Empfehlung:** Alles über die HTTP-API routen. Vorteile:
- Automatisches Auth, Rate-Limiting, Audit-Logging
- Identischer Code funktioniert auch remote (z.B. vom Rock Pi 4C+)
- Klare Trennung TUI ↔ Backend
- Keine doppelte Business-Logik

**Trade-off:** Backend muss laufen — aber genau dann ist die TUI ja der Recovery-Pfad in das WebUI-Outage-Szenario. Der Direkt-DB-Fallback sollte explizite Ausnahme für Notfälle bleiben (z.B. `reset-password` Command — existiert bereits richtigerweise als CLI-only).

---

## Feature-Roadmap nach Priorität

### 🔴 Pflicht — fehlt aktuell, hoher Recovery-/Diagnose-Wert

#### 1. Service-Health & Service-Restart
- **Backend:** `app/services/service_status.py`, `/api/admin/*`
- **Use-Case:** Wenn WebUI tot ist, ist das der erste Anlaufpunkt
- **Features:**
  - List Services + Status (running/stopped/failed)
  - Action: Restart Backend / Reload Service
  - Health-Indicators (uptime, memory, error-rate)

#### 2. System-Logs live (journalctl-ähnlich)
- **Backend:** `baluhost-backend.service` + Audit-DB
- **Use-Case:** Diagnose im Echtzeit
- **Features:**
  - Tail-Modus mit Filter (Level, Service)
  - Pause / Resume
  - Search innerhalb Buffer
  - Audit-Viewer existiert separat — hier geht's um System-Logs

#### 3. Power: Sleep / Reboot / Shutdown
- **Backend:** `app/services/power/manager.py`, `/api/sleep/*`
- **Use-Case:** Klassischer "headless via SSH" Workflow
- **Features:**
  - Confirm-Dialog (Sleep / Reboot / Shutdown)
  - Wake-up-Status
  - Last-Sleep-Timestamp anzeigen

#### 4. SMART / Disk-Health
- **Backend:** `app/services/hardware/smart/`
- **Use-Case:** Single-Disk-Health (Temp, Reallocated Sectors, Power-On-Hours)
- **Features:**
  - Per-Disk SMART-Übersicht
  - Health-Status-Indicator (PASS/FAIL/WARN)
  - Frühwarnung vor Ausfällen
- **Lücke:** RAID-Screen zeigt Array-Status — Single-Disk-Details fehlen

#### 5. Telemetrie-Detail-Screen
- **Backend:** `app/services/telemetry.py`, `app/services/monitoring/*`
- **Use-Case:** Drill-Down über das Dashboard hinaus
- **Features:**
  - CPU-Frequenz-Verlauf
  - CPU-Temperatur (per-Core)
  - Pro-Thread-Auslastung
  - Memory-Detail (Cached/Buffered/Swap)

---

### 🟡 Sollte mit — mittlere Priorität

#### 6. Power-Profile & Fan-Control
- **Backend:** `app/services/power/`, `app/services/power/fan_control.py`
- **Features:** Read + Write — Profile umschalten, Fan-Mode setzen

#### 7. Backup
- **Backend:** `app/services/backup/`
- **Features:** Status, manueller Trigger, letzte Restore-Points

#### 8. Network-Status
- **Backend:** `app/services/network_discovery.py`, `psutil`
- **Features:** Interfaces, IPs, aktive Verbindungen
- **Use-Case:** "Ist NAS überhaupt noch erreichbar?"

#### 9. Scheduler-Übersicht
- **Backend:** `app/services/scheduler/service.py`
- **Features:** Letzter Run, Run-Now per Hand, Execution-History

---

### 🟢 Optional — Read-Only reicht

| Feature | Backend | Hinweis |
|---|---|---|
| VPN-Clients | `app/services/vpn/` | **Nur anzeigen** — kein Tunnel-Start (per User-Vorgabe) |
| Mobile-Devices | `app/services/mobile.py` | Liste registrierter Geräte |
| Shares | `app/services/files/` | Aktive Share-Links |
| Pi-hole | `app/services/pihole/` | Status + Block-Stats |

---

## Bestehende Issues / Tech-Debt

### Code-Smells in der bestehenden TUI

1. **Doppelte Action-Definition** (`app.py:143-152`)
   ```python
   def action_logs(self) -> None:  # Erste Definition mit Auth-Check
       if not self.current_user: ...
   def action_logs(self) -> None:  # Zweite Definition überschreibt — KEIN Auth-Check
       self.push_screen(AuditLogViewerScreen())
   ```
   → Bug: Audit-Logs sind ohne Login erreichbar.

2. **Direkt-DB-Zugriffe trotz `mode='remote'`**
   `login.py`, `users.py`, `dashboard.py` ignorieren `mode` und gehen direkt an `SessionLocal()`.
   → Im Remote-Mode funktioniert die TUI nur, wenn die DB-URL auch remote stimmt — was selten der Fall ist.

3. **`sys.path.insert(...)` in jedem Screen-Modul**
   `screens/dashboard.py:6`, `screens/login.py:5`, etc. — sollte einmal in `__init__.py` oder via Package-Install gelöst sein.

4. **RAID-Widget zeigt "not available in TUI dev mode"** (`dashboard.py:195-197`)
   Mock-Daten werden bewusst übersprungen — sollte stattdessen die Mock-Daten zeigen, dann ist der Dev-Workflow nutzbar.

5. **Settings-Screen fehlt komplett**
   Keine TUI-eigene Config (Server-URL, Token, Theme).

---

## Empfohlene Implementierungs-Reihenfolge

1. **Bugfix:** Doppelte `action_logs` in `app.py` entfernen
2. **Refactor:** TUI auf HTTP-API-only umstellen (Direkt-DB nur für `reset-password` CLI)
3. **Feature 1:** Service-Health & Restart-Screen
4. **Feature 3:** Power-Actions (Sleep/Reboot/Shutdown) — kleinster Scope, größter Recovery-Wert
5. **Feature 4:** SMART-Screen
6. **Feature 2:** System-Logs live
7. **Feature 5:** Telemetrie-Detail
8. — Rest nach Bedarf —

---

## Out of Scope (per User-Vorgabe)

- ❌ VPN-Tunnel aus der TUI starten
- ❌ Externe Erreichbarkeit (TUI bleibt LAN-only)
