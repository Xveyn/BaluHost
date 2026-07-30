# S1 — Sync-SQLAlchemy raus aus dem Event-Loop

**Datum:** 2026-07-30
**Issue:** [#300](https://github.com/Xveyn/BaluHost/issues/300) (`[S1] 🟠 Sync-SQLAlchemy blockiert den Event-Loop in async-Routen`), Teil von [#298](https://github.com/Xveyn/BaluHost/issues/298)
**Status:** Design freigegeben, Umsetzung ausstehend

---

## Problem

377 Route-Handler sind `async def`, nehmen `Depends(get_db)` und führen synchrone
SQLAlchemy-Queries aus. Bei 314 davon enthält der Body **kein einziges** `await`,
`async with` oder `async for` — sie sind ohne Verhaltensänderung zu `def`
konvertierbar, laufen dann im FastAPI-Threadpool statt auf dem Event-Loop.

Solange sie `async def` sind, blockiert jede DB-Query den kompletten Event-Loop
ihres Workers. Betroffen ist nicht nur die eigene Latenz, sondern alles, was im
selben Worker auf dem Loop lebt: WebSocket-Broadcasts, der SSE-Log-Stream und
`/api/health`.

**Verifizierter Extremfall:** `backend/app/api/routes/monitoring.py:159`
(`get_cpu_history`) — `async def`, zieht über
`orchestrator.cpu_collector.get_history_db()` (Z. 178/182) bis zu 10.000 Samples
synchron aus der DB und wird von den Monitoring-Dashboards gepollt.

### Eigene Messung (2026-07-30, `main` @ `fdebd887`)

AST-Analyse über alle 67 Module in `backend/app/api/routes/`. Die Zahlen im Issue
(399 / 573 / 89) stammen aus einer Textsuche; die 89 „def" enthielten alle
Modul-Funktionen inklusive Helper. Echte Sync-Handler sind 24.

| Kennzahl | Wert |
|---|---|
| Route-Handler gesamt | 588 |
| davon `async def` | 564 |
| davon `def` (läuft bereits im Threadpool) | 24 |
| `async def` **mit** `Depends(get_db)` | 377 |
| davon **ohne jedes `await`** im Body | **314** ← Umfang dieses Specs |
| davon mit echtem `await` | 63 |

Verteilung der 314 auf 47 Dateien; nach HTTP-Methode: 153 GET, 96 POST, 30 PUT,
24 DELETE, 11 PATCH — also **153 read-only, 161 mutierend**.

Weitere 105 Handler sind `async def` ohne `await`, aber **ohne** `Depends(get_db)`.
Die gehören nicht hierher: sync-`subprocess.run` im async-Pfad ist
[#302](https://github.com/Xveyn/BaluHost/issues/302) (S2).

### Risiko-Scan der 314 Kandidaten

- **0 Treffer** für `asyncio.*`, `create_task`, `get_event_loop`,
  `run_in_threadpool`, `StreamingResponse`, `anyio.*` in den Bodies.
- 308 tragen `@user_limiter.limit` / `@limiter.limit`. slowapi hat einen
  expliziten `sync_wrapper` (`slowapi/extension.py:752`) — unkritisch.
- **2 tragen `@requires_power`** — siehe Etappe C.
- 6 haben `BackgroundTasks` in der Signatur (`cloud.py:383`,
  `cloud_export.py:27` und `:125`, `migration.py:108`, `:147`, `:176`).
  Starlette führt sync Background-Funktionen im Threadpool aus — kein Eingriff,
  nur im Review zu bestätigen.
- Nebeneffekt in die richtige Richtung: es existieren sync Service-Wrapper mit
  `loop.run_until_complete(...)` (`services/versioning/cache.py:377-406`,
  `services/pihole/service.py`) und `asyncio.run(...)`
  (`services/setup/service.py:124`). Die funktionieren **nur** außerhalb des
  Loop-Threads. Die Umstellung entschärft sie, statt sie zu brechen.

---

## Ziel und Erfolgskriterium

Kein Route-Handler mehr, der `async def` deklariert, `Depends(get_db)` nimmt und
in seinem eigenen Body nie awaitet.

Erfolg ist **gemessen, nicht behauptet**. Leitkennzahl ist der **Event-Loop-Lag**:
ein Task schläft 250 ms und misst die Überschreitung der Sollzeit. Der
Vorher/Nachher-Vergleich aus demselben Log ist der Abnahmebeleg für #300.

---

## Architektur: zwei PRs

### PR1 — Instrumentierung (`feat/s1-concurrency-probe`)

Additiv, kein Verhaltenswechsel an bestehenden Routen.

| Baustein | Ort | Zweck |
|---|---|---|
| In-Flight-Zähler | `backend/app/middleware/inflight.py`, **pure ASGI** | Gleichzeitige Requests pro Worker, Ankunftsrate, Handler-Dauer |
| Loop-Lag-Sonde | `backend/app/core/concurrency_probe.py` | `sleep(0.25)`-Überschuss → p50 / p95 / max |
| Pool-Ableser | dito | `engine.pool.status()` → `checked_out`, `overflow`; Zähler für Pool-Timeouts |
| Threadpool-Ableser | dito | anyio `current_default_thread_limiter().statistics()` → `borrowed_tokens`, `tasks_waiting` |
| Reporter | dito | Eine JSON-Logzeile pro 60 s auf Logger `baluhost.concurrency`, mit High-Water-Marks pro Fenster |

**Pure ASGI statt `BaseHTTPMiddleware`** ist Absicht. Der Stack hat bereits 8
`BaseHTTPMiddleware` — das ist als K9 ([#334](https://github.com/Xveyn/BaluHost/issues/334))
erfasst. Es wäre widersinnig, den Overhead ausgerechnet mit dem Werkzeug zu
messen, das ihn erzeugt.

**Der Sonden-Task wird referenziert und im Shutdown gecancelt.** K2
([#320](https://github.com/Xveyn/BaluHost/issues/320)) listet 5 unreferenzierte
`create_task`-Loops ohne Cancel — dieser Spec fügt keinen sechsten hinzu.

Die Sonde läuft auf **jedem** Worker, nicht nur dem primären: der gesuchte Effekt
ist per-Worker. Intervall über Env konfigurierbar (Default 60 s), abschaltbar.
Logvolumen: 1 Zeile/min × 4 Worker ≈ 5.760 Zeilen/Tag in journald — vertretbar.

Dabei wird `baluhost_database_connections` (`api/routes/metrics.py:255`) endlich
befüllt. Die Gauge ist seit v1.2 deklariert und in `docs/monitoring/MONITORING.en.md`
dokumentiert, wird aber **nirgends** je `.set()`. Es ist dieselbe Messung.

**Danach: deployen, 3–7 Tage Normalbetrieb, Zahlen sichten.** Erst dann PR2.

### PR2 — Der Sweep (`refactor/s1-sync-db-routes`)

Alle 314 Handler in einem PR, intern in Etappen A–F gegliedert.

---

## Warum die Zahlen die Grenzen bestimmen müssen

Heute serialisiert der blockierte Loop faktisch auf eine DB-Query pro Worker.
Nach dem Sweep gilt pro Worker `min(anyio-Threadpool 40, Pool 10 + 20 Overflow = 30)`.

| Ebene | Wert (gemessen) |
|---|---|
| anyio-Default-Threadpool | 40 Tokens pro Event-Loop |
| PG-Pool pro Worker | `pool_size=10` + `max_overflow=20` = 30 (`core/database.py:43-45`) |
| Backend-Worker | 4 (`deploy/install/templates/baluhost-backend.service:26`) |
| Zusätzliche Prozesse mit eigenem Pool | 3 Sidecar-Units (monitoring, scheduler, webdav) |
| PostgreSQL `max_connections` | **ungetunt** — `06-postgresql.sh` setzt es nie, Debian-Default 100 |

4 × 30 = **120 mögliche Verbindungen allein aus dem Backend**, gegen ein Limit von
100. Ohne Etappe D verwandelt der Sweep ein Latenzproblem in
`FATAL: sorry, too many clients already`.

### Methodische Einschränkung

Der gemessene In-Flight-Peak ist **nach unten verzerrt**: bei blockiertem Loop
stauen sich Requests vor dem Accept, statt als „in flight" gezählt zu werden.
Unverzerrt messbar sind Ankunftsrate und Bedienzeit. Die Auslegung der Grenzen
erfolgt deshalb über

```
Nebenläufigkeit ≈ Ankunftsrate × Bedienzeit    (Little's Law)
```

und nimmt den gemessenen Peak ausdrücklich nur als **untere Schranke**. Wer die
Grenzen direkt aus dem Peak ableitet, leitet sie aus einer geschönten Zahl ab.

---

## Etappen in PR2

### A — Werkzeug und Wächter

Codemod-Skript unter `backend/scripts/debug/`, das genau die AST-identifizierte
Menge von `async def` auf `def` flippt. Reproduzierbarkeit ist das Review-Kriterium:
Skript erneut laufen lassen → leeres Diff.

Dazu ein Meta-Test `backend/tests/test_route_async_convention.py`:

> Ein `async def`-Route-Handler mit `Depends(get_db)` muss mindestens ein `await`,
> `async with` oder `async for` im **eigenen** Body enthalten (verschachtelte
> Funktionen zählen nicht).

Mit expliziter, begründeter Allowlist. Nach Etappe C soll sie leer sein.

### B — Die 153 GET-Handler

Read-only, keine Write-Races möglich. Die risikoärmste Hälfte zuerst.

### C — Die 161 mutierenden Handler

**Vorbedingung: `requires_power` dual-mode machen.** Der Decorator ist heute
async-only — `core/power_rating.py:97` macht `return await func(*args, **kwargs)`.
Ein async Wrapper um einen sync Body würde die Blockade nur eine Ebene nach oben
schieben, weil FastAPI dann den async Wrapper sieht und auf dem Loop ausführt. Der
Wrapper muss einen sync Callee erkennen (`inspect.iscoroutinefunction`) und über
`starlette.concurrency.run_in_threadpool` dispatchen.

Betroffene Kandidaten: `backup.py:32` (`create_backup`) und `backup.py:172`
(`restore_backup`). Von den insgesamt 10 `@requires_power`-Routen (weitere in
`files.py:693` und `system_raid.py`) fallen nur diese beiden in die
Kandidatenmenge; die übrigen 8 bleiben unverändert.

**Begrenzte Race-Durchsicht.** Die heutige Serialisierung wirkt als unfreiwilliger
Mutex. Read-Modify-Write ohne Transaktionsschutz (Quota-Prüfungen, Zähler,
Share-Erzeugung) kann nach dem Sweep real werden. Vorgehen: per Skript eine
Shortlist der mutierenden Handler erzeugen, die `db.query(...)` gefolgt von
`db.add(...)`/`db.commit()` auf derselben Entität ausführen, und diese durchsehen.

Das ist ausdrücklich eine **Urteilsrunde, kein Vollbeweis**. Gefundene echte Races
werden nach der Projektkonvention **als GitHub-Issue gemeldet, nicht still
mitgefixt**.

### D — Grenzen setzen

Auf Basis der PR1-Zahlen:

- anyio-Threadpool-Tokens pro Worker explizit setzen (im Lifespan-Startup).
- `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` im `.env`-Template setzen.
- Invariante, die einzuhalten ist:
  `4 × (DB_POOL_SIZE + DB_MAX_OVERFLOW) + Sidecar-Bedarf < max_connections`.

`06-postgresql.sh` (`max_connections` anheben) **nur**, wenn die Zahlen es
erzwingen. Das Modul läuft bei einem normalen `ci-deploy` nicht erneut — es wäre
ein manueller Ops-Schritt auf BaluNode und damit ein Kandidat fürs Vergessen
(dasselbe Muster wie beim Marketplace-Pubkey).

### E — Konvention verschriftlichen

`.claude/rules/backend/coding-style.md` sagt heute „**Async/await** for all I/O
operations". Das ist genau die Regel, aus der der Fehler folgt. Sie muss zu einer
Formulierung werden, die zwischen echtem async-I/O und synchronem DB-Zugriff
trennt: kein sync-I/O in `async def`; DB-lastige Handler ohne await-Bedarf sind
`def` und laufen im Threadpool.

Ebenfalls anzupassen: `backend/app/api/CLAUDE.md` (Abschnitt „Adding a New Route")
und `backend/app/core/CLAUDE.md` (Abschnitt „DB sessions").

### F — Verifikation

- Volle Backend-Suite grün, `ruff` grün.
- Frontend unberührt.
- Nach dem Deploy: Loop-Lag-Vergleich gegen die PR1-Baseline aus demselben Log.
- Dev-Smoke-Test (siehe unten).

---

## Dev (SQLite) vs. Prod (PostgreSQL)

| | Dev | Prod |
|---|---|---|
| Engine | SQLite, WAL, `check_same_thread=False`, `busy_timeout=30000` | PostgreSQL 17.7 |
| Pool | `QueuePool` 5 + 10 (SQLAlchemy-Default) | `QueuePool` 10 + 20 pro Worker |
| Prozesse | 1 (uvicorn `--reload`) | 4 Worker + 3 Sidecars |
| Was nach dem Sweep neu ist | erstmals echte Schreib-Nebenläufigkeit | erstmals echte Verbindungs-Nebenläufigkeit |

Dev bekommt zum ersten Mal parallele Writer. WAL erlaubt einen Writer und beliebig
viele Reader; `PRAGMA busy_timeout=30000` (`core/database.py:25`) fängt den
Normalfall ab, indem ein Writer wartet statt zu scheitern.

Das zweite Netz — `commit_with_retry` (`core/database.py:140`) — ist faktisch nicht
gespannt: **0 von 46** `db.commit()`-Aufrufen in Routen und **14 von 321** in
Services nutzen es. Solange der Loop serialisiert, fällt das nicht auf.

**Entscheidung:** kein Flächeneinbau von `commit_with_retry` in diesem Spec — das
wäre ein eigener Task mit eigenem Risiko. Stattdessen in Etappe F ein
Dev-Smoke-Test, der ein Write-Endpoint aus N Threads trifft und zeigt, ob
`busy_timeout` allein trägt. Ergebnis kommt in die Etappen-Notiz; trägt es nicht,
ist das ein eigenes Issue.

---

## Fehlerbehandlung

Kein neues Verhalten. `HTTPException` und `ServiceError` funktionieren in sync
Handlern identisch; der globale 5xx-Scrubber (`core/exception_handlers.py`) bleibt
unberührt. Rate-Limiting bleibt wirksam (slowapi `sync_wrapper`).

Die einzige neue Fehlerklasse ist Pool-Erschöpfung — `TimeoutError` nach
`pool_timeout=30` beziehungsweise `FATAL: sorry, too many clients already` auf
PG-Seite. Genau die verhindert Etappe D, und die Sonde aus PR1 zählt sie mit.

---

## Tests

**PR1**

- Unit-Tests für Sonde und Reporter: Fenster-Aggregation, High-Water-Reset,
  kein Crash wenn `engine.pool` keine `status()`-Fähigkeit hat (z. B. `NullPool`
  in Tests).
- Test, dass der Sonden-Task im Shutdown tatsächlich gecancelt wird.
- Test, dass die In-Flight-Middleware Requests korrekt inkrementiert/dekrementiert,
  auch wenn der Handler eine Exception wirft.

**PR2**

- Bestehende Backend-Suite bleibt grün — sie ist das Hauptnetz und deckt einen
  Großteil der 314 Routen ab.
- Meta-Test aus Etappe A (Konvention, ratchet-fähig).
- `requires_power` mit sync Endpoint: Demand wird registriert und in `finally`
  wieder entlassen.
- Dev-Smoke: paralleler Write auf SQLite aus N Threads.

---

## Rollback

PR2 ist ein Revert ohne Datenmigration — es gibt keine Schema-Änderung und keinen
persistierten Zustand. PR1 ist rein additiv und unabhängig zurücknehmbar.

---

## Ausdrücklich nicht in diesem Spec

- **async-SQLAlchemy** (`AsyncSession`, async Engine). Die im Issue genannte
  Langfristvariante beträfe 377 Route-Signaturen plus die gesamte Service-Schicht
  und ist ein eigener XL-Track.
- **Die 105 `async def`-Handler ohne `Depends(get_db)`.** Sync-`subprocess.run`
  im async-Pfad ist S2 ([#302](https://github.com/Xveyn/BaluHost/issues/302)).
- **Flächeneinbau von `commit_with_retry`** (siehe oben).
- **Die übrigen toten Prometheus-Metriken.** `database_query_duration_seconds`,
  `http_requests_total` und `users_active_sessions` sind ebenfalls deklariert und
  werden nie gesetzt. Nur `database_connections` wird hier befüllt, weil es
  dieselbe Messung ist; der Rest ist ein separater Befund.
