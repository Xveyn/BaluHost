# BaluHost RAM Anzeige: Aufschlüsselung pro systemd-Unit

**Datum:** 2026-05-27
**Status:** Spec — pending implementation plan
**Branch:** *(neu)* `feat/memory-per-unit-breakdown`

## Problem

Der System Monitor zeigt einen einzelnen RAM-Wert für "BaluHost" (`MemoryTab.tsx:68-73`). Hinter dem Wert steht `get_baluhost_memory_bytes()` (`backend/app/services/monitoring/memory_collector.py:23`), das `psutil.process_iter` durchläuft und RSS aller Prozesse summiert, deren Name oder cmdline einem der Patterns in `BALUHOST_PROCESS_PATTERNS` entspricht (`backend/app/services/monitoring/process_tracker.py:25`):

```python
BALUHOST_PROCESS_PATTERNS = [
    {"name": "baluhost-backend",  "patterns": ["uvicorn", "app.main"]},
    {"name": "baluhost-frontend", "patterns": ["node", "vite"]},
    {"name": "baluhost-tui",      "patterns": ["baluhost-tui", "baluhost_tui"]},
]
```

In Production läuft BaluHost als **fünf separate systemd-Units**:

| Unit | ExecStart | Aktuell erfasst? |
|---|---|---|
| `baluhost-backend.service` | `uvicorn app.main:app --workers 4` (1 Master + 4 Worker) | ✓ via `"uvicorn"` |
| `baluhost-backend-local.service` | `uvicorn app.main:app --fd 3 --workers 2` (1 Master + 2 Worker, Unix-Socket) | ✓ via `"uvicorn"`, aber **als Backend-Topf**, nicht separat |
| `baluhost-scheduler.service` | `python scripts/scheduler_worker.py` | ✗ kein Pattern matcht |
| `baluhost-webdav.service` | `python scripts/webdav_worker.py` | ✗ kein Pattern matcht |
| `baluhost-monitoring.service` | `python scripts/monitoring_worker.py` | ✗ kein Pattern matcht |

Daraus folgen drei konkrete Defekte:

1. **3 von 5 Units fehlen in der Gesamtsumme** — Scheduler, WebDAV und Monitoring-Worker tauchen im "BaluHost"-Wert gar nicht auf.
2. **Pattern `"node"` ist Substring-fragil** — In Production läuft kein Vite/Node; auf Dev-Boxen kann `"node"` an beliebige unrelated Node-Prozesse anschlagen.
3. **Keine Aufschlüsselung** — `MemorySampleSchema` hat nur ein Feld `baluhost_memory_bytes: int`. Die UI hat keine Möglichkeit, "wo geht das RAM eigentlich hin" zu beantworten.

## Goal

Die "BaluHost"-RAM-Anzeige zeigt:
- Eine korrekte **Gesamtsumme** über alle BaluHost-Prozesse (inklusive Scheduler/WebDAV/Monitoring).
- Eine **Aufschlüsselung pro systemd-Unit**:
  - `baluhost-backend` — aggregiert über Master + 4 Worker
  - `baluhost-backend-local` — eigene Zeile (separat von `baluhost-backend`)
  - `baluhost-scheduler`
  - `baluhost-webdav`
  - `baluhost-monitoring`
  - `baluhost-tui` (nur wenn präsent)
  - `baluhost-frontend-dev` (nur Dev-Modus)

## Non-Goals

- **Per-Worker-Drill-down** (welcher der 4 Uvicorn-Worker wie viel) — vertagt. `process_samples` speichert pro PID, der Daten-Pfad ist da; nur UI fehlt.
- **cgroup-basierte Erkennung** (Hybrid-Ansatz aus dem Brainstorm) — vertagt. cmdline-Patterns reichen, solange Units immer per systemd oder `start_dev.py`/`start_prod.py` gestartet werden.
- **Postgres-/Nginx-/Redis-RAM** — sind keine BaluHost-Prozesse; gehört in eine eigene "Stack View" wenn überhaupt.
- **Migration auf JSON-Spalte in `memory_samples`** — Historie pro Unit lebt schon in `process_samples` (existierende Tabelle); keine zusätzliche Migration nötig.

## Approach

