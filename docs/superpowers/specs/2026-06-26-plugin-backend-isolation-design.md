# Plugin-Backend-Isolation (Plugin-Sandboxing Track B) — Design

- **Datum:** 2026-06-26
- **Status:** Design / Spec (Brainstorm abgeschlossen, vor Implementierungsplan)
- **Track:** Plugin-Sandboxing **Track B** aus dem Security-Audit 2026-06-14
  (`SECURITY_AUDIT_2026-06-14.md`). Track A (Frontend-iframe-Isolation) ist
  abgeschlossen (PR #278/#279); Track C (Supply-Chain-Signing) ist orthogonal
  und nicht Teil dieser Spec.
- **Verwandt:** `docs/superpowers/specs/2026-06-22-plugin-frontend-iframe-sandbox-design.md`,
  `docs/superpowers/specs/2026-06-24-plugin-sandbox-phase3-5-design.md`

---

## Problem

Externe (Marketplace-)Plugins laufen heute mit **vollem In-Process-RCE** im
Backend-Prozess. Der Kern ist `app/plugins/manager.py` (`load_plugin`):

```python
module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = module
spec.loader.exec_module(module)   # führt beliebigen Plugin-Code im Host-Prozess aus
```

Konkrete Konsequenzen:

- **Laden = Code-Ausführung.** Schon `exec_module` führt Modul-Ebenen-Code aus —
  ein bösartiges Plugin braucht keinen Route-Call (`import os; os.system(...)` reicht).
- **Eigene Deps in-process.** Externe Plugins prependen ihr `site-packages/` auf
  `sys.path` (`manager.py`), d.h. auch transitive Supply-Chain läuft im Host.
- **Plugin-Router ist gleichberechtigter FastAPI-Code** (`manager.py` `get_router()`):
  bekommt die echte `db`-Session, `Depends(get_current_user)`, importiert Host-Services
  frei, ruft `subprocess`.
- **Background-Tasks** sind `asyncio.create_task` im Host-Event-Loop.
- **Permissions sind rein deklarativ.** `PermissionManager.validate_permissions`
  prüft beim Enable nur `granted ⊇ required`. Zur Laufzeit gibt es **keinerlei**
  Durchsetzung — ein Plugin ohne `system:execute` kann trotzdem `subprocess` aufrufen.

Das ist exakt die im Audit als letzte große offene Schwachstelle geführte Backend-Lücke.

## Ziel & Scope

**Externe/Marketplace-Plugins** laufen isoliert in einem unprivilegierten
Subprozess; der Host vermittelt jeden Zugriff über eine default-deny RPC-Grenze.

**Bundled-Plugins bleiben unverändert in-process** (First-Party, trusted). Diese
Spec ändert ihren Pfad nicht.

Greenfield-Annahme: aktuell sind **null** externe Plugins deployed
(Repo enthält nur `app/plugins/installed/` = bundled). Es gibt nichts zu
migrieren — reines proaktives Härten „bevor das Ökosystem wächst".

## Entscheidungen (aus dem Brainstorm)

| Frage | Entscheidung |
|---|---|
| Welche Plugins isolieren? | **Nur external/Marketplace.** Bundled bleiben in-process trusted. |
| Isolations-Mechanismus | **Subprozess als Low-Priv-OS-User** + UDS-RPC (spiegelt CI-Sandbox Layer A). Kein Container-Zwang; härtere Stufe später einsteckbar. |
| Request-Pfad | **Ansatz A — Host-Proxy + RPC-Forward.** Host validiert Auth/Gating, schickt kuratierten, **token-freien** Request über RPC. |
| Capabilities (default-deny) | **Per-User KV-Storage**, **eigene Plugin-Routen**, **kuratierte Core-API-Scopes**. **Kein** Outbound-Netz, **kein** Raw-DB/FS/Shell. |

---

## Architektur

### Komponenten

```
Host-Prozess (Uvicorn-Worker, trusted)
├── PluginManager                 # dual-path: bundled in-process | external → SandboxedPlugin
├── SandboxSupervisor             # spawn/health/restart/kill der Worker (nur Primary-Worker)
├── PluginProxyRouter             # FastAPI catch-all /api/plugins/{name}/{path}
├── RpcChannel (Host-Seite)       # UDS, msgpack-Framing, voll-duplex, pending-map
└── CapabilityRouter              # default-deny Dispatch von cap_call → schmale Host-Handler
                                  #   storage.*  |  core.*  (fester Katalog)

Sandbox-Worker (Subprozess, untrusted, Low-Priv-User, kein Netz)
├── plugin_host_runner            # Entry-Point: UDS verbinden, RPC-Loop
├── RpcChannel (Plugin-Seite)     # spiegelbildlich
├── Plugin-SDK                    # host.storage.*, host.scopes.*, Routen-Registry
└── <external plugin __init__.py> # exec NUR hier, nie im Host
```

### Prozess-Topologie & Lifecycle

- **Dual-Path im `PluginManager`.** `load_plugin`/`enable_plugin` verzweigen anhand
  `DiscoveredPlugin.source` (`manager.py`):
  - `bundled` → unveränderter `exec_module`-Pfad.
  - `external` → **nie** `exec_module` im Host; `SandboxSupervisor` spawnt einen Worker.
- **Ein Prozess pro externem Plugin** (kein geteilter Pool): eigene `site-packages/`,
  Blast-Radius-Isolation (kein Quer-Zugriff zwischen Plugins), Crash-Isolation.
- **Worker-Eigenschaften** (gespiegelt von CI-Sandbox Layer A):
  - dedizierter unprivilegierter OS-User (z.B. `baluhost-plugin`): kein sudo, keine
    Gruppen, kein Lesezugriff auf `/opt/baluhost`, `.env.production`, Storage-Root.
  - **Kein Netzwerk-Egress** (Netzwerk-Namespace / `unshare -n` bzw. Egress-Drop) —
    UDS zum Host ist der einzige Kanal nach außen.
  - Working-Dir = nur das Plugin-Verzeichnis.
  - Optional als Härtung: `rlimit`/cgroup (CPU/Mem) beim Spawn.
- **Multi-Worker (4 Uvicorn-Worker in prod):**
  - Worker-Spawn + UDS-Ownership liegen **nur beim Primary-Worker** — exakt analog
    zum bestehenden `start_background_tasks=False`-Muster auf Secondary-Workern
    (`manager.py`).
  - `PluginProxyRouter` läuft auf **jedem** Uvicorn-Worker und connectet zum geteilten UDS.
  - `enable` → spawn + Health-Handshake; `disable` → graceful `shutdown`-RPC, dann
    SIGTERM→SIGKILL mit Timeout; **Crash-Supervision** → bounded Restart
    (max N Restarts/Fenster, sonst auto-disable + Audit-Log).

### RPC-Protokoll

- **Transport:** Längen-präfixierte Frames über UDS. Payload-Encoding **msgpack**
  (native `bytes` → keine base64-Aufblähung für Bodies/Uploads). Frame =
  `4-Byte-Length` + msgpack-Envelope.
- **Voll-Duplex, reentrant, Correlation-IDs.** Während der Host auf die
  `http_response` wartet, kann das Plugin `cap_call`s zurücksenden. Beide Seiten
  halten eine `pending`-Map `{id → Future}`. Envelope: `{ id, type, ... }`.
  - Host → Plugin: `http_request`, `lifecycle` (startup / health-ping / shutdown)
  - Plugin → Host: `cap_call` → vom Host beantwortet mit `cap_result`
  - Antworten: `http_response`, `cap_result`, `error`

**Request-Contract (Ansatz A — kuratiert, Token bleibt im Host):**

```
http_request {
  id, method, path,            # path = Subpfad NACH /plugins/{name}/
  query: {str: str},
  headers: {…},                # ALLOWLIST (content-type, accept, …)
                               #   NIE Authorization / Cookie
  body: bytes,
  context: { user_id, username, role }   # vom Host aufgelöst, KEIN Token
}
http_response { id, status, headers (allowlist), body: bytes }
```

**Error-Handling & Limits** (schließt an Posten 2 / Error-Leakage an):

- Plugin wirft/crasht im Request → Host liefert **gescrubbtes** 502/500; Detail nur
  server-side geloggt, nie an den Client.
- **Per-Request-Timeout** → 504, Request abgebrochen; wiederholte Timeouts zählen
  auf das Crash-Budget.
- **Body-Size-Cap** (Request & Response) + **max in-flight Requests/Plugin** → DoS-Schutz.
- Malformed Frame → Connection-Drop + Supervisor-Restart.

### Capability-Layer (default-deny)

Jeder `cap_call {capability, request_id, args}` läuft host-seitig durch den
`CapabilityRouter`:

1. `capability ∈ granted_scopes`? Nein → `cap_result{error:"denied"}` + Audit-Log.
   **Das ist die eigentliche Sandbox-Durchsetzung** (ersetzt die deklarative Prüfung).
2. Ja → schmaler, validierter Host-Handler läuft mit Host-Rechten, gibt nur das
   kuratierte Ergebnis zurück.

**a) `storage.*` — Per-User KV** (reuse Track A `plugin_storage`, PR #279):
`get/set/delete/list`, gebunden an `(plugin, user_id)`. Der `user_id` kommt **nicht**
vom Plugin, sondern aus dem `context` des `request_id`, auf den sich der `cap_call`
bezieht — der Host korreliert, welchen In-Flight-Request das Plugin gerade bedient.
Ein Plugin kann so nie fremde User-Buckets adressieren. Quota: 64 KB / 100 keys
(bestehender Service).

**b) Eigene Routen** — kein Capability-Call, sondern der `http_request`-Pfad. Frei
nutzbar (Plugin-Hauptzweck), immer hinter Host-Auth/Gating.

