Du bist ein erfahrener Python-Architekt und arbeitest am Projekt BaluHost 
(Self-hosted NAS Management Platform). Lies zunächst die bestehende 
Plugin-Infrastruktur vollständig durch, bevor du irgendetwas implementierst.

## Kontext

BaluHost hat eine ausgereifte Plugin-Infrastruktur unter:
  backend/app/plugins/
    base.py        – PluginBase, PluginMetadata, BackgroundTaskSpec, DashboardPanelSpec
    hooks.py       – Pluggy HookSpecs (25+ Hook-Punkte)
    events.py      – Async EventManager mit Queue
    manager.py     – PluginManager Singleton (Lifecycle, Routing, Tasks)
    permissions.py – PermissionManager
    emit.py        – emit_hook / emit_event Helfer

Plugins liegen unter backend/app/plugins/installed/{plugin_name}/__init__.py

## Deine Aufgabe

Plane und implementiere die folgenden drei Features. Arbeite sie NACHEINANDER ab –
schließe jedes vollständig ab (inkl. Tests) bevor du mit dem nächsten beginnst.

─────────────────────────────────────────────────────────────
FEATURE 1 – Fehlende Hook-Punkte in hooks.py ergänzen
─────────────────────────────────────────────────────────────

Füge folgende Hook-Specs zur Klasse BaluHostHookSpec in hooks.py hinzu.
Halte den bestehenden Stil (Docstring, typed Args, Sektionskommentare) exakt ein.

  # File Events (Ergänzung)
  on_file_access_denied(path, user_id, reason)
    – Wenn ein User auf eine Datei zugreift für die er keine Berechtigung hat

  # System Events (Ergänzung)  
  on_quota_exceeded(user_id, username, used_bytes, quota_bytes)
    – Wenn ein Upload die Quota eines Users überschreiten würde

  on_telemetry_snapshot(cpu_percent, ram_percent, disk_usage, timestamp)
    – Feuert bei jedem Telemetrie-Intervall (~3s); ermöglicht custom Metriken

  # Sync Events (neu)
  on_sync_conflict_detected(path, device_id, local_mtime, remote_mtime)
    – Wenn ein Sync-Konflikt erkannt wird

  on_sync_completed(device_id, files_synced, bytes_transferred, duration_seconds)
    – Nach erfolgreichem Sync-Lauf

  # Scheduler Events (neu)
  on_scheduler_run_started(scheduler_name, run_id)
    – Wenn ein Scheduler-Job startet

  on_scheduler_run_failed(scheduler_name, run_id, error, duration_seconds)
    – Wenn ein Scheduler-Job fehlschlägt

Danach: Prüfe wo im bestehenden Backend-Code die passenden Events bereits
ausgelöst werden (z.B. in api/files.py, services/telemetry*, services/sync*,
services/scheduler*) und ergänze dort die emit_hook()-Aufrufe.
Suche systematisch mit grep/glob – ändere nichts an der Geschäftslogik.

Tests: Schreibe pytest-Tests in backend/tests/test_plugin_hooks_new.py die
sicherstellen, dass jeder neue Hook korrekt gefeuert wird (Mock-Plugin Pattern
wie in bestehenden Hook-Tests verwenden).

─────────────────────────────────────────────────────────────
FEATURE 2 – Plugin Service Registry
─────────────────────────────────────────────────────────────

Erstelle backend/app/plugins/registry.py mit einer ServiceRegistry-Klasse.

Anforderungen:
- Plugins können Services (beliebige Objekte/Callables) unter einem Namen
  registrieren: registry.register("my_plugin.weather_data", my_instance)
- Andere Plugins können Services abrufen: registry.get("my_plugin.weather_data")
- Namespacing: Service-Namen müssen das Format "{plugin_name}.{service_name}"
  haben – Registry validiert dies beim Registrieren
- Beim Deaktivieren eines Plugins (disable_plugin) werden alle seine Services
  automatisch deregistriert
- registry.list_services(plugin_name=None) gibt verfügbare Services zurück
- Fehler: get() auf unbekannten Service wirft ServiceNotFoundError (eigene
  Exception), NICHT KeyError
- Thread-safe mit asyncio.Lock

Integration:
- ServiceRegistry als Singleton analog zum EventManager
- get_service_registry() Funktion in registry.py
- PluginManager.disable_plugin() ruft registry.deregister_all(plugin_name) auf
- PluginBase bekommt eine optionale Methode get_services() -> Dict[str, Any]
  die beim enable_plugin() automatisch registriert wird