**Ansatz A** aus dem Brainstorm: cmdline-Patterns präzisieren und erweitern. Begründung:
- Cross-platform (Windows-Dev läuft auch ohne systemd).
- Minimal-invasiv: die `ProcessTracker`-Pipeline existiert, schreibt schon pro `process_name` in `process_samples`.
- Die ExecStart-Strings sind eindeutig genug (`scheduler_worker.py`, `webdav_worker.py`, `monitoring_worker.py`, `uvicorn app.main`), dass Substring-Matching robust ist.
- cgroup-Hybrid kann später nachgezogen werden ohne API-Bruch.

### Unterscheidung `baluhost-backend` vs. `baluhost-backend-local`

Beide laufen mit `uvicorn app.main:app`. Unterscheidungsmerkmal in cmdline:
- **Backend (HTTP)**: `--host 0.0.0.0 --port 8000 --workers 4`
- **Backend-Local (Unix-Socket)**: `--fd 3 --workers 2` und Env `BALUHOST_CHANNEL=local`

Patterns müssen also Backend-Local **zuerst** matchen (z. B. via `"--fd 3"`), damit nicht beides in den `baluhost-backend`-Topf fällt.

## Components

### Backend

#### `process_tracker.py` — Pattern-Definition

`BALUHOST_PROCESS_PATTERNS` wird zu einer geordneten Liste, in der spezifischere Einträge zuerst stehen. Erste Übereinstimmung gewinnt — Prozesse werden nicht doppelt gezählt.

```python
BALUHOST_PROCESS_PATTERNS = [
    # Order matters: more-specific patterns first.
    {"name": "baluhost-backend-local",  "patterns": ["uvicorn app.main", "--fd 3"]},       # both must match
    {"name": "baluhost-backend",        "patterns": ["uvicorn app.main"]},                 # remaining uvicorn procs
    {"name": "baluhost-scheduler",      "patterns": ["scheduler_worker.py"]},
    {"name": "baluhost-webdav",         "patterns": ["webdav_worker.py"]},
    {"name": "baluhost-monitoring",     "patterns": ["monitoring_worker.py"]},
    {"name": "baluhost-tui",            "patterns": ["baluhost_tui"]},
    {"name": "baluhost-frontend-dev",   "patterns": ["vite"]},                              # dev only; "node" alone removed
]
```

**Match-Semantik-Änderung**: Bisher war `patterns` ein "any-of" (jeder Substring-Treffer reicht). Für `baluhost-backend-local` brauchen wir **all-of**, damit `--fd 3` zusätzlich zu `uvicorn app.main` matchen muss. Anpassung in `_find_processes()` und `get_baluhost_memory_bytes()`:

```python
def _matches(cmdline: str, name: str, patterns: list[str]) -> bool:
    return all(p.lower() in name or p.lower() in cmdline for p in patterns)
```

(Bisher `any(...)`. Alle bestehenden Patterns sind ein-elementige Listen, also Verhalten identisch — bis auf Backend-Local.)

**First-match-wins**: In der Sammel-Schleife durch `BALUHOST_PROCESS_PATTERNS` wird ein PID, der für `baluhost-backend-local` gematcht hat, beim `baluhost-backend`-Pattern übersprungen. Implementierung: pro PID nach erstem Match `break`, dann zur nächsten PID — also Match-Schleife pro Prozess, nicht pro Pattern.

#### `memory_collector.py` — Aufschlüsselung

`get_baluhost_memory_bytes()` wird zu `get_baluhost_memory_breakdown() -> dict[str, int]`:

```python
def get_baluhost_memory_breakdown() -> dict[str, int]:
    """RSS bytes pro process_name. Keys aus BALUHOST_PROCESS_PATTERNS."""
    breakdown: dict[str, int] = {entry["name"]: 0 for entry in BALUHOST_PROCESS_PATTERNS}
    for proc in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
        # match in first-wins order, accumulate RSS in breakdown[name]
        ...
    return breakdown
```

`MemoryMetricCollector.collect_sample()` ruft das auf und schreibt:
- `baluhost_memory_breakdown` (neues Feld) — komplette Aufschlüsselung
- `baluhost_memory_bytes` (bestehend) — `sum(breakdown.values())` für Backward-Compat

Units mit `0` Bytes (Prozess nicht gefunden) bleiben im Dict mit Wert `0`. Das ist absichtlich: der Konsument sieht den Unterschied zwischen "Unit nicht definiert" (Key fehlt) und "Unit läuft gerade nicht" (Key da, Wert 0).

#### `schemas/monitoring.py` — Schema-Erweiterung