**c) `core.*` — kuratierte Core-API-Scopes.** Fester, kleiner Katalog; jeder Scope =
eine **enge** Host-Funktion (z.B. read-only Systemmetriken, Notification senden).
**Kein** roher DB-/Shell-Zugriff. Katalog erweitern = Host-Code-Änderung + Review.
Der Start-Katalog wird im Implementierungsplan festgelegt (minimal halten; YAGNI).

**Single Source of Truth = `granted_api_scopes`** (DB `InstalledPlugin`,
bereits vorhanden) — **dieselbe** Spalte, die Track A fürs Frontend-Gating nutzt.
Backend-Cap-Gating und Frontend-Bridge-Gating teilen denselben Scope-Satz, vom Admin
bei Install gewährt.

**Plugin-SDK (im Sandbox-Prozess):** dünnes Python-SDK, das RPC-Calls zu einer
sauberen API wrappt — `host.storage.get(key)`, `host.scopes.system_metrics()`, plus
Routen-Registrierung — analog zu `window.BaluHost` im Frontend. Plugin-Autor schreibt
nie rohes msgpack.

**Permission-Modell-Aufräumung:** Die alte `PluginPermission`-Enum (`file:*`,
`system:execute`, `db:*`) bleibt für **bundled** Plugins (dort informativ). Für
**external** Plugins ist die gewährbare Menge ausschließlich der Scope-Katalog; die
gefährlichen Raw-Permissions sind nicht installierbar.