- Exportiere aus plugins/__init__.py

Tests in backend/tests/test_plugin_registry.py:
  - register / get / deregister Roundtrip
  - Namespace-Validierung (falsche Namen werden abgelehnt)
  - Auto-deregister beim Plugin-Disable
  - ServiceNotFoundError bei unbekanntem Service
  - Concurrent access (mehrere asyncio Tasks gleichzeitig)

─────────────────────────────────────────────────────────────
FEATURE 3 – Plugin SDK / Scaffolding CLI
─────────────────────────────────────────────────────────────

Erstelle backend/app/plugins/sdk/ als neues Package:

  sdk/
    __init__.py
    scaffold.py    – Template-Generierung
    templates/     – Jinja2-Templates (oder pure f-strings, kein externes Tool nötig)
      plugin_init.py.tmpl
      plugin_test.py.tmpl
    validator.py   – Validiert ein bestehendes Plugin gegen die Contracts
    cli.py         – Click-basierte CLI (Click ist bereits in FastAPI-Dependencies)

CLI-Befehle (erreichbar via: python -m app.plugins.sdk):

  create <plugin_name> [--category monitoring|storage|network|security|general]
                       [--author "Name"]
                       [--with-router]        # Fügt Beispiel-APIRouter hinzu
                       [--with-background-task] # Fügt Beispiel-BackgroundTask hinzu
                       [--with-dashboard-panel] # Fügt DashboardPanelSpec hinzu
                       [--with-service]       # Fügt get_services() Beispiel hinzu

    Generiert: installed/{plugin_name}/__init__.py mit:
      - Vollständig ausgefüllter PluginMetadata
      - Gewählten Features als auskommentierte, aber funktionierende Beispiele
      - Inline-Kommentare die jeden Schritt erklären ("# Schritt 1: ...")
      - Import-Beispiel für hookimpl
      - Einem konkreten Hook-Beispiel passend zur --category

  validate <plugin_name>
    – Lädt das Plugin und prüft:
      * Metadata vollständig (name, version, author, description)
      * Alle deklarierten required_permissions existieren in PermissionManager
      * Keine zirkulären Dependencies (plugin.metadata.dependencies)
      * Falls SmartDevicePlugin: Capability Contracts (bereits vorhanden)
    – Gibt strukturierten Report aus (✅ / ⚠️ / ❌)

  list
    – Zeigt alle installed Plugins mit Status (enabled/disabled), Version, Author

Das generierte __init__.py Template soll so gestaltet sein, dass ein
Entwickler es ohne weitere Dokumentation verstehen und erweitern kann.
Kommentiere jeden Hook und jede Methode mit einem "Warum" nicht nur "Was".

Tests in backend/tests/test_plugin_sdk.py:
  - scaffold create generiert valide Python-Datei (ast.parse() schlägt nicht fehl)
  - Alle --with-* Flags produzieren den erwarteten Code
  - validate erkennt fehlerhafte Plugins korrekt
  - Idempotenz: create auf existierendes Plugin fragt nach Überschreiben

─────────────────────────────────────────────────────────────
WICHTIGE REGELN
─────────────────────────────────────────────────────────────

1. Lies vor jeder Änderung die betroffene Datei vollständig.
2. Ändere KEINE bestehende Logik – nur Ergänzungen.
3. Halte den bestehenden Code-Stil (Docstrings, Type Hints, Logger-Namen).
4. Nach jedem Feature: führe die Tests aus und behebe Fehler bevor du
   weitermachst.
5. Fasse am Ende jedes Features kurz zusammen was du geändert hast
   und welche Dateien betroffen sind.

Ein paar Hinweise zur Nutzung:
Reihenfolge ist bewusst — Feature 1 (Hooks) ist die Basis, weil Feature 3 (SDK) die neuen Hooks als Beispiele im generierten Template verwenden kann.
--with-service im SDK-Befehl setzt Feature 2 voraus — wenn du die Features auf mehrere Sessions aufteilst, sag Claude Code am Anfang der zweiten Session kurz was bereits implementiert wurde.
Für den Start: claude im backend/-Verzeichnis aufrufen, damit die relativen Pfade stimmen und Claude Code direkt auf die Dateien zugreifen kann.