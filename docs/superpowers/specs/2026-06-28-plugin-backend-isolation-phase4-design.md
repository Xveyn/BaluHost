# Plugin-Backend-Isolation Phase 4 — Request-Proxy + PluginManager-Dual-Path (Design)

- **Datum:** 2026-06-28
- **Status:** Design / Spec (Brainstorm abgeschlossen, vor Implementierungsplan)
- **Track:** Plugin-Sandboxing **Track B**, Phase 4 — baut auf Phase 1–3 auf.
- **Übergeordnete Spec:** `docs/superpowers/specs/2026-06-26-plugin-backend-isolation-design.md`
- **Audit-Referenz:** `SECURITY_AUDIT_2026-06-14.md` (Plugin-Sandboxing, größtes verbleibendes Architektur-Risiko)

---

## Kontext & Ausgangslage

Phase 1–3 haben die komplette Sandbox-Maschinerie gebaut — aktuell **toter Code**,
weil nichts im laufenden `PluginManager` sie aufruft:

| Komponente | Datei | Status |
|---|---|---|
| RPC (Framing, Channel, Transport) | `sandbox/protocol.py`, `channel.py`, `transport.py` | ✅ |
| Worker-Prozess + Loader + SDK | `sandbox/worker.py`, `loader.py`, `sdk.py` | ✅ |
| `SandboxSupervisor` (spawn/health/restart/kill, `dispatch()`) | `sandbox/supervisor.py` | ✅ (Spawn-Hook = Stub → Phase 5) |
| `CapabilityRouter` (default-deny, `storage.*`/`core.*`) | `sandbox/capabilities.py` | ✅ (Deps per Injection) |

Der reale Backend-Pfad (`manager.py`) ist unberührt: `load_plugin()` macht für **alle**
Plugins `spec.loader.exec_module(module)` — also auch für `source == "external"` noch
In-Process-RCE. Phase 4 schneidet das ab und verdrahtet die Sandbox in den echten
Request-Pfad.

### Korrektur einer Spec-Annahme

Die übergeordnete Spec (Zeile ~168) behauptet, `granted_api_scopes` sei als
DB-Spalte „bereits vorhanden" (aus Track A). **Das stimmt nicht.** Tatsächlich:

- DB `InstalledPlugin` hat nur **`granted_permissions`** (JSON) — die alte
  `PluginPermission`-Enum (`file:write`, `system:execute`, …), gegated durch
  `PluginGateMiddleware`.
- Das Manifest (`plugin.json`) hat ein deklaratives Feld **`api_scopes`**
  (`manifest.py:57`), das aktuell **nirgends gespeichert oder durchgesetzt** wird —
  es wartet auf genau diese Phase.

Phase 4 führt deshalb die fehlende `granted_api_scopes`-DB-Spalte ein.

---

## Entscheidungen (aus dem Brainstorm)

| Frage | Entscheidung |
|---|---|
| Scope-Storage | **Dedizierte `granted_api_scopes`-JSON-Spalte** (Alembic-Migration), getrennt von `granted_permissions`. |
| Scope-Vergabe-Tiefe in Phase 4 | **Backend-only** (Spalte + API + Durchsetzung). Install-Scope-Picker-UI → Phase 5. |
| `core.*`-Katalog v1 | **`core.system_metrics` + `core.notify`** ausliefern (beide Stubs sind fertig + getestet, beide harmlos). Plus `storage.*` und eigene Routen. |
| Multi-Worker-Topologie | **Ein Subprozess pro uvicorn-Worker.** Aktueller 1:1-Transport bleibt unverändert; kein Cross-Worker-IPC. |

---

## Architektur

### 1. Scope-Storage & -Vergabe

- **Neue Spalte** `granted_api_scopes: JSON` (nullable, default `list`) auf
  `installed_plugins`. Migration **muss an die echten `alembic heads` ketten**, nicht
  an den stale dev-DB-Head (siehe `project_alembic_migration_head_pitfall`).
- `enable`-Pfad eines externen Plugins akzeptiert + persistiert `granted_api_scopes`.
  **v1: Backend-only** — kein UI-Picker (Phase 5).