```python
class MemorySampleSchema(BaseModel):
    timestamp: datetime
    used_bytes: int
    total_bytes: int
    percent: float
    available_bytes: int
    baluhost_memory_bytes: int  # Gesamtsumme (Backward-Compat)
    baluhost_memory_breakdown: Optional[Dict[str, int]] = None  # NEU
```

`Optional`, weil ältere DB-Rows das Feld nicht haben (s. nächster Punkt).

#### Persistenz

Zwei Optionen:

| Option | Beschreibung | Empfehlung |
|---|---|---|
| **Live-only** | Breakdown nur im API-Response (`/api/monitoring/memory/current`), nicht in `memory_samples` persistiert | ✓ |
| **In DB-Spalte (JSON)** | Neue Spalte `memory_samples.baluhost_breakdown JSONB` + Alembic-Migration | ✗ |

**Empfehlung: Live-only.** Die Historie pro Unit lebt bereits in `process_samples` (über `ProcessTracker`), das ist die natürliche Quelle für Zeitreihen. Doppeltes Schreiben wäre Redundanz. `MemorySample.baluhost_memory_bytes` (Gesamtsumme) bleibt persistent — das ist die Series, die auf der Memory-Chart als zweite Linie liegt.

#### API-Route — Process-History

Das Frontend braucht eine Endpoint, um pro Unit eine RAM-History zu plotten. Existiert vermutlich schon (`orchestrator.get_process_history()` ist da). Wenn nicht direkt unter `/api/monitoring/processes`, dann hinzufügen:

```
GET /api/monitoring/processes/history?process_name=baluhost-backend&minutes=10
→ List[ProcessSampleSchema]
```

Mit DB-Fallback (siehe `ProcessTracker.get_history_db()`).

**Zu prüfen während der Implementation**: ob die Route schon existiert. Falls ja, nur konsumieren; falls nein, hinzufügen.

### Frontend

#### `api/monitoring.ts` — Type-Erweiterung

```ts
export interface MemorySample {
  timestamp: string;
  used_bytes: number;
  total_bytes: number;
  percent: number;
  available_bytes: number;
  baluhost_memory_bytes: number;
  baluhost_memory_breakdown?: Record<string, number>;  // NEU
}
```

#### `MemoryTab.tsx` — UI-Änderungen

Aktuell (`MemoryTab.tsx:42-74`): fünf StatCards (Used, Total, Available, Utilization, BaluHost). Die "BaluHost"-StatCard wird ersetzt durch eine **kompaktere Komponente** mit Drill-down:

```
┌─────────────────────────────────┐
│ 🏠 BaluHost            842 MB   │
├─────────────────────────────────┤
│  Backend (HTTP)         612 MB  │   ← aggregiert: Master + 4 Worker
│  Backend (Local)        180 MB  │   ← Unix-Socket Channel
│  Scheduler               24 MB  │
│  WebDAV                  18 MB  │
│  Monitoring               8 MB  │
└─────────────────────────────────┘
```

Layout-Entscheidung: die Aufschlüsselung ersetzt nicht die "Total"/"Used"-StatCards, sondern nimmt deren Slot (5. Karte). Bei `width < sm` klappbar (default zu) damit das Grid auf Mobile nicht überquillt.

**Translation-Keys** (`client/src/i18n/locales/{en,de}/system.json`):
- `monitor.baluhostBreakdown` — Header "BaluHost Breakdown"
- `monitor.units.backend` — "Backend (HTTP)"
- `monitor.units.backend-local` — "Backend (Local)"
- `monitor.units.scheduler`, `.webdav`, `.monitoring`, `.tui`, `.frontend-dev`

Mapping `process_name → translation-key` zentral in einer Konstante:
```ts
const UNIT_LABELS: Record<string, string> = {
  "baluhost-backend":       "monitor.units.backend",
  "baluhost-backend-local": "monitor.units.backend-local",
  "baluhost-scheduler":     "monitor.units.scheduler",
  // ...
};
```

#### Chart-Erweiterung — vertagt im Rahmen dieser Spec

Das Chart in `MemoryTab.tsx:77-94` bleibt vorerst zweispurig (System Used + BaluHost Total). Per-Unit-Stacked-Area wäre ein eigenes Feature mit Historien-Pull aus `process_samples` — dafür braucht es die Process-History-Route + neue Hook + Chart-Anpassung. Falls die Route schon existiert, kann das in einer **Stretch-Task** mitgehen; sonst separates Folge-Ticket.

