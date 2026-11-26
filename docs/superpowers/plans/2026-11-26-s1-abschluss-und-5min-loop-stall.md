# S1-Abschluss (#300) und 5-Minuten-Stillstand des Event-Loops — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** #300 mit einer kleinen, risikoarmen Änderung abschließen statt mit dem 300-Handler-Sweep, den 5-Minuten-Stillstand aller Backend-Worker beseitigen (#872) und die Power-Demands des Schedulers reparieren, die heute immer mit 401 scheitern und dabei den Soft-Sleep beenden.

**Architecture:** Drei unabhängige Teile, drei PRs. **Teil A** schreibt die Regel richtig, die das Muster erzeugt hat, sperrt es per AST-Wächter mit schrumpfender Ausnahmeliste und stellt die DB-lastigen Monitoring-GETs auf `def` (Threadpool). **Teil B** behebt den periodischen Stillstand, der in der Messung vom 2026-11-26 die größte verbleibende Lag-Quelle ist. **Teil C** ersetzt den HTTP-Loopback des Schedulers durch direktes Schreiben in `power_demands`, sorgt dafür, dass der primäre Worker fremd geschriebene Demands auch anwendet, und hält die Suspend-Eskalation an, solange ein Scheduler-Job läuft.

**Tech Stack:** Python 3.13, FastAPI 0.135.1 / Starlette 0.52.1 / slowapi 0.1.9 (Prod-venv `/opt/baluhost/backend/.venv`; Dev-venv: 0.141.1 / 1.6.0 / 0.1.10 — sync-Handler mit Limiter verhalten sich in beiden gleich), SQLAlchemy 2.0, pytest (`asyncio_mode = "auto"`), PostgreSQL 17.