- Gewährbare Menge = die im Manifest deklarierten `api_scopes` ∩ bekannter Host-Katalog
  (`storage`, `core.system_metrics`, `core.notify`). Unbekannte/nicht-deklarierte Scopes
  werden beim Grant abgelehnt.
- `CapabilityRouter.granted_scopes` wird aus dieser Spalte gespeist.
- Die alten `PluginPermission`-Enum-Strings (`granted_permissions`) bleiben
  **unangetastet** — informativ nur für bundled.

### 2. Dual-Path im `PluginManager`

- `enable_plugin` / `load_plugin` verzweigen auf `discovered.source`:
  - `bundled` → **unveränderter** `exec_module`-Pfad (trusted, in-process).
  - `external` → **nie** `exec_module`. Stattdessen:
    1. Manifest lesen (ohne Code-Ausführung),
    2. `CapabilityRouter` mit `granted_api_scopes` + injizierten Host-Deps bauen,
    3. `SandboxSupervisor` starten (`.start()` → spawn + Health-Handshake),
    4. in neuem `self._sandboxes[name]` registrieren (getrennt von `self._plugins`).
- `disable_plugin` (external) → `supervisor.stop()` (graceful `shutdown`-RPC →
  SIGTERM → SIGKILL mit Timeout). `shutdown_all` nimmt Sandboxes mit.
- **Multi-Worker:** Jeder uvicorn-Worker spawnt + besitzt seinen **eigenen**
  Subprozess. Der aktuelle 1:1-Transport (`WorkerListener` lauscht, Worker connectet
  einmal zurück) bleibt unverändert. `start_background_tasks`-Gating ist fürs Spawnen
  **irrelevant** — v1-external hat keine Background-Tasks/Events (out-of-scope), also
  keine N×-Ausführung. Storage ist DB-shared → über alle Worker konsistent.
  - *Accepted cost:* N× Plugin-Prozesse + N× Kalt-RAM (bei Ryzen 5 / 16 GB + wenigen
    Plugins akzeptabel).

### 3. Proxy-Router & Gating

- **Catch-all** `/api/plugins/{name}/{path:path}` (alle HTTP-Methoden), in den
  kombinierten Plugin-Router **nach** den bundled-Routern eingehängt → bundled-Routen
  matchen zuerst, nur ungematchte Pfade erreichen den Catch-all. Der Catch-all ist
  statisch gemountet; enable/disable externer Plugins spawnt/killt nur den Subprozess,
  ohne Route-/OpenAPI-Rebuild.
- Handler-Ablauf:
  1. `Depends(get_current_user)` (jeder authentifizierte User, wie bundled-Routen),
  2. ist `{name}` ein enabled externes Sandbox-Plugin in `self._sandboxes`? sonst **404**,
  3. Body-Cap prüfen (sonst **413**),
  4. Header-Allowlist anwenden,
  5. `context {user_id, username, role}` host-seitig auflösen (**kein Token**),
  6. `supervisor.dispatch(method, path, body, context)` → `http_response` zurück.
- `PluginGateMiddleware` bleibt unverändert: für external ist
  `get_required_permissions(name)` leer (Plugin nie in `self._plugins`) → Middleware
  lässt durch, der Catch-all-Handler macht die echten Checks.
- **Eigene Plugin-Routen** brauchen **keinen** spezifischen Scope (nur Auth + enabled).
  Scopes gaten ausschließlich den `cap_call`-Pfad (storage/core) host-seitig im
  `CapabilityRouter`.

### 4. RPC-Request-Contract, Limits, Error-Scrubbing

- **Buffered** Bodies in v1; Streaming (große Up-/Downloads) = Follow-up.
- **Caps** (konfigurierbar, Defaults):
  - Request-Body ≤ **10 MB** → sonst 413,
  - Response-Body ≤ **10 MB**,
  - Per-Request-Timeout **30 s** → sonst 504,
  - max in-flight Requests/Plugin = **10**.