## Data Flow

```
psutil.process_iter()
  └─→ ProcessTracker.collect_samples()      ← pro PID + process_name (DB-persistent in process_samples)
  └─→ get_baluhost_memory_breakdown()       ← {unit_name: total_rss_bytes}
                                            ↓
                          MemorySampleSchema.baluhost_memory_breakdown
                                            ↓
                          GET /api/monitoring/memory/current
                                            ↓
                                  MemoryTab.tsx → Breakdown-Card
```

## Error Handling

- `psutil.NoSuchProcess` / `psutil.AccessDenied` während Iteration: skip, bestehende Logik (`memory_collector.py:45`) bleibt.
- Wenn alle Patterns 0 Bytes ergeben (z. B. Tests, frisch gebooteter Container): Breakdown-Dict mit allen Keys auf 0, Total = 0. UI zeigt dann "—" oder Nullzeile.
- DB-Row ohne `baluhost_memory_breakdown` (historisch persistierte Samples gibt's nicht — Live-only — also nur möglich, falls jemand zwischenzeitlich Persistierung nachzieht): Feld ist `Optional`, Frontend zeigt nur Gesamtsumme.

## Testing

### Unit Tests
- `tests/services/monitoring/test_process_tracker.py`:
  - Pattern `baluhost-backend-local` matcht nur cmdline mit *beiden* `uvicorn app.main` und `--fd 3`.
  - First-match-wins: ein Mock-Prozess mit cmdline `uvicorn app.main --fd 3` landet in `baluhost-backend-local`, **nicht** in `baluhost-backend`.
  - Mock-Prozess mit `scheduler_worker.py` landet in `baluhost-scheduler`.
- `tests/services/monitoring/test_memory_collector.py`:
  - `get_baluhost_memory_breakdown()` liefert ein Dict mit allen `BALUHOST_PROCESS_PATTERNS`-Keys.
  - Gesamtsumme = sum(breakdown.values()).
  - Backward-Compat: `MemorySampleSchema.baluhost_memory_bytes` weiterhin gefüllt.

### Integration Test
- `tests/api/test_monitoring.py`:
  - `GET /api/monitoring/memory/current` enthält `baluhost_memory_breakdown` mit erwarteten Keys.

### Manual / Production Smoke
Nach Deploy auf BaluNode:
```bash
curl -s -H "Authorization: Bearer <token>" http://localhost/api/monitoring/memory/current | jq '.baluhost_memory_breakdown'
# Erwartet: alle 5 prod-Units mit nicht-null RSS
```

## Files to Modify

### Backend
- `backend/app/services/monitoring/process_tracker.py` — `BALUHOST_PROCESS_PATTERNS` erweitern, `_find_processes()` auf `all(...)` umstellen, first-match-wins in `collect_samples()`
- `backend/app/services/monitoring/memory_collector.py` — `get_baluhost_memory_bytes()` → `get_baluhost_memory_breakdown()`, Sample befüllen
- `backend/app/schemas/monitoring.py` — `MemorySampleSchema.baluhost_memory_breakdown` hinzufügen
- `backend/tests/services/monitoring/test_process_tracker.py` — neue/erweiterte Tests
- `backend/tests/services/monitoring/test_memory_collector.py` — neue/erweiterte Tests

### Frontend
- `client/src/api/monitoring.ts` — `MemorySample.baluhost_memory_breakdown` Type
- `client/src/components/system-monitor/MemoryTab.tsx` — Breakdown-Card statt einfacher StatCard
- `client/src/i18n/locales/en/system.json` — neue Keys
- `client/src/i18n/locales/de/system.json` — neue Keys

### Optional (sofern Route nicht schon existiert)
- `backend/app/api/routes/monitoring.py` — `/processes/history?process_name=...` Endpoint hinzufügen

## Open Verifications Before Implementation

- [ ] Existiert `/api/monitoring/processes/history` schon? (für späteren Per-Unit-Chart)
- [ ] Wo wird `MemoryMetricCollector` instanziiert (lifespan? monitoring worker?) — sicherstellen, dass `BALUHOST_PROCESS_PATTERNS`-Erweiterung dort durchschlägt
- [ ] In welchem Worker läuft die Memory-Collection? Wenn nur Monitoring-Worker, sieht der seinen eigenen `monitoring_worker.py` korrekt