---

## Trust-Boundary (Invarianten)

- **Einziger Trust-Boundary = der Host.** Der Plugin-Prozess ist vollständig untrusted.
- `exec_module` läuft für externe Plugins **nie** im Host-Prozess.
- OS: Low-Priv-User, kein sudo, kein Lesezugriff auf Prod-Secrets/Storage-Root.
- **Kein Netzwerk-Egress**; UDS zum Host ist der einzige Außen-Kanal.
- **Token verlässt nie den Host** — Plugin sieht nur `context {user_id, role}`.
- **Default-deny**, host-seitig am `cap_call`-Dispatch durchgesetzt.
- **Alle Plugin-Fehler werden host-seitig gescrubbt** (kein Internals-Leak).

**Dokumentierter Accepted Risk** (analog CI-Gap #2): Subprozess teilt den Host-Kernel;
ein Kernel-/Namespace-Escape landet als Low-Priv-User — weiterhin ohne sudo/Prod-Zugriff.
Härtere Stufe (Container/gVisor) bleibt einsteckbares Backend an derselben RPC-Grenze.

## Explizit Out-of-Scope (v1)

- **Bundled-Plugin-Isolation** — bleiben in-process trusted.
- **Outbound-Netzwerk für Plugins** — gesperrt; spätere Lockerung nur via
  Egress-Allowlist (wie CI-Gap #8).
- **System-Event/Hook-Zustellung über die Grenze** (`on_file_uploaded` etc.) —
  Host→Plugin-Event-Push ist Follow-up; v1-External-Plugins abonnieren keine
  Core-Events. (Plugin-interne Periodik im eigenen Prozess geht trivial.)
- **Direkter DB-Zugriff / eigene Plugin-Tabellen** für external — nur KV-Storage +
  kuratierte Scopes. Reicht das nicht, ist das ein neuer kuratierter Scope (Review),
  kein Raw-DB.
- **Track C (Signing)** — orthogonaler eigener Track.
- **Migration bestehender external Plugins** — Greenfield (0 deployed).

---

## Testing

- **RPC-Unit-Tests:** Framing/Envelope-Roundtrip (msgpack), Correlation-ID-Matching,
  reentrante `cap_call` während offenem `http_request`, malformed-Frame-Drop.
- **CapabilityRouter:** default-deny (nicht-gewährter Scope → `denied` + Audit),
  Storage-User-Bindung (Plugin kann fremden `user_id` nicht adressieren), Quota-Enforcement.
- **Request-Proxy:** Host-Auth/Gating vor Forward; Token/Authorization-Header erscheinen
  **nie** im an das Plugin gesendeten `http_request` (positiv-Assertion wie Track-A
  `'BaluHost' in window === false`); Header-Allowlist greift.
- **Error-Scrubbing:** Plugin-Exception → gescrubbte 5xx an den Client, kein Internals-Leak
  (verknüpft mit Posten-2-Tests).
- **Lifecycle/Supervisor:** spawn→health→ready, graceful + hard kill, bounded Restart →
  auto-disable nach Budget, Primary-only-Spawn (Secondary-Worker spawnt nicht).
- **Isolations-Smoke-Test:** ein Test-„böses" Plugin, das `subprocess`/`open('/etc/..')`/
  Outbound-Socket versucht → scheitert (kein Zugriff), Host bleibt unbeeinträchtigt.
- **End-to-End:** ein Beispiel-Sandbox-Plugin (eigene Route + Storage + ein Core-Scope)
  durch den vollen Proxy→RPC→Capability-Pfad.

## Offene Punkte für den Implementierungsplan

- Konkreter Start-Katalog der `core.*`-Scopes (minimal).
- Genauer OS-User-Provisioning-Schritt (deploy-Template / sudoers-frei), Netzwerk-Namespace-Mechanik
  (`unshare -n` vs. spawn-Wrapper), Windows-Dev-Fallback (Subprozess ohne Low-Priv-User/Namespace
  im Dev-Mode — Isolation nur in prod erzwungen, Dev simuliert).
- Streaming-Bodies (große Up-/Downloads) über RPC: v1 buffered mit Body-Cap; Streaming als
  Follow-up falls nötig.
- Health-/Readiness-Protokolldetails und Restart-Budget-Parameter.