- **Header-Allowlist:**
  - rein (Host → Plugin): `content-type`, `accept`,
  - raus (Plugin → Client): `content-type`,
  - **nie** `Authorization` / `Cookie` (in keine Richtung). Token verlässt nie den Host.
- **Error-Scrubbing** (knüpft an Posten 2 / Error-Leakage an):
  - Plugin-Crash im Request → gescrubbtes **502**,
  - Per-Request-Timeout → **504**, Request abgebrochen; wiederholte Timeouts zählen aufs
    Crash-Budget des Supervisors,
  - Detail nur server-side geloggt, nie an den Client.
- **Capability-Deps produktiv injizieren** (heute nur in Tests gesetzt):
  `session_factory` (DB-Session), `metrics_reader` (read-only Systemmetriken),
  `notifier` (Notification an `context.user_id`), `audit_logger` (denied-Scopes).

---

## Trust-Boundary (unverändert ggü. übergeordneter Spec)

- Einziger Trust-Boundary = der Host; Plugin-Prozess vollständig untrusted.
- `exec_module` läuft für externe Plugins **nie** im Host-Prozess.
- Token verlässt nie den Host — Plugin sieht nur `context {user_id, username, role}`.
- Default-deny, host-seitig am `cap_call`-Dispatch durchgesetzt (`granted_api_scopes`).
- Alle Plugin-Fehler host-seitig gescrubbt.
- *OS-Härtung (Low-Priv-User/netns) ist Phase 5* — bis dahin läuft der Subprozess als
  derselbe User; die RPC-/Capability-Grenze gilt bereits.

---

## Testing (TDD, subagent-driven wie Vorphasen)

- **Migration:** round-trip up/down; bestehende Records unverändert; default `[]`.
- **Dual-Path:** external → kein `exec_module`, Supervisor gestartet, in `_sandboxes`;
  bundled → unveränderter Pfad, in `_plugins`. disable → Supervisor gestoppt.
- **Proxy:** Auth-Gate vor Forward; `Authorization`/`Cookie` erscheinen **nie** im an
  das Plugin gesendeten `http_request` (Positiv-Assertion, analog Track-A
  `'BaluHost' in window === false`); Header-Allowlist greift; Body-Cap → 413;
  Timeout → 504; Plugin-Crash → gescrubbtes 502 (kein Internals-Leak).
- **Scope-Durchsetzung end-to-end:** nicht-gewährter Scope → `denied` + Audit-Log;
  Storage user-gebunden (Plugin kann fremden `user_id` nicht adressieren);
  Quota-Enforcement.
- **Routing-Präzedenz:** ein bundled-Plugin-Pfad wird NICHT vom Catch-all geschluckt.
- **E2E:** Beispiel-Sandbox-Plugin (eigene Route + `storage` + ein `core`-Scope) durch
  den vollen Proxy → RPC → Capability-Pfad.

---

## Explizit Out-of-Scope (Phase 4)

- **Hardened Spawn-Hook** (Low-Priv-OS-User / Netzwerk-Namespace) → Phase 5.
- **Frontend:** Doku-Update + Install-Scope-Picker-UI → Phase 5.
- **Background-Tasks / System-Event-Zustellung** für external → späteres Follow-up.
- **Streaming-Bodies** → Follow-up (v1 buffered + Cap).
- **Track C (Signing)** → orthogonaler eigener Track.

---

## Offene Punkte für den Implementierungsplan

- Genaue Verdrahtung der `metrics_reader`/`notifier`-Host-Funktionen (welcher
  bestehende Service liefert read-only Metriken bzw. die User-Notification).
- Ablage der Caps/Timeouts: `settings`-Felder vs. Konstanten im Sandbox-Modul.
- Wo der Supervisor-Lifecycle pro uvicorn-Worker aufgehängt wird (Reuse des
  `enable_plugin`-Pfads aus `load_enabled_plugins`, der bereits pro Worker läuft).
- Verhalten bei Supervisor-`disabled` (Restart-Budget erschöpft): Catch-all liefert
  503/502 + Audit; DB-`is_enabled` bleibt true (auto-disable ist laufzeit-lokal).