**Spec:** `docs/superpowers/specs/2026-07-30-s1-sync-sqlalchemy-event-loop-design.md` (Teil A weicht bewusst davon ab, siehe „Entscheidung"). Für Teil B und C gibt es keinen Spec; die Befunde stehen jeweils unter „Messung"/„Befund". Teil C folgt dem Prinzip aus `docs/superpowers/specs/2026-04-02-sleep-aware-sync-design.md`: automatische Vorgänge wecken das NAS nicht, manuelle schon.
**Issues:** [#300](https://github.com/Xveyn/BaluHost/issues/300) (Teil A, wird geschlossen), [#872](https://github.com/Xveyn/BaluHost/issues/872) (Teil B), Teil C ohne eigenes Issue (Bezug [#314](https://github.com/Xveyn/BaluHost/issues/314), dort als „HTTP-Loopback, fragil" erfasst), Bezug [#797](https://github.com/Xveyn/BaluHost/issues/797)

## Entscheidung (warum kein Sweep)

Sondendaten 2026-11-13 bis 2026-11-26 (24.242 Minutenfenster, nach #816):

- `req_in_flight_max` = 0 in 90 % der Fenster, ≤ 1 in 99,1 %, Maximum 14. Gleichzeitigkeit nach Little's Law höchstens 0,5.
- `pool_saturation_events` 0, `threadpool_waiting_max` 0, `pool_in_use_max` höchstens 10 von 30.
- Keine Lag-Spitze lässt sich einem Handler zuordnen; der einzige Kandidat (2026-11-18 19:00, 7,5-s-Request + 4,4 s Lag) war ein Resume aus dem Suspend.
- `loop_lag_p95` des primären Workers 0,9–1,1 ms (Oktober: ~53 ms, behoben durch #796/#807/#816).

Der Spec verlangt als Abnahme einen Vorher/Nachher-Vergleich des Loop-Lags. Den kann der Sweep nicht liefern, weil kaum Requests gleichzeitig laufen. Seine Risiken (147 schreibende Handler mit erstmals echter Nebenläufigkeit, 4 × 30 Verbindungen gegen `max_connections` 100, parallele SQLite-Schreiber im Dev-Modus, `requires_power` dual-mode) blieben. Teil A übernimmt deshalb nur die Spec-Etappen A (Wächter) und E (Konvention) und aus B die Monitoring-GETs.

## Global Constraints

- **Tests laufen aus `backend/`**: `cd backend && python -m pytest …`; Ruff: `cd backend && python -m ruff check app tests` (CI bricht bei F401 vor pytest ab).
- **Auf BaluNode (Prod-Box) nur in der Sandbox testen** — siehe Projekt-Memory „Prod-Box: kein sudo, pytest nur in Sandbox".
- **Kein Verhaltenswechsel an Antworten.** Statuscodes, Schemas und Rate-Limits der geänderten Routen bleiben gleich. Einzige Ausnahme: Task C3 (Auth der Demand-Routen, dort aufgelistet).
- **Kein `shell=True`, keine neuen sudoers-Regeln, keine neuen Abhängigkeiten.**
- **Ein PR je Teil**, je von `main` abgezweigt; Teil A: `refactor/s1-close-out`, Teil B: `fix/loop-stall-5min`, Teil C: `fix/scheduler-power-demands`.
- **Sprache der Doku-Dateien beibehalten**: `.claude/rules/backend/coding-style.md`, `backend/app/api/CLAUDE.md`, `backend/app/core/CLAUDE.md` sind englisch, Spec und Plan deutsch.

## Review Focus

1. **Neuer Handler mit `Annotated[Session, Depends(get_db)]`** — heute nicht im Code, aber der Wächter muss ihn genauso fangen wie `= Depends(get_db)`. Test: Task A1, Fall `annotated`.
2. **`await` nur in einer verschachtelten Funktion** — zählt nicht als eigenes `await`, der Handler blockiert trotzdem. Test: Task A1, Fall `nested_await_only`.
3. **WebSocket-Handler mit `Depends(get_db)`** — muss `async def` bleiben und darf nicht gemeldet werden. Test: Task A1, Fall `ws`.
4. **Rate-Limit auf einem sync-Handler** — `@user_limiter.limit` muss nach der Umstellung weiter greifen und `request`/`response` bekommen. Präzedenz: `api/routes/admin_db.py` (sync `def` mit Limiter). Test: Task A2 lässt die bestehenden Monitoring-Routentests unverändert laufen.
5. **Monitoring-Puffer aus einem Threadpool-Thread gelesen** — kein Risiko, solange die Collector nicht im API-Prozess laufen: in Dev wie Prod läuft das Monitoring im eigenen Prozess (`start_dev.py` startet `scripts/monitoring_worker.py`; `lifespan.py`: „Monitoring managed by monitoring_worker process"), die Puffer der API-Prozesse werden also nie nebenläufig verändert. `get_all_disk_histories()` iteriert ein dict auf Python-Ebene und wäre racy, falls das je anders wird — nicht in diesem Plan ändern, nur wissen.
6. **Admin startet den Health-Monitor im Dashboard neu, die Anfrage landet auf einem Sekundär-Worker** (3 von 4 Fällen) — es darf keine zweite Schleife entstehen, und der Status muss der des Primary sein. Test: Task B2, `test_admin_restart_on_a_secondary_starts_nothing` und `test_health_monitor_status_comes_from_the_primary_on_secondaries`.
7. **SMART-Warnung aus dem Worker-Thread** — muss weiterhin per WebSocket ankommen. Unverändert sicher: `emit_sync` → `_broadcast_sync` nutzt `run_coroutine_threadsafe` mit dem in `lifespan.py:661` gebundenen Loop (Singleton, `init_event_emitter` ersetzt ihn nicht). Kein neuer Test; die bestehenden `_broadcast_sync`-Tests decken den Pfad.
8. **Lokaler Kanal (`baluhost-backend-local`)** — wählt seit #710 keinen eigenen Primary, startet nach Task B2 also keine Schleife mehr. Nach dem Deploy im Journal prüfen: genau ein `smartctl --scan` je 5 min über beide Units.
9. **Admin hat ein Profil manuell gesetzt, dann kommt eine fremd geschriebene Demand** — nach Task C1 rechnet der Primary neu und kann das manuelle Profil überschreiben. Das tut seine eigene `register_demand` heute schon genauso (`_recalculate_profile` prüft `_manual_override_until` nicht); C1 macht den Follower-Pfad gleich — praktisch aber neu: bisher überschrieb nur jede vierte Follower-Demand (die auf dem Primary landete) das manuelle Profil, jetzt jede. Im PR-Text nennen. Kein eigener Test.
10. **Geplantes Backup im Soft-Sleep** — nach Teil C kein Aufwecken mehr, aber die `surge`-Demand wird angewandt (der „CPU IDLE lock" des Sleep ist nur eine `idle`-Demand `sleep_mode`; die höchste gewinnt). Die 30-min-Eskalation (in Prod an) darf den Job nicht mittendrin suspendieren → Task C4. Tests: C1 `test_primary_applies_a_demand_another_process_wrote`, C4.
11. **Demand-Routen nach Task C3** — Verhaltensänderungen stehen in Task C3 (inaktiver Admin jetzt 401, Admin-API-Key jetzt angenommen — bewusst wie bei den `require_power_*`-Routen in `security-agent.md`). Nicht-Admin bleibt 403, ohne Anmeldung 401 — bestehende Tests in `tests/api/test_power_routes.py`.
12. **DB-Aussetzer auf dem Primary** — `list_active_demands()` schluckt Fehler und liefert `[]`; ohne strikten Lesepfad hieße das „alle Demands weg", Rückfall auf IDLE mitten im Backup. Test: C1 `test_db_error_keeps_cache_and_profile`.
13. **Scheduler-Job läuft, Eskalation fällig, DB nicht lesbar** — die Eskalation muss dann ausbleiben (fail-closed, wie das Display-Gate des Neustarts). Test: C4.

## Nicht in diesem Plan (eigene Issues)

Alle Nebenbefunde sind am 2026-11-26 angelegt.

- **#874** — `_reconcile_sleep_inhibitor()` synchron im Loop (aus #300, Kommentar 2026-09-27); `services/power/sleep.py:397, 946, 1288, 1617`, `CoreUptimeInhibitor` mit `time.sleep(0.2)` und `proc.wait(timeout=3.0)`.
- **#873** (severity:high) — SMART-Warnungsprüfung meldet nichts: `_check_smart_for_notifications` liest `attr.when_failed`/`attr.raw_value`, `SmartAttribute` hat nur `raw`/`status`. Der `AttributeError` beim ersten `Reallocated_*`-Attribut bricht die Prüfung **aller** Geräte ab, auch die auf `FAILED`. Im Dev-venv belegt: drei synthetische Geräte (Reallocated 8 / `FAILED` / Attribut `FAILING`) → 0 Meldungen. Teil B ändert daran nichts; die Formulierung „runs the SMART notification check" in `services/CLAUDE.md` bleibt trotzdem richtig.
- **#876** (zu prüfen) — SMART weckt im Soft-Sleep vermutlich heruntergefahrene Platten (`smartctl` ohne `-n standby`, Health-Schleife wird nicht pausiert).
- **#875** — `power_demand_logs` ohne Aufbewahrungsfrist; Teil C nimmt `sync_check` (5 min) und `auto_update` heraus, der Rest läuft stündlich oder seltener.
- **Am 2026-11-26 ebenfalls angelegt** (Nummern zu den drei Punkten unten: #877, #878, #879); aus dem Review von #873 dazu #880 (SMART-Mehrfachmeldungen je Prozess) und #881 (weitere SMART-Ausfallzeichen). #873 selbst ist mit PR #882 umgesetzt.
  - #877 — Die Auto-Wake-Middleware weckt bei **jedem** Request auf einen nicht freigegebenen Pfad aus dem Soft-Sleep und zählt ihn für die Idle-Messung — auch ohne Anmeldung (`middleware/sleep_auto_wake.py:117-151`). Teil C entfernt nur einen Aufrufer, nicht den Mechanismus; mit dauerhaftem Soft-Sleep fällt das stärker auf.
  - #878 — Suspend-on-exit (nach den Kernzeitfenstern) prüft keinen laufenden Scheduler-Job, nur die Idle-Messung (CPU > 8 %, I/O > 1 MB/s). Ein Job mit wenig Last (z. B. `cloud_sync`, der auf das Netz wartet) kann mittendrin suspendiert werden — schon heute, unabhängig von Teil C. Dasselbe Gate wie in C4 würde reichen.
  - #879 — `_boost_max_override` (`power/manager.py:1065-1066`) wird beim Ablauf eines manuellen Boosts nicht zurückgesetzt; eine spätere SURGE-Demand, die nach C1 jetzt auch von Followern und vom Scheduler kommt, wird bei aktiver externer Autorität mit der alten Obergrenze erzwungen.
- **#720** (Monitoring-Worker: `NoNewPrivileges` blockiert `sudo mdadm`/SMART) — schon erfasst.
- **#797** (primärer Worker, minütlich ~45 ms) — bleibt bestehen.

---

# Teil A — #300 abschließen

## File Structure

| Datei | Verantwortung |
|---|---|
| `backend/tests/test_route_async_convention.py` (neu) | AST-Wächter: `async def`-Route mit `Depends(get_db)` ohne eigenes `await` ist ein Fehler, außer sie steht in der Ausnahmeliste |
| `backend/tests/fixtures/async_db_route_allowlist.txt` (neu) | Ausnahmeliste der heutigen Altfälle, darf nur schrumpfen |
| `.claude/rules/backend/coding-style.md` | Regel „Async/await for all I/O" ersetzen |
| `backend/app/api/CLAUDE.md`, `backend/app/core/CLAUDE.md` | Konvention an den Stellen, an denen neue Routen entstehen |
| `docs/superpowers/specs/2026-07-30-s1-sync-sqlalchemy-event-loop-design.md` | Status-Zeile: PR2 verworfen, Verweis auf diesen Plan |
| `backend/app/api/routes/monitoring.py` | 13 GET-Handler `async def` → `def` |
| `backend/tests/api/test_monitoring_routes.py` | Verhaltenstest: DB-Lesen läuft nicht im Loop-Thread |

### Task A1: Konventions-Wächter und Regeltext

**Files:**
- Create: `backend/tests/test_route_async_convention.py`
- Create: `backend/tests/fixtures/async_db_route_allowlist.txt`
- Modify: `.claude/rules/backend/coding-style.md` (Zeile `- **Async/await** for all I/O operations`)
- Modify: `backend/app/api/CLAUDE.md` (Abschnitt „Adding a New Route", neuer Schritt 6)
- Modify: `backend/app/core/CLAUDE.md` (Bullet „**DB sessions**")
- Modify: `docs/superpowers/specs/2026-07-30-s1-sync-sqlalchemy-event-loop-design.md` (Zeile `**Status:**`)

**Interfaces:**
- Produces (alle in `tests/test_route_async_convention.py`):
  - `APP_DIR: Path` (= `backend/app`), `ALLOWLIST_PATH: Path`
  - `find_awaitless_async_db_handlers(source: str, rel: str) -> list[str]` — sortierte Einträge `"<rel>::<funktionsname>"`
  - `scan_app() -> set[str]` — über `app/api/routes/**/*.py` und `app/plugins/installed/**/*.py`, `rel` relativ zu `APP_DIR` mit `/` (z. B. `api/routes/monitoring.py::get_cpu_history`)
  - `load_allowlist() -> set[str]` — ignoriert Leerzeilen und Zeilen, die mit `#` beginnen

Erkennungsregeln (verbindlich):
- **Route-Handler**: `FunctionDef`/`AsyncFunctionDef` (beliebig verschachtelt) mit einem Dekorator `ast.Call`, dessen `func` ein `ast.Attribute` mit `attr` in `{"get", "post", "put", "delete", "patch", "api_route"}` ist. `websocket` gehört nicht dazu.
- **Nimmt `get_db`**: irgendwo in `ast.walk(fn.args)` (Defaults **und** Annotationen) steht ein Aufruf `Depends(...)` (`func` ist `Name("Depends")`), dessen erstes Argument `Name("get_db")` oder ein `Attribute` mit `attr == "get_db"` ist. Heute im Code kommen nur diese beiden Formen vor: `Depends(get_db)` und `Depends(deps.get_db)`; keine Route über `add_api_route`, keine doppelten Handlernamen je Datei.
- **Eigenes `await`**: ein `Await`, `AsyncWith` oder `AsyncFor` im Rumpf, ohne in `FunctionDef`, `AsyncFunctionDef`, `Lambda`, `ClassDef` abzusteigen.
- Gemeldet wird: `AsyncFunctionDef` ∧ Route ∧ `get_db` ∧ kein eigenes `await`.

- [ ] **Step 1: Detektor-Test schreiben**

```python
SRC = '''
@router.get("/a")
async def flagged(db: Session = Depends(get_db)):
    return db.query(X).all()

@router.get("/b")
async def awaits(db: Session = Depends(get_db)):
    await asyncio.sleep(0)

@router.get("/c")
def sync_ok(db: Session = Depends(get_db)):
    return 1

@router.post("/d")
async def nested_await_only(db: Session = Depends(deps.get_db)):
    async def inner():
        await x()
    return inner

@router.get("/e")
async def no_db(user=Depends(get_current_user)):
    return 1

@router.websocket("/f")
async def ws(db: Session = Depends(get_db)):
    return 1

@router.get("/g")
async def annotated(db: Annotated[Session, Depends(get_db)]):
    return 1
'''

def test_detector_flags_only_awaitless_async_db_handlers():
    assert find_awaitless_async_db_handlers(SRC, "x.py") == [
        "x.py::annotated", "x.py::flagged", "x.py::nested_await_only",
    ]
```

- [ ] **Step 2: Ausführen, muss fehlschlagen**

Run: `cd backend && python -m pytest tests/test_route_async_convention.py -v`
Expected: FAIL (`NameError`/`ImportError` für `find_awaitless_async_db_handlers`)

- [ ] **Step 3: `find_awaitless_async_db_handlers`, `scan_app`, `load_allowlist` implementieren** — nach den Erkennungsregeln oben, Muster wie `tests/test_async_subprocess_offloop.py` (`APP_DIR`, `ast.parse(path.read_text(encoding="utf-8"))`).

- [ ] **Step 4: Ausnahmeliste erzeugen**

Kopfzeilen (wörtlich):
```
# Route-Handler, die `async def` sind, Depends(get_db) nehmen und nie awaiten (#300).
# Diese Liste darf nur schrumpfen. Neue Handler dieser Form sind `def`.
# Wer einen Eintrag umstellt, entfernt ihn hier (test_allowlist_has_no_stale_entries).
```
Darunter die Ausgabe von
`cd backend && python -c "from tests.test_route_async_convention import scan_app; print('\n'.join(sorted(scan_app())))"`.
Erwartung: ≈ 304 Zeilen (Zählung 2026-11-26: 302 in `api/routes`, 2 in Plugins). Die tatsächliche Zahl in der Commit-Nachricht nennen.

- [ ] **Step 5: Die drei Wächter-Tests schreiben**

```python
def test_no_new_awaitless_async_db_handlers():
    new = sorted(scan_app() - load_allowlist())
    assert new == [], (
        "async def + Depends(get_db) ohne await blockiert den Event-Loop. "
        "Als `def` deklarieren (läuft im Threadpool), siehe "
        ".claude/rules/backend/coding-style.md: " + ", ".join(new)
    )

def test_allowlist_has_no_stale_entries():
    stale = sorted(load_allowlist() - scan_app())
    assert stale == [], "Aus tests/fixtures/async_db_route_allowlist.txt entfernen: " + ", ".join(stale)

def test_allowlist_is_sorted_and_unique():
    entries = [l for l in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    assert entries == sorted(set(entries))
```

- [ ] **Step 6: Ausführen, alles grün**

Run: `cd backend && python -m pytest tests/test_route_async_convention.py -v`
Expected: 4 passed

- [ ] **Step 7: Negativkontrolle** — in einer beliebigen Route-Datei vorübergehend einen Handler aus der Liste auf `def` stellen → `test_allowlist_has_no_stale_entries` rot; zurückdrehen. Einen Listeneintrag löschen → `test_no_new_awaitless_async_db_handlers` rot; zurückdrehen. Nichts davon committen.

- [ ] **Step 8: Regeltexte**

- `coding-style.md`: Zeile `- **Async/await** for all I/O operations` ersetzen durch
  `- **\`async def\` only with a real \`await\`**: no synchronous I/O (DB session, files, \`subprocess\`, sync HTTP clients) directly inside \`async def\` — it blocks the event loop of the whole worker. A route handler that takes \`Depends(get_db)\` and awaits nothing is a plain \`def\` (FastAPI runs it in the threadpool); blocking calls inside async code go through \`asyncio.to_thread(...)\`. Guards: \`tests/test_route_async_convention.py\` (allowlist only shrinks), \`tests/test_async_subprocess_offloop.py\`.`
- `coding-style.md`, Abschnitt „Example Service Function": das Beispiel zeigt heute `async def get_file_list(path, current_user, db: Session)` — genau das Muster, das die neue Regel verbietet. Auf `def get_file_list(...)` ändern, Rest unverändert.
- `api/CLAUDE.md`, „Adding a New Route": Schritt 6 anhängen:
  `6. A handler that takes \`Depends(get_db)\` and awaits nothing is \`def\`, not \`async def\` — FastAPI runs it in the threadpool. \`tests/test_route_async_convention.py\` fails for a new \`async def\` of that shape.`
- `core/CLAUDE.md`, Bullet „**DB sessions**": Satz anhängen:
  `A route that only does sync DB work is a \`def\` handler; in \`async def\` code, sync DB work goes through \`asyncio.to_thread\`.`
- Spec, Zeile `**Status:**` ersetzen durch:
  `**Status:** PR1 (Sonde, #496) umgesetzt. PR2 (Sweep) am 2026-11-26 nach Messung verworfen — kaum gleichzeitige Requests, kein Handler-Lag messbar. Ersetzt durch Wächter + Monitoring-GETs: \`docs/superpowers/plans/2026-11-26-s1-abschluss-und-5min-loop-stall.md\`.`

- [ ] **Step 9: Ruff, Commit**

Run: `cd backend && python -m ruff check tests/test_route_async_convention.py` → keine Meldung.
```bash
git add backend/tests/test_route_async_convention.py backend/tests/fixtures/async_db_route_allowlist.txt \
  .claude/rules/backend/coding-style.md backend/app/api/CLAUDE.md backend/app/core/CLAUDE.md \
  docs/superpowers/specs/2026-07-30-s1-sync-sqlalchemy-event-loop-design.md
git commit -m "test(routes): Wächter gegen async-Handler mit sync-DB ohne await (#300)"
```

### Task A2: Monitoring-GETs auf `def`

**Files:**
- Modify: `backend/app/api/routes/monitoring.py` — genau diese 13 Handler (Zeilen Stand `main` @ `635b273f`): `get_cpu_current` (131), `get_cpu_history` (159), `get_memory_current` (200), `get_memory_history` (226), `get_network_current` (267), `get_network_history` (293), `get_disk_io_current` (334), `get_disk_io_history` (349), `get_processes_history` (442), `get_uptime_current` (514), `get_uptime_history` (566), `get_retention_config` (637), `get_database_stats` (698)
- Modify: `backend/tests/fixtures/async_db_route_allowlist.txt` — dieselben 13 Einträge entfernen
- Test: `backend/tests/api/test_monitoring_routes.py`

Nicht anfassen: `update_retention_config` (PUT), `trigger_cleanup` (POST) — schreibend, bleiben in der Liste. `get_processes_current`, `get_monitoring_status` — kein `get_db`.

**Interfaces:**
- Consumes: Task A1 (`tests/fixtures/async_db_route_allowlist.txt`, Wächter-Tests)

- [ ] **Step 1: Verhaltenstest schreiben** (`tests/api/test_monitoring_routes.py`)

```python
async def test_cpu_history_db_read_runs_off_event_loop(async_client, user_headers, monkeypatch):
    from app.services.monitoring.orchestrator import get_monitoring_orchestrator
    orch = get_monitoring_orchestrator()
    seen: list[int] = []
    def fake_history_db(db, start=None, limit=None, **kw):
        seen.append(threading.get_ident())
        return []
    monkeypatch.setattr(orch.cpu_collector, "get_history_db", fake_history_db)
    r = await async_client.get(
        "/api/monitoring/cpu/history",
        params={"time_range": "24h", "source": "database"},
        headers=user_headers,
    )
    assert r.status_code == 200
    assert seen, "get_history_db wurde nicht aufgerufen"
    assert threading.get_ident() not in seen, "DB-Lesen lief im Event-Loop-Thread"
```
(`import threading` im Testmodul ergänzen. `async_client` aus `tests/conftest.py` führt die App im Loop des Tests aus; ein `async def`-Handler ruft im selben Thread, ein `def`-Handler im anyio-Threadpool. Falls `get_monitoring_orchestrator` anders importiert wird, den Import aus `api/routes/monitoring.py` übernehmen.)

- [ ] **Step 2: Ausführen, muss fehlschlagen**

Run: `cd backend && python -m pytest tests/api/test_monitoring_routes.py::test_cpu_history_db_read_runs_off_event_loop -v`
Expected: FAIL „DB-Lesen lief im Event-Loop-Thread"

- [ ] **Step 3: Die 13 Einträge aus der Ausnahmeliste löschen**

Run: `cd backend && python -m pytest tests/test_route_async_convention.py -v`
Expected: FAIL in `test_no_new_awaitless_async_db_handlers`, Meldung nennt genau die 13 Handler

- [ ] **Step 4: Die 13 Handler von `async def` auf `def` umstellen** — nur das Schlüsselwort; Dekoratoren, Signaturen, Rümpfe bleiben.

- [ ] **Step 5: Ausführen, alles grün**

Run: `cd backend && python -m pytest tests/test_route_async_convention.py tests/api/test_monitoring_routes.py -v`
Expected: alle passed

- [ ] **Step 6: Ruff, Commit**

Run: `cd backend && python -m ruff check app/api/routes/monitoring.py tests/api/test_monitoring_routes.py`
```bash
git add backend/app/api/routes/monitoring.py backend/tests/fixtures/async_db_route_allowlist.txt backend/tests/api/test_monitoring_routes.py
git commit -m "refactor(monitoring): DB-lesende GET-Handler laufen im Threadpool (#300)"
```

### Abschluss Teil A

- [ ] Volle Suite in der Sandbox bzw. CI grün; `cd backend && python -m ruff check app tests` sauber.
- [ ] **Vor dem Schließen von #300:** Der Kommentar vom 2026-09-27 in #300 meldet `SleepManagerService._reconcile_sleep_inhibitor()` synchron im Loop (`CoreUptimeInhibitor`: `time.sleep(0.2)`, `proc.wait(timeout=3.0)`). Das gilt weiter (`services/power/sleep.py:397, 946, 1288, 1617`) und ist jetzt **#874** — im Abschlusskommentar an #300 darauf verweisen, damit der Befund nicht mit #300 verschwindet.
- [ ] PR `refactor/s1-close-out` → `main`, Text enthält den Abschnitt „Entscheidung" oben und `Closes #300`.
- [ ] Nach dem Merge: Kommentar an #300 mit den Zahlen aus „Entscheidung" und den bekannten Grenzen des Wächters: 96 `async def`-Handler mit `get_db` **und** einem `await` führen weiterhin sync-DB im Loop aus und stehen in keiner Liste; `async def`-Routen, die selbst `SessionLocal()` öffnen (~10 Stellen), sieht er ebenfalls nicht. Kein Nachmessen nötig — Teil A verspricht keinen Latenzgewinn. Kurz nach dem Deploy `pool_in_use_max` und `threadpool_borrowed_max` in der Sonde ansehen (bisherige Maxima 10 bzw. 6).

---

# Teil B — 5-Minuten-Stillstand aller Backend-Worker

## Messung (Prod, 2026-11-26)

- **Symptom:** In 18,2 % aller Minuten (1.101 von 6.062, 13.–26.11.) zeigen mindestens drei Worker gleichzeitig `loop_lag_max` > 100 ms; Abstand fast immer exakt 5 min (1.028 von ~1.100 Abständen), phasenstarr zum Prozessstart, auch in Fenstern ohne Requests. Typisch 200–850 ms. Auf den drei sekundären Workern ist das die größte verbleibende Lag-Quelle (dort sonst ~1 ms).
- **Ausgeschlossen:** System-Stillstand (eine unabhängige asyncio-Sonde in einem fremden Prozess sah über 6,5 min keine Verzögerung > 30 ms), PostgreSQL-Checkpoints (Korrelation auf Zufallsniveau), CPU-Last der Worker (Thread-CPU-Zeiten aus `/proc` zeigen keine gleichzeitige Rechenlast).
- **Beleg:** Um 13:03:33.709 und 13:08:34.584 standen alle vier Hauptthreads gleichzeitig im Zustand `D`. `py-spy record --idle` (über `sg baluhost`, ohne sudo) auf einem sekundären Worker über die Blockade 13:08:34 zeigt als einzige Nicht-Leerlauf-Stacks:
  `_health_check_loop (services/jobs.py:19)` → `get_system_info (services/system.py:219)` → `measure_cpu_percent` (`time.sleep(0.1)`), → `get_cpu_sensor_data` → `psutil.sensors_temperatures` (sysfs, `D`), sowie `jobs.py:20` → `get_smart_status` → `_run_smartctl`.
  Das Journal zeigt dazu je Blockade **viermal** `sudo dmidecode -t memory` und **viermal** `sudo smartctl --scan -j` plus `smartctl` je Platte und `mdadm --detail` — einmal pro Worker, um 13:08:34 zusammen 36 sudo-Aufrufe.
  Anteile im Profil des sekundären Workers (~920 ms unter `_health_check_loop`): SMART ~540 ms, `dmidecode` ~190 ms, `measure_cpu_percent` ~110 ms, Sensoren ~50 ms.

## Ursache

`services/jobs.py:_health_check_loop` ruft alle 300 s **synchron im Event-Loop** `system_service.get_system_info()` und `smart_service.get_smart_status()` auf. Gestartet wird die Schleife in `core/lifespan.py:690`, **vor** `_try_become_primary()` (Z. 693) — also auf jedem API-Prozess (4 TCP-Worker, dazu 2 auf dem lokalen Kanal, falls aktiv). Weil alle Worker im selben Moment starten, blockieren sie im selben Moment.

- `get_system_info()` ist eine reine Lesefunktion; ihr Ergebnis wird in der Schleife verworfen. Der Aufruf ist tot, kostet aber `time.sleep(0.1)`, sysfs-Lesen und einen Subprozess (`sudo dmidecode`, ohne `-n`; `_get_cpu_model()` liest `/proc/cpuinfo` direkt).
- `get_smart_status()` hat zwei gewollte Nebenwirkungen: es füllt den SMART-Cache des Prozesses (`_SMART_CACHE_TTL_SECONDS = 120`, bei 300 s Takt also nur 120 von 300 s warm; jeder Leser füllt ihn bei Bedarf selbst nach) und läuft durch die SMART-Warnungsprüfung (`_check_smart_for_notifications`). Diese Prüfung meldet heute praktisch nichts (#873) — Teil B erhält den Aufruf trotzdem, damit der Fix von #873 wirkt, sobald er kommt. Der Cooldown der Warnungen liegt nur im Prozessspeicher (`events.py:_cooldown_cache`); primary-only verringert Doppelmeldungen, beseitigt sie aber nicht (Request-Pfade und der Scheduler-Worker prüfen mit eigenem Cooldown).
- Dieselben blockierenden Aufrufe stecken in zwei Request-Pfaden: `api/routes/system.py:531` (`async def get_smart_status`) und `api/routes/system_raid.py:272` (`async def get_system_health`), beide ohne `await`. Nach dem Fix haben die sekundären Worker keinen vorgewärmten SMART-Cache mehr — dort blockierte der erste Aufruf je 120 s den Worker für ~0,5–0,9 s. Deshalb Task B3.
- `emit_sync` ist für Worker-Threads gebaut (`_broadcast_sync` → `asyncio.run_coroutine_threadsafe`); der Aufruf aus `asyncio.to_thread` ist sicher.

## Fix

1. Die Schleife ruft nur noch den SMART-Check, und zwar über `asyncio.to_thread`. Der tote `get_system_info()`-Aufruf entfällt.
2. Nur der primäre Worker startet sie — wie die Upload-Bereinigung (`_start_chunked_upload_cleanup_if_primary`) und mit Start-Wrapper im Service-Registry wie Lüfter (#555) und Sleep (#817), damit ein Admin-Neustart auf einem Sekundär-Worker keine zweite Schleife startet. Ein solcher Neustart meldet danach Erfolg aus dem DB-Leser, ohne etwas neu zu starten — wie heute schon bei Lüfter und Sleep.
3. Die zwei Request-Pfade mit denselben Aufrufen werden `def` (Task B3).

## File Structure

| Datei | Verantwortung |
|---|---|
| `backend/app/services/jobs.py` | `run_health_checks()` (sync), Schleife über `asyncio.to_thread` |
| `backend/app/core/lifespan.py` | `_start_health_monitor_if_primary()`, Aufruf nach der Primary-Wahl |
| `backend/app/core/service_registry.py` | `health_monitor` primary-only, Start-Wrapper mit festgehaltener Rolle |
| `backend/app/services/CLAUDE.md` | Zeile `jobs.py` |
| `backend/tests/services/test_health_monitor.py` (neu) | Verhalten der Schleife |
| `backend/tests/core/test_lifespan_health_monitor.py` (neu) | Primary-only-Start, Admin-Neustart |
| `backend/tests/test_async_subprocess_offloop.py` | statischer Wächter um `jobs.py`, `api/routes/system.py`, `api/routes/system_raid.py` erweitert |
| `backend/app/api/routes/system.py`, `backend/app/api/routes/system_raid.py` | zwei Handler `async def` → `def` |
| `backend/app/core/CLAUDE.md` | Zeile `lifespan.py`: Health-Monitor nur auf dem Primary |

### Task B1: Health-Check aus dem Event-Loop

**Files:**
- Modify: `backend/app/services/jobs.py:1-23`
- Create: `backend/tests/services/test_health_monitor.py`
- Modify: `backend/tests/test_async_subprocess_offloop.py` (`_SYNC_SUBPROCESS_HELPERS`)

**Interfaces:**
- Produces: `jobs.run_health_checks() -> None` — sync; ruft `smart_service.get_smart_status()`, fängt `Exception` und loggt auf DEBUG (wie heute in der Schleife). `jobs._health_check_loop(interval_seconds: int) -> None` — `await asyncio.to_thread(run_health_checks)`, dann `await asyncio.sleep(interval_seconds)`.

- [ ] **Step 1: Tests schreiben** (`tests/services/test_health_monitor.py`)

**Pflicht in jedem Test, der die Schleife laufen lässt:** `get_system_info` abklemmen. Die alte Schleife ruft es vor SMART auf, und sein Pfad endet in `sudo dmidecode` (NOPASSWD für `sven`) — ohne Abklemmen liefe in der Rot-Phase `dmidecode` als root auf der Box. Die Zeile wirkt vor und nach dem Fix gleich.

```python
@pytest.fixture(autouse=True)
def no_system_info(monkeypatch):
    monkeypatch.setattr("app.services.system.get_system_info", lambda: None)

async def test_health_check_runs_off_the_event_loop(monkeypatch):
    loop = asyncio.get_running_loop()
    seen, done = [], asyncio.Event()
    def fake_smart():
        seen.append(threading.get_ident())
        loop.call_soon_threadsafe(done.set)
    monkeypatch.setattr(jobs.smart_service, "get_smart_status", fake_smart)
    task = asyncio.create_task(jobs._health_check_loop(3600))
    await asyncio.wait_for(done.wait(), 5)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert seen and threading.get_ident() not in seen

def test_health_check_does_not_read_system_info(monkeypatch):
    calls = []
    monkeypatch.setattr(jobs.smart_service, "get_smart_status", lambda: None)
    monkeypatch.setattr("app.services.system.get_system_info", lambda: calls.append(1))
    jobs.run_health_checks()
    assert calls == []

async def test_a_failing_check_does_not_end_the_loop(monkeypatch):
    loop = asyncio.get_running_loop()
    calls, second = [], asyncio.Event()
    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("smartctl kaputt")
        loop.call_soon_threadsafe(second.set)
    monkeypatch.setattr(jobs.smart_service, "get_smart_status", flaky)
    task = asyncio.create_task(jobs._health_check_loop(0.01))
    await asyncio.wait_for(second.wait(), 5)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
```
In `tests/test_async_subprocess_offloop.py` den Eintrag `"services/jobs.py": {"get_smart_status", "get_system_info"}` in `_SYNC_SUBPROCESS_HELPERS` ergänzen.

- [ ] **Step 2: Ausführen, muss fehlschlagen**

Run: `cd backend && python -m pytest tests/services/test_health_monitor.py "tests/test_async_subprocess_offloop.py::test_sync_subprocess_helpers_not_called_directly_from_async_def" -v`
Expected: FAIL in `test_health_check_runs_off_the_event_loop` (Loop-Thread), `test_health_check_does_not_read_system_info` (`run_health_checks` fehlt) und im Wächter (`services/jobs.py:19 _health_check_loop -> get_system_info`, `:20 … -> get_smart_status`). `test_a_failing_check_does_not_end_the_loop` ist schon vorher grün — die alte Schleife fängt die Ausnahme auch; der Test hält fest, dass der Umbau das nicht verliert.

- [ ] **Step 3: `run_health_checks()` und die Schleife umbauen** — Import `system_service` entfernen (sonst F401).

- [ ] **Step 4: Ausführen, alles grün; Ruff**

Run: `cd backend && python -m pytest tests/services/test_health_monitor.py tests/test_async_subprocess_offloop.py -v && python -m ruff check app/services/jobs.py tests/services/test_health_monitor.py`
Expected: alle passed, Ruff ohne Meldung

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/jobs.py backend/tests/services/test_health_monitor.py backend/tests/test_async_subprocess_offloop.py
git commit -m "fix(async): Health-Check aus dem Event-Loop, ohne toten Systeminfo-Aufruf (#872)"
```

### Task B2: Nur der primäre Worker startet den Health-Monitor

**Files:**
- Modify: `backend/app/core/lifespan.py:690` (Aufruf entfernen), neue Funktion neben `_start_chunked_upload_cleanup_if_primary` (Z. ~621), Aufruf direkt nach `_start_chunked_upload_cleanup_if_primary()` (Z. ~700)
- Modify: `backend/app/core/service_registry.py` (`PRIMARY_ONLY_SERVICES` Z. 20; Registrierung `health_monitor` Z. ~281)
- Modify: `backend/app/services/CLAUDE.md` (Zeile `jobs.py` in der Top-level-Tabelle ersetzen; heute: „Health monitor background task (disk space, SMART)" — den Plattenplatz hat die Schleife nie geprüft, das Ergebnis wurde verworfen)
- Modify: `backend/app/core/CLAUDE.md` (Zeile `lifespan.py`: „Starts hardware services, plugins, mDNS, heartbeat writer" um „and the SMART health monitor" ergänzen — alles davon nur auf dem Primary)
- Create: `backend/tests/core/test_lifespan_health_monitor.py`

**Interfaces:**
- Consumes: `jobs.start_health_monitor()`, `jobs.stop_health_monitor()`, `jobs.run_health_checks` (Task B1)
- Produces: `lifespan._start_health_monitor_if_primary() -> None` (async; no-op wenn `IS_PRIMARY_WORKER` falsch). Im Registry ein Start-Wrapper `_start_health_monitor_for_worker()` (async), der über `is_primary_worker` schließt und auf einem Sekundär-Worker nichts startet.

- [ ] **Step 1: Tests schreiben** (`tests/core/test_lifespan_health_monitor.py`; Muster: `tests/core/test_lifespan_chunked_upload_cleanup.py` und `tests/test_fan_service_registry_worker_role.py`)

```python
@pytest.fixture
def registry_snapshot():
    # Kopie aus tests/test_fan_service_registry_worker_role.py:21 (dort modullokal)
    previous = dict(service_status._service_registry)
    yield
    service_status._service_registry.clear()
    service_status._service_registry.update(previous)

@pytest.fixture
async def no_real_checks(monkeypatch):
    monkeypatch.setattr(jobs, "_health_task", None)            # sauberer Ausgangszustand
    monkeypatch.setattr(jobs.settings, "is_dev_mode", False)   # sonst startet start_health_monitor nie
    monkeypatch.setattr(jobs, "run_health_checks", lambda: None)
    yield
    await jobs.stop_health_monitor()   # räumt eine gestartete Schleife ab, No-op sonst

async def test_the_primary_starts_the_health_monitor(monkeypatch, no_real_checks):
    monkeypatch.setattr(lifespan_module, "IS_PRIMARY_WORKER", True)
    await lifespan_module._start_health_monitor_if_primary()
    assert jobs._health_task is not None and not jobs._health_task.done()

async def test_a_secondary_worker_starts_no_health_monitor(monkeypatch, no_real_checks):
    monkeypatch.setattr(lifespan_module, "IS_PRIMARY_WORKER", False)
    await lifespan_module._start_health_monitor_if_primary()
    assert jobs._health_task is None

def test_startup_starts_it_only_after_the_primary_is_elected():
    tree = ast.parse(textwrap.dedent(inspect.getsource(lifespan_module._startup)))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    def lines(name):  # Name- und Attribute-Aufrufe
        return [c.lineno for c in calls
                if getattr(c.func, "id", None) == name or getattr(c.func, "attr", None) == name]
    assert lines("start_health_monitor") == []
    assert min(lines("_try_become_primary")) < min(lines("_start_health_monitor_if_primary"))

async def test_admin_restart_on_a_secondary_starts_nothing(monkeypatch, registry_snapshot, no_real_checks):
    service_registry.register_all_services(is_primary_worker=False, discovery_service=None)
    await service_status._service_registry["health_monitor"]["start"]()
    assert jobs._health_task is None

async def test_admin_restart_on_the_primary_starts_the_loop(monkeypatch, registry_snapshot, no_real_checks):
    service_registry.register_all_services(is_primary_worker=True, discovery_service=None)
    await service_status._service_registry["health_monitor"]["start"]()
    assert jobs._health_task is not None

def test_health_monitor_status_comes_from_the_primary_on_secondaries(registry_snapshot):
    service_registry.register_all_services(is_primary_worker=False, discovery_service=None)
    assert service_status._service_registry["health_monitor"]["get_status"] is not jobs.get_status
```

- [ ] **Step 2: Ausführen, muss fehlschlagen**

Run: `cd backend && python -m pytest tests/core/test_lifespan_health_monitor.py -v`
Expected: FAIL — `_start_health_monitor_if_primary` fehlt, Sekundär-Neustart startet eine Schleife, `health_monitor` nicht in `PRIMARY_ONLY_SERVICES`

- [ ] **Step 3: Umsetzen** — `lifespan.py`: Aufruf in Z. 690 entfernen, `_start_health_monitor_if_primary()` mit Docstring im Stil von `_start_chunked_upload_cleanup_if_primary` (warum primary-only: SMART-Cooldown nur im Prozessspeicher, 4–6 gleichzeitige smartctl-Läufe, #872), Aufruf nach `_start_chunked_upload_cleanup_if_primary()`. Der Shutdown-Aufruf `await jobs.stop_health_monitor()` (Z. 942) bleibt; auf Sekundär-Workern ist er ein No-op. `service_registry.py`: `"health_monitor"` in `PRIMARY_ONLY_SERVICES`, Wrapper analog `_start_fan_control_for_worker` mit Kommentar (#555/#817-Muster). `services/CLAUDE.md`: Zeile `| \`jobs.py\` | SMART health check every 300 s, primary worker only, off the event loop (\`asyncio.to_thread\`); refreshes the primary's SMART cache and runs the SMART notification check (#872) |`. `core/CLAUDE.md`: Zeile `lifespan.py` wie unter Files.

- [ ] **Step 4: Ausführen, alles grün; Ruff**

Run: `cd backend && python -m pytest tests/core/test_lifespan_health_monitor.py tests/test_fan_service_registry_worker_role.py tests/services/test_sleep_inhibitor_primary_only.py tests/services/test_network_discovery_registry_state.py tests/core -v && python -m ruff check app tests`
Expected: alle passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/lifespan.py backend/app/core/service_registry.py backend/app/services/CLAUDE.md backend/app/core/CLAUDE.md backend/tests/core/test_lifespan_health_monitor.py
git commit -m "fix(lifespan): Health-Monitor nur auf dem primären Worker (#872)"
```

### Task B3: SMART- und Health-Route im Threadpool

**Files:**
- Modify: `backend/app/api/routes/system.py:531` (`get_smart_status`), `backend/app/api/routes/system_raid.py:272` (`get_system_health`) — je nur `async def` → `def`; beide ohne `await`, beide mit `@user_limiter.limit` (Präzedenz `admin_db.py`)
- Modify: `backend/tests/test_async_subprocess_offloop.py` (`_SYNC_SUBPROCESS_HELPERS`)
- Create: `backend/tests/api/test_system_routes_off_loop.py` (eine `test_system_routes.py` gibt es nicht)

**Interfaces:**
- Consumes: nichts aus B1/B2; unabhängig umsetzbar.

- [ ] **Step 1: Tests schreiben**

`_SYNC_SUBPROCESS_HELPERS` um `"api/routes/system.py": {"get_smart_status"}` und `"api/routes/system_raid.py": {"get_smart_status", "get_system_info"}` ergänzen. Verhaltenstest nach dem Muster von Task A2:

```python
async def test_smart_status_route_reads_off_event_loop(async_client, user_headers, monkeypatch):
    from app.services.hardware import smart as smart_service   # derselbe Import wie api/routes/system.py:31
    from app.schemas.system import SmartStatusResponse
    seen = []
    def fake():
        seen.append(threading.get_ident())
        return SmartStatusResponse(checked_at=datetime.now(tz=timezone.utc), devices=[])
    monkeypatch.setattr(smart_service, "get_smart_status", fake)
    r = await async_client.get("/api/system/smart/status", headers=user_headers)
    assert r.status_code == 200
    assert seen and threading.get_ident() not in seen
```

- [ ] **Step 2: Ausführen, muss fehlschlagen**

Run: `cd backend && python -m pytest tests/api/test_system_routes_off_loop.py "tests/test_async_subprocess_offloop.py::test_sync_subprocess_helpers_not_called_directly_from_async_def" -v`
Expected: FAIL — Verhaltenstest (Loop-Thread), Wächter meldet `api/routes/system.py:532` und `api/routes/system_raid.py:276/280`

- [ ] **Step 3: Beide Handler auf `def` umstellen.**

- [ ] **Step 4: Ausführen, alles grün; Ruff; Commit**

Run: `cd backend && python -m pytest tests/api/test_system_routes_off_loop.py tests/test_async_subprocess_offloop.py -v && python -m ruff check app/api/routes/system.py app/api/routes/system_raid.py tests`
```bash
git add backend/app/api/routes/system.py backend/app/api/routes/system_raid.py backend/tests/test_async_subprocess_offloop.py backend/tests/api/test_system_routes_off_loop.py
git commit -m "fix(async): SMART- und Health-Route laufen im Threadpool (#872)"
```

### Abschluss Teil B

- [ ] Volle Suite (Sandbox/CI) und `python -m ruff check app tests` grün.
- [ ] PR `fix/loop-stall-5min` → `main`, Text mit „Messung" und „Ursache" oben, `Closes #872`, `Refs #797`.
- [ ] **Nach dem Deploy messen** (mindestens 24 h Wachzeit, Fenster > 65 s ausgeschlossen). Je Worker zählen, nicht je Minute über alle Worker: die Worker loggen zu verschiedenen Sekunden, eine Blockade verteilt sich sonst auf zwei Minuten-Eimer, und die Vorher-Zahl wäre unterschätzt (echt ≈ jeder 5-Minuten-Tick, ~20 %).
  - Je sekundärem Worker der Anteil der Fenster mit `loop_lag_max` > 100 ms: vorher ~18–20 % → Ziel < 1 %.
  - `loop_lag_max` der sekundären Worker, 90. Perzentil: vorher ~360 ms → Ziel < 10 ms.
  - Journal: `journalctl --since '-1h' | awk '/COMMAND=.*(dmidecode|smartctl --scan)/'` — kein `dmidecode` mehr aus der Schleife; aus der Schleife genau ein `smartctl --scan` je Tick statt vier (Request-Pfade können weitere auslösen, solange die UI offen ist).
  - Auswertung: `journalctl -u baluhost-backend --since … -o cat | awk '/"concurrency_probe"/'`, Felder `worker_pid` und `loop_lag_max_ms` (Vorgehen wie in #788).
  - Ergebnis als Kommentar an #872; bleibt auf dem primären Worker der minütliche ~45-ms-Rest (Lüfter-hwmon im Loop), gehört der zu #797, nicht hierher.

---

# Teil C — Power-Demands des Schedulers

## Befund (Prod, 2026-11-26)

- **401 bei jeder Registrierung:** `scheduler/worker.py:_register_power_demand` schickt `POST /api/power/demands` mit `X-Service-Token: settings.scheduler_service_token`. Das Feld ist standardmäßig leer und wird dann in `core/config.py:333-335` **pro Prozess** per `secrets.token_urlsafe(32)` erzeugt. `SCHEDULER_SERVICE_TOKEN` steht weder in `/opt/baluhost/.env.production` noch in `backend/.env` → Scheduler und jeder Backend-Worker haben verschiedene Tokens. Journal: 264 × `Power demand registration failed … 401` in 3 Tagen (232 `sync_check`, 16 `cloud_sync`, 16 `smart_scan`). Die Funktion hat in Produktion nie gewirkt.
- **Aufwecken trotz 401:** `middleware/sleep_auto_wake.py` weckt bei jedem nicht freigegebenen Request aus dem Soft-Sleep, bevor die Route authentifiziert. `POST`/`DELETE /api/power/demands` stehen nicht auf der Liste. Journal 26.11.: Soft-Sleep endet um 10:45:10 und 10:50:10 mit `auto_wake: POST /api/power/demands` — exakt im Takt von `sync_check` (alle 300 s, `schemas/scheduler.py:264`).
- **Primary wendet fremd geschriebene Demands nicht an:** Demands liegen in `power_demands`; `register_demand` auf einem Follower schreibt nur die Zeile. Der Primary lädt sie alle 5 s in seinen Cache (`manager.py:_refresh_demand_cache`), rechnet das Profil aber nur neu bei Ablauf, bei Auto-Scaling oder bei einer Registrierung auf ihm selbst. Der Docstring von `register_demand` verspricht das Gegenteil („the next monitor tick on the primary picks up the new row"). Betrifft heute schon jede Demand, die auf einem Follower registriert wird (`@requires_power`, `POST /api/power/demands` in 3 von 4 Fällen), und ein Profil bleibt hängen, wenn die Registrierung auf dem Primary und die Freigabe auf einem Follower landet. `_check_auto_scaling` wendet nie eine Demand an und ist ohnehin tot (`set_cpu_usage_callback` hat keinen Aufrufer).
- **Sleep-Konfiguration in Prod** (DB, 2026-11-26): `auto_idle_enabled` an (5 min), `auto_escalation_enabled` **an** (30 min Soft-Sleep → echter Suspend), `disk_spindown_enabled` **aus**, kein Zeitplan. Weil `sync_check` die Box bisher spätestens nach 5 min weckte, hat die Eskalation noch nie gegriffen (kein `Auto-escalation` im Journal seit 20.11.).

## Fix

1. Der Primary rechnet neu, wenn sich die Demands in der DB geändert haben (Task C1) — mit striktem Lesepfad, damit ein DB-Fehler nicht als „alle Demands weg" gilt.
2. Der Scheduler schreibt seine Demand direkt in `power_demands` — kein HTTP, kein Token, kein Aufwecken (Task C2). `sync_check` (alle 5 min, eine DB-Abfrage) und `auto_update` (kehrt sofort zurück, `worker.py:370-372`) melden keine Demand mehr an (`idle`): eine Demand wirkt erst beim nächsten Tick des Primary (≤ 5 s), ein kürzerer Job erzeugt nur zwei Log-Zeilen.
3. Der Service-Token-Pfad hat danach keinen Aufrufer mehr und wird entfernt (Task C3): die beiden Demand-Routen nehmen `deps.get_current_admin`.
4. Die Eskalation zum Suspend wartet, solange ein Scheduler-Job läuft (Task C4) — dasselbe Gate wie beim geplanten Neustart.

**Politik (neu, im PR ausdrücklich nennen):** Scheduler-Jobs wecken das NAS nicht mehr aus dem Soft-Sleep, sie laufen im Soft-Sleep weiter und bekommen ihre CPU über die Demand (der „CPU IDLE lock" ist nur eine `idle`-Demand `sleep_mode`). Das entspricht „automatisch weckt nicht" aus dem Sleep-Aware-Sync-Spec; dass Jobs im Schlaf *laufen*, ist eine neue Entscheidung — der Spec weist automatische Syncs im Soft-Sleep mit 503 ab. Folgen: der Soft-Sleep hält zum ersten Mal länger als 5 min, und die 30-min-Eskalation greift. Auto-Idle und Suspend-on-exit sind durch die Idle-Erkennung geschützt (CPU > 8 %, Platten-I/O > 1 MB/s gelten als aktiv), die Eskalation ist ein reiner Timer — daher C4. Platten-Spindown ist in Prod aus; #876 betrifft BaluNode erst, wenn er eingeschaltet wird.

## File Structure

| Datei | Verantwortung |
|---|---|
| `backend/app/services/power/config_store.py` | `list_active_demands(*, strict=False)` |
| `backend/app/services/power/manager.py` | `_refresh_demand_cache()` meldet Änderung, `_sync_demands_from_db()` rechnet dann neu |
| `backend/app/services/scheduler/power_demand.py` (neu) | `SCHEDULER_POWER_LEVELS`, `register_scheduler_demand()`, `unregister_scheduler_demand()` |
| `backend/app/services/scheduler/worker.py` | Methoden delegieren, kein `requests` mehr für Demands |
| `backend/app/api/routes/power.py`, `backend/app/core/config.py` | Service-Token-Pfad und -Feld entfernen |
| `backend/app/services/power/scheduled_reboot.py`, `backend/app/services/power/sleep.py` | Gate „Scheduler-Job läuft" öffentlich machen und in der Eskalation nutzen |
| `backend/app/services/CLAUDE.md` | Eintrag `scheduler/power_demand.py` unter `scheduler/`, Hinweis Eskalations-Gate unter `sleep.py` |
| `backend/tests/services/conftest.py` (neu) | Fixture `power_tables_in_global_db` (aus `test_power_manager.py` verschoben, plus `PowerDemandLog`) |
| `backend/tests/services/test_power_manager.py`, `backend/tests/services/test_scheduler_power_demand.py` (neu), `backend/tests/api/test_power_routes.py`, `backend/tests/services/test_sleep_escalation_scheduler_gate.py` (neu) | Tests |
| `backend/tests/test_service_token_compare.py` | löschen (testet die entfernte Funktion) |

### Task C1: Primary wendet Demands aus der DB an

**Files:**
- Modify: `backend/app/services/power/config_store.py:418-439` (`list_active_demands`)
- Modify: `backend/app/services/power/manager.py` — `_refresh_demand_cache` (Z. 545-550), Aufruf in `_monitor_loop` (Z. ~535)
- Create: `backend/tests/services/conftest.py`
- Modify: `backend/tests/services/test_power_manager.py`

**Interfaces:**
- Produces: `config_store.list_active_demands(*, strict: bool = False) -> List[PowerDemandInfo]` — Standard wie heute (DB-Fehler → Warnung, `[]`); mit `strict=True` wird der Fehler weitergereicht. Die übrigen neun Aufrufer bleiben unverändert.
- Produces: `PowerManagerService._refresh_demand_cache(self) -> bool` — liest mit `strict=True`; True genau dann, wenn sich `{source: level}` gegenüber dem bisherigen Cache geändert hat; bei DB-Fehler (Ausnahme gefangen, DEBUG-Log wie heute) False und Cache unverändert. `async PowerManagerService._sync_demands_from_db(self) -> None` — unter `self._state_lock`: Cache auffrischen, bei Änderung `await self._recalculate_profile("demand_sync")`. `_monitor_loop` ruft `_sync_demands_from_db()` an der Stelle von `_refresh_demand_cache()`.
- Produces (Test-Infrastruktur): Fixture `power_tables_in_global_db` in `tests/services/conftest.py` — Inhalt der heutigen autouse-Fixture `_power_tables_in_global_db` aus `test_power_manager.py`, Tabellenliste um `PowerDemandLog.__table__` ergänzt, beim Aufräumen auch `PowerDemandLog` leeren. In `test_power_manager.py` per `pytestmark = pytest.mark.usefixtures("power_tables_in_global_db")` weiter für alle Tests aktiv.

- [ ] **Step 1: Fixture verschieben, bestehende Suite bleibt grün**

Run: `cd backend && python -m pytest tests/services/test_power_manager.py -q`
Expected: gleiche Anzahl passed wie vorher

- [ ] **Step 2: Tests schreiben** (neue Klasse `TestDemandsWrittenByOtherProcesses` in `test_power_manager.py`; die autouse-Fixture `reset_singleton` und die Fixture `service` aus `TestPowerManagerServiceDemands` (Z. 266-280) übernehmen, `service` zusätzlich mit `service._primary = True`, `service._current_profile = PowerProfile.IDLE`)

```python
def _write_backup_demand():
    now = datetime.now(timezone.utc)
    upsert_demand(source="scheduler:backup", level=PowerProfile.SURGE,
                  power_property=ServicePowerProperty.SURGE, registered_at=now,
                  expires_at=now + timedelta(hours=1), description="x")

async def test_primary_applies_a_demand_another_process_wrote(self, service):
    _write_backup_demand()
    await service._sync_demands_from_db()
    assert service._current_profile == PowerProfile.SURGE

async def test_primary_drops_back_when_the_row_is_deleted(self, service):
    _write_backup_demand()
    await service._sync_demands_from_db()
    delete_demand("scheduler:backup")
    await service._sync_demands_from_db()
    assert service._current_profile == PowerProfile.IDLE

async def test_unchanged_demands_do_not_recalculate(self, service, monkeypatch):
    _write_backup_demand()
    await service._sync_demands_from_db()          # erster Sync: Änderung, rechnet
    spy = AsyncMock()
    monkeypatch.setattr(service, "_recalculate_profile", spy)
    await service._sync_demands_from_db()          # zweiter Sync: nichts geändert
    spy.assert_not_awaited()

async def test_db_error_keeps_cache_and_profile(self, service, monkeypatch):
    _write_backup_demand()
    await service._sync_demands_from_db()
    assert service._current_profile == PowerProfile.SURGE
    def broken(*, strict=False):
        raise OperationalError("SELECT", {}, Exception("db weg"))
    monkeypatch.setattr(manager_module, "list_active_demands", broken)
    spy = AsyncMock()
    monkeypatch.setattr(service, "_recalculate_profile", spy)
    await service._sync_demands_from_db()
    spy.assert_not_awaited()
    assert "scheduler:backup" in service._demands
    assert service._current_profile == PowerProfile.SURGE

def test_monitor_loop_uses_the_sync(self):
    src = inspect.getsource(PowerManagerService._monitor_loop)
    assert "_sync_demands_from_db" in src and "_refresh_demand_cache" not in src
```
(`manager_module` = `app.services.power.manager`; `OperationalError` aus `sqlalchemy.exc`. Den Helfer `_write_backup_demand` in den ersten beiden Tests statt des ausgeschriebenen `upsert_demand` verwenden.)

- [ ] **Step 3: Ausführen, muss fehlschlagen**

Run: `cd backend && python -m pytest tests/services/test_power_manager.py -k OtherProcesses -v`
Expected: FAIL (`_sync_demands_from_db` fehlt; `test_monitor_loop_uses_the_sync` findet `_refresh_demand_cache` im Loop)

- [ ] **Step 4: Umsetzen** — `list_active_demands(*, strict=False)`: im `except` bei `strict` erneut werfen. `_refresh_demand_cache` liest mit `strict=True` und vergleicht `{s: d.level for s, d in alt.items()}` mit dem neu geladenen Stand; `_monitor_loop` ruft `await self._sync_demands_from_db()`. Docstring von `register_demand` bleibt (stimmt jetzt).

- [ ] **Step 5: Ausführen, alles grün; Commit**

Run: `cd backend && python -m pytest tests/services/test_power_manager.py tests/services/power -q && python -m ruff check app/services/power tests/services`
```bash
git add backend/app/services/power/config_store.py backend/app/services/power/manager.py backend/tests/services/conftest.py backend/tests/services/test_power_manager.py
git commit -m "fix(power): Primary wendet Demands anderer Prozesse an"
```

### Task C2: Scheduler schreibt seine Demand direkt

**Files:**
- Create: `backend/app/services/scheduler/power_demand.py`
- Modify: `backend/app/services/scheduler/worker.py` — `SCHEDULER_POWER_LEVELS` (Z. 42-53) entfernen und **nicht** wieder importieren (nach der Delegation unbenutzt → F401; sonst nutzt ihn niemand); `_register_power_demand`/`_unregister_power_demand` (Z. 188-244) delegieren an `register_scheduler_demand`/`unregister_scheduler_demand`, Methodennamen und Aufrufstellen bleiben
- Modify: `backend/app/services/CLAUDE.md` — unter `scheduler/` eine Zeile für `power_demand.py` („Scheduler jobs register power demands by writing `power_demands` directly; the primary applies them on its next 5 s tick. No HTTP, no token — scheduler jobs never wake soft sleep")
- Create: `backend/tests/services/test_scheduler_power_demand.py`

**Interfaces:**
- Consumes: `config_store.upsert_demand`, `config_store.delete_demand`, `config_store.persist_demand_log`, `config_store.list_active_demands` (alle sync, öffnen eigene Session); Fixture `power_tables_in_global_db` (Task C1)
- Produces (in `scheduler/power_demand.py`):
  - `SCHEDULER_POWER_LEVELS: dict[str, str]` — Inhalt wie heute, außer `"sync_check": "idle"` und `"auto_update": "idle"` (Begründung unter „Fix", Punkt 2)
  - `DEMAND_TIMEOUT_S = 3600`
  - `register_scheduler_demand(name: str) -> bool` — für unbekannte oder `idle`-Jobs `False` ohne DB-Zugriff; sonst `upsert_demand(source=f"scheduler:{name}", level=PowerProfile(level), power_property=ServicePowerProperty(level), registered_at=jetzt (UTC), expires_at=jetzt + DEMAND_TIMEOUT_S, description=f"Scheduler job: {name}")`, danach `persist_demand_log(action="registered", …, resulting_profile="pending", timeout_seconds=DEMAND_TIMEOUT_S)`; Rückgabe = Ergebnis von `upsert_demand`
  - `unregister_scheduler_demand(name: str) -> None` — für unbekannte oder `idle`-Jobs nichts; sonst `delete_demand(source)`, bei `True` `persist_demand_log(action="unregistered", …, resulting_profile="pending")`
  - `"pending"`, weil der Scheduler das Ergebnis nicht kennt: der Primary entscheidet beim nächsten Tick (≤ 5 s, Task C1).

- [ ] **Step 1: Tests schreiben** (`pytestmark = pytest.mark.usefixtures("power_tables_in_global_db")`)

```python
def _no_http(*a, **kw):
    raise AssertionError("Scheduler darf für Demands kein HTTP benutzen")

def test_register_writes_the_row_without_http(monkeypatch):
    monkeypatch.setattr(requests, "post", _no_http)
    monkeypatch.setattr(requests, "delete", _no_http)
    assert register_scheduler_demand("backup") is True
    d = {x.source: x for x in list_active_demands()}["scheduler:backup"]
    assert d.level == PowerProfile.SURGE
    assert d.expires_at - d.registered_at == timedelta(seconds=3600)

def test_unregister_removes_the_row():
    register_scheduler_demand("backup")
    unregister_scheduler_demand("backup")
    assert "scheduler:backup" not in {x.source for x in list_active_demands()}

def test_idle_and_unknown_jobs_register_nothing():
    for name in ("sync_check", "auto_update", "notification_check", "gibt_es_nicht"):
        assert register_scheduler_demand(name) is False
    assert list_active_demands() == []

def test_worker_has_no_http_loopback_for_demands():
    src = inspect.getsource(app.services.scheduler.worker)
    assert "/api/power/demands" not in src and "X-Service-Token" not in src

def test_worker_methods_delegate(monkeypatch):
    import app.services.scheduler.worker as worker_module
    calls = []
    monkeypatch.setattr(worker_module, "register_scheduler_demand", lambda n: calls.append(("reg", n)) or True)
    monkeypatch.setattr(worker_module, "unregister_scheduler_demand", lambda n: calls.append(("unreg", n)))
    w = worker_module.SchedulerWorker()        # Konstruktor ist leichtgewichtig
    w._register_power_demand("backup")
    w._unregister_power_demand("backup")
    assert calls == [("reg", "backup"), ("unreg", "backup")]
```

- [ ] **Step 2: Ausführen, muss fehlschlagen**

Run: `cd backend && python -m pytest tests/services/test_scheduler_power_demand.py -v`
Expected: FAIL (`ImportError` für `app.services.scheduler.power_demand`)

- [ ] **Step 3: Umsetzen** — Modul anlegen; in `worker.py` die beiden Methoden auf je einen Aufruf reduzieren, `import requests as http_requests` dort entfernen, falls sonst unbenutzt.

- [ ] **Step 4: Ausführen, alles grün; Commit**

Run: `cd backend && python -m pytest tests/services/test_scheduler_power_demand.py tests/services -k "scheduler or power" -q && python -m ruff check app/services/scheduler tests/services`
```bash
git add backend/app/services/scheduler/power_demand.py backend/app/services/scheduler/worker.py backend/app/services/CLAUDE.md backend/tests/services/test_scheduler_power_demand.py
git commit -m "fix(scheduler): Power-Demands direkt in die DB statt per HTTP-Loopback"
```

### Task C3: Service-Token-Pfad entfernen

**Files:**
- Modify: `backend/app/api/routes/power.py` — `_get_admin_or_service_token` (Z. 24-~70) und `_oauth2_scheme` (Z. 21) entfernen; danach unbenutzt und zu entfernen (sonst F401): `secrets`, `Optional`, `OAuth2PasswordBearer`, `settings` (Z. 8-21). `register_power_demand` und `unregister_power_demand` nehmen `current_user: UserPublic = Depends(deps.get_current_admin)`
- Modify: `backend/app/core/config.py` — Feld `scheduler_service_token` (Z. 170) und Block Z. 332-335 entfernen (`extra="ignore"`: eine übrig gebliebene Env-Variable stört nicht)
- Delete: `backend/tests/test_service_token_compare.py`
- Modify: `backend/tests/api/test_power_routes.py` (neuer Test; Docstring von `_patch_session_local`, Z. 15-25, nennt `_get_admin_or_service_token` — auf „Code in den Power-Routen, der `SessionLocal()` selbst öffnet" umformulieren, Fixture bleibt)

**Verhaltensänderung (Ausnahme zur globalen Regel „kein Verhaltenswechsel an Antworten"):** `deps.get_current_admin` statt eigener JWT-Prüfung. Gleich bleiben 401 ohne Anmeldung, 403 für Nicht-Admins, 401 für unbekannte Nutzer und 2FA-pending-Tokens. Neu: ein **inaktiver** Admin mit gültigem Token wird abgewiesen (vorher angenommen — die alte Prüfung kannte `is_active` nicht); ein Admin-API-Key wird angenommen; Fehltexte und `WWW-Authenticate` folgen dem Standard; Fehlversuche landen im Audit-Log wie bei allen Admin-Routen.

**Interfaces:**
- Consumes: Task C2 (kein Aufrufer sendet mehr `X-Service-Token`)

- [ ] **Step 1: Tests schreiben** (`tests/api/test_power_routes.py`, Klasse der Demand-Tests)

```python
def test_service_token_header_no_longer_authenticates(self, client: TestClient):
    response = client.post(
        "/api/power/demands",
        json={"source": "x", "level": "medium"},
        headers={"X-Service-Token": "irgendwas"},
    )
    assert response.status_code == 401

def test_no_service_token_path_left():
    root = Path(__file__).resolve().parents[2] / "app"
    for rel in ("api/routes/power.py", "core/config.py", "services/scheduler/worker.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert "X-Service-Token" not in src and "scheduler_service_token" not in src, rel
```
(Der erste Test ist vorher wie nachher 401 — das Token ist heute zufällig; er hält fest, dass es so bleibt, auch wenn jemand `SCHEDULER_SERVICE_TOKEN` setzt. Rot ist vorher der zweite.)

- [ ] **Step 2: Ausführen, muss fehlschlagen**

Run: `cd backend && python -m pytest tests/api/test_power_routes.py -k "service_token" -v`
Expected: FAIL in `test_no_service_token_path_left` (`api/routes/power.py`)

- [ ] **Step 3: Entfernen und umstellen**, `tests/test_service_token_compare.py` löschen, Docstring anpassen.

- [ ] **Step 4: Ausführen, alles grün; Commit**

Run: `cd backend && python -m pytest tests/api/test_power_routes.py -q && python -m ruff check app tests`
```bash
git add -A backend/app/api/routes/power.py backend/app/core/config.py backend/tests/api/test_power_routes.py backend/tests/test_service_token_compare.py
git commit -m "refactor(power): Service-Token-Pfad entfernen, Demand-Routen nur für Admins"
```

### Task C4: Eskalation wartet auf laufende Scheduler-Jobs

**Files:**
- Modify: `backend/app/services/power/scheduled_reboot.py:93` — `_another_scheduler_job_running` → öffentlich `another_scheduler_job_running(db: Session, own_execution_id: Optional[int] = None) -> bool`, Aufrufstelle Z. 152 anpassen
- Modify: `backend/app/services/power/sleep.py` — neue Methode, Prüfung in `_escalation_monitor` (Z. ~1068-1118) nach dem Fremd-Inhibitor-Gate
- Modify: `backend/app/services/CLAUDE.md` — Zeile `sleep.py`: ein Satz „auto-escalation is skipped while a scheduler job is running (same gate as the scheduled reboot)"
- Create: `backend/tests/services/test_sleep_escalation_scheduler_gate.py` (Muster: `tests/services/test_sleep_foreign_inhibitor_integration.py:133-150`, `_build_service()`/`_config()` von dort übernehmen)

**Interfaces:**
- Consumes: Tasks C1–C3 nicht; unabhängig, gehört aber in denselben PR, weil erst C2 den Soft-Sleep lange genug für die Eskalation macht.
- Produces: `SleepManagerService._scheduler_job_running(self) -> bool` — sync; eigene `SessionLocal()`, ruft `another_scheduler_job_running(db)`; bei jeder Ausnahme `True` (fail-closed) mit WARNING-Log. In `_escalation_monitor`: `if await asyncio.to_thread(self._scheduler_job_running): logger.info("Auto-escalation skipped: scheduler job running"); return` — wie die übrigen Gates einmalig, kein Neuversuch in diesem Soft-Sleep.

- [ ] **Step 1: Tests schreiben**

```python
async def _run_escalation(svc, *, job_running):
    cfg = _config(auto_escalation_enabled=True)
    svc._current_state = SleepState.SOFT_SLEEP
    svc._is_running = True
    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_is_always_awake", return_value=False), \
         patch.object(svc, "_is_user_present", return_value=False), \
         patch.object(svc, "_is_gaming_active", return_value=False), \
         patch.object(svc, "_foreign_inhibitor", return_value=None), \
         patch.object(svc, "_scheduler_job_running", return_value=job_running), \
         patch.object(svc, "enter_true_suspend", new=AsyncMock()) as mock_suspend, \
         patch("app.services.power.sleep.asyncio.sleep", new=AsyncMock()):
        await svc._escalation_monitor()
    return mock_suspend

async def test_escalation_skipped_while_a_scheduler_job_runs():
    (await _run_escalation(_build_service(), job_running=True)).assert_not_called()

async def test_escalation_proceeds_without_a_running_job():
    (await _run_escalation(_build_service(), job_running=False)).assert_awaited_once()

def test_unreadable_scheduler_state_counts_as_running(monkeypatch):
    def broken(db, own_execution_id=None):
        raise OperationalError("SELECT", {}, Exception("db weg"))
    monkeypatch.setattr("app.services.power.scheduled_reboot.another_scheduler_job_running", broken)
    assert _build_service()._scheduler_job_running() is True
```
(Falls `sleep.py` die Funktion per `from … import` bindet, den Patch auf den Namen in `app.services.power.sleep` setzen.)

- [ ] **Step 2: Ausführen, muss fehlschlagen**

Run: `cd backend && python -m pytest tests/services/test_sleep_escalation_scheduler_gate.py -v`
Expected: FAIL (`_scheduler_job_running` fehlt)

- [ ] **Step 3: Umsetzen** — Umbenennung, Methode, Gate.

- [ ] **Step 4: Ausführen, alles grün; Commit**

Run: `cd backend && python -m pytest tests/services/test_sleep_escalation_scheduler_gate.py tests/services -k "sleep or reboot" -q && python -m ruff check app/services/power tests/services`
```bash
git add backend/app/services/power/scheduled_reboot.py backend/app/services/power/sleep.py backend/app/services/CLAUDE.md backend/tests/services/test_sleep_escalation_scheduler_gate.py
git commit -m "fix(sleep): Eskalation zum Suspend wartet auf laufende Scheduler-Jobs"
```

### Abschluss Teil C

- [ ] Volle Suite (Sandbox/CI) und `python -m ruff check app tests` grün.
- [ ] PR `fix/scheduler-power-demands` → `main`, Text mit „Befund", „Fix" und dem Absatz „Politik" oben, `Refs #314`. Ausdrücklich nennen:
  - Scheduler-Jobs wecken das NAS nicht mehr aus dem Soft-Sleep; sie laufen dort mit ihrer Demand weiter. Der Soft-Sleep hält dadurch erstmals länger als 5 min, die 30-min-Eskalation greift (mit Gate C4).
  - Demands, die auf Followern registriert werden (`@requires_power`, 3 von 4 Anfragen), wirken jetzt — mehr Profilwechsel und `power_profile_logs`-Zeilen; ein manuelles Profil wird von jeder solchen Demand überschrieben.
  - `sync_check` und `auto_update` melden keine Demand mehr an.
  - Auth der Demand-Routen: siehe Task C3.
- [ ] **Vor dem Deploy:** Sleep-Konfiguration noch einmal lesen (Stand 26.11.: Eskalation an, 30 min; Spindown aus). Ist inzwischen `disk_spindown_enabled` an, wird #876 mit diesem Deploy akut — dann #876 vorziehen oder im PR als bekannte Lücke nennen.
- [ ] **Nach dem Deploy prüfen:**
  - Journal `baluhost-scheduler`: kein `Power demand registration failed` mehr.
  - Journal `baluhost-backend`: kein `auto_wake: POST /api/power/demands` / `DELETE /api/power/demands` mehr; Soft-Sleep-Phasen dauern länger als 5 min; bei Eskalation während eines Jobs `Auto-escalation skipped: scheduler job running`.
  - Bei einem stündlichen Job (z. B. `upload_cleanup`, Level `low`): `power_demand_logs` bekommt `registered`/`unregistered` mit Quelle `scheduler:upload_cleanup`.
