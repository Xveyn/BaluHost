# Plugin-Aktivierung über Worker hinweg — Design

**Datum:** 2026-07-23
**Status:** entworfen, abgenommen
**Issue:** #448
**Anlass:** In Produktion beobachtet, nachdem Teilprojekt 2 (#457) ausgeliefert war.

## Das Symptom

Ein Admin aktiviert `steam_gaming` unter *Plugins*, lädt die Seite hart neu — und das Plugin steht wieder auf **deaktiviert**. Beim nächsten Reload womöglich wieder auf aktiviert. Der Zustand scheint zu springen.

## Root Cause (gemessen, nicht vermutet)

Der Schreibpfad ist in Ordnung. `POST /api/plugins/{name}/toggle` schreibt `is_enabled=True` in die Tabelle `installed_plugins` (`routes/plugins.py:329`, `plugin_service.enable_plugin`). Das ist der einzige worker-übergreifende Zustand, und er stimmt.

Der **Lesepfad** ist der Fehler. Jede „ist aktiviert?"-Frage wird aus `PluginManager._enabled` beantwortet — einer **prozess-lokalen** Menge:

| Fundort | Zeile |
|---|---|
| `get_all_plugins()` (speist `GET /api/plugins`) | `manager.py:910`, `:934` |
| `get_ui_manifest()` (speist `GET /api/plugins/ui/manifest`) | `manager.py:799` |
| `is_enabled()` | `manager.py:873` |
| `iter_enabled_plugins()` (Status-Bar-Pills, Menü-Aktionen) | `manager.py:859` |

`_enabled` wird beim Start jedes Workers aus der DB befüllt (`load_enabled_plugins`, `manager.py:696`) — deshalb heilt ein Neustart das Problem. Ein Toggle zur Laufzeit erreicht dagegen nur **den einen** Worker, der die Anfrage bearbeitet hat (`manager.py:341` im Toggle-Handler); `invalidate_plugin_cache(name)` ebenso.

**Auf der Prod-Box gemessen** (`ps -eo pid,ppid,cmd`):

```
792957  1  /opt/baluhost/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 ...
```

Vier Worker. Der Toggle landet auf einem davon, der Reload auf einem zufälligen — **etwa drei von vier Aufrufen zeigen den falschen Zustand**. Genau das beobachtete Bild.

*Messhinweis für später:* `pgrep -fa uvicorn | wc -l` liefert hier `2` und ist irreführend — Uvicorns Kindprozesse tragen „uvicorn" nicht in der Kommandozeile (sie entstehen über `multiprocessing`). Nur Master und ein fremder `open_webui`-Prozess matchen. Die Worker-Zahl kommt aus dem `--workers`-Argument, nicht aus einer Prozesszählung.

## Der eigentliche Konstruktionsfehler

`_enabled` beantwortet heute **zwei verschiedene Fragen** mit einem Feld:

1. *Ist dieses Plugin laut Konfiguration aktiviert?* — eine globale Tatsache, die in der DB steht.
2. *Hat dieser Worker die Plugin-Instanz geladen und gestartet?* — eine lokale Tatsache.

Solange beide immer gleich waren (Zustand nur beim Start gesetzt), fiel das nicht auf. Ein Laufzeit-Toggle trennt sie, und die Antwort auf Frage 2 wird als Antwort auf Frage 1 ausgegeben.

## Ziel

- Die UI zeigt den Zustand, der in der DB steht — unabhängig davon, welcher Worker antwortet.
- Ein Toggle wirkt **ohne Neustart** für methodenbasierte Extension-Points (Status-Pills, Menü-Aktionen, Dashboard-Panels).
- Wo ein Neustart technisch unvermeidbar bleibt, sagt das System es, statt Bereitschaft vorzutäuschen.

## Nicht-Ziele

- **Kein Broadcast/SHM/Message-Bus zwischen Workern.** Die DB ist bereits der geteilte Zustand; ein zweiter Kanal wäre eine zweite Wahrheit.
- **Kein Hot-Mounting von Plugin-Routern.** Siehe Randbedingung unten.
- **Keine Änderung am Toggle-Endpunkt selbst** — der schreibt bereits korrekt.

## Randbedingung: Router lassen sich nicht nachrüsten

Plugin-Router werden **einmalig beim Start** eingehängt (`lifespan.py:630-633`, `app.include_router(...)`). Ein zur Laufzeit nachaktiviertes Plugin kann seine HTTP-Endpunkte deshalb nicht bekommen. Methodenbasierte Beiträge — `collect_status_pill()`, `run_menu_action()`, `get_dashboard_data()` — funktionieren dagegen sofort, weil sie über die Instanz laufen, nicht über die Routing-Tabelle.

Konsequenz für den Entwurf: nachaktiviert wird trotzdem (halbe Funktion ist besser als keine), aber ein Plugin mit eigenem Router meldet in der Detailansicht **„Neustart erforderlich"**. `steam_gaming` hat keinen Router und ist vollständig abgedeckt.

## Architektur

```
services/plugin_enablement.py     NEU: enabled_names(db) -> set[str], DB + TTL-Cache
                                       reconcile_worker(db) -> None  (async)
plugins/manager.py                 Lesepfade beantworten aus der DB-Menge;
                                   _enabled bedeutet nur noch "lokal geladen"
middleware/plugin_gate.py          nutzt denselben Helper statt eigener Kopie
api/routes/plugins.py              reconcile an den async-Einstiegspunkten
services/status_bar/service.py     dito vor dem Pill-Collect
```

### Eine Wahrheitsquelle

`enabled_names(db) -> set[str]` liest `installed_plugins.is_enabled` und cacht das Ergebnis für ein kurzes TTL-Fenster. Das Muster existiert bereits in `PluginGateMiddleware._fetch_plugin_status` (5 s TTL, `plugin_gate.py:25`); dieser Entwurf zieht es an **eine** Stelle, und die Middleware wird sein zweiter Nutzer statt einer zweiten Implementierung.

`_enabled` bleibt bestehen, verliert aber seine Doppelrolle: es beantwortet ausschließlich „dieser Worker hat die Instanz geladen und gestartet" und wird nie wieder als Aktivierungszustand nach außen gegeben.

### Selbstheilung statt Signalisierung

```python
async def reconcile_worker(db: Session) -> None:
    """Gleicht die lokal geladenen Plugins an die DB an."""
```

Die Funktion bildet die Differenz zwischen `enabled_names(db)` und `manager._enabled` und gleicht sie lokal an: fehlende werden über `enable_plugin()` nachgeladen, überzählige über `disable_plugin()` abgeräumt. Aufgerufen wird sie an den **async** Einstiegspunkten, die den Zustand brauchen:

- `GET /api/plugins` (Liste)
- `GET /api/plugins/ui/manifest`
- `POST /api/plugins/{name}/menu-actions/{action_id}`
- Status-Bar-`collect_state()`

Damit heilt sich jeder Worker beim nächsten Request selbst; im eingeschwungenen Zustand ist die Differenz leer und der Aufruf kostet nichts außer einem gecachten DB-Blick.

**Warum nicht im Getter?** `get_all_plugins()` ist synchron, `enable_plugin()` async. Ein Reconcile im Getter bräuchte `asyncio.run()` mitten im Request — die Sorte Abkürzung, die später als Deadlock zurückkommt. Der Reconcile gehört deshalb vor den Getter, in den async Aufrufer.

### Hintergrund-Tasks bleiben primary-only

`load_enabled_plugins()` übergibt heute `start_background_tasks=IS_PRIMARY_WORKER` (`lifespan.py:628`). Der Reconcile **muss** dasselbe tun. Täte er es nicht, würden nach dem ersten Reconcile alle vier Worker die Hintergrund-Tasks eines Plugins starten — aus einem Anzeigefehler würde vierfache Arbeit, vierfache Schreibzugriffe und ein echter Schaden.

## Fehlerbehandlung

Der interessante Fall ist die nicht lesbare DB — und derselbe Fakt muss dort in **zwei Richtungen** scheitern:

| Aufrufer | Verhalten bei DB-Fehler | Begründung |
|---|---|---|
| Anzeige, Manifest, Pills | Rückfall auf den letzten bekannten lokalen Zustand + Warnung | Ein DB-Aussetzer darf die Plugin-Liste nicht leeren und Pills nicht verschwinden lassen |
| `PluginGateMiddleware` | **fail closed** (wie heute: 500) | Eine Sicherheitsentscheidung darf nicht auf veraltetem Zustand fußen |

Der Helper reicht den Fehler deshalb nach oben durch, statt ihn selbst zu behandeln; die beiden Aufrufer entscheiden gegenläufig. Ein Helper, der „etwas Sinnvolles" täte, hätte zwangsläufig einen der beiden Fälle falsch.

Weitere Fälle:

| Fall | Verhalten |
|---|---|
| `on_startup()` des nachzuladenden Plugins wirft | Warnung im Log, Plugin **nicht** in `_enabled`; die übrigen laufen unberührt weiter |
| Wiederholt scheiterndes Nachladen | Kurze Sperre pro Plugin, damit nicht jeder Request es erneut versucht |
| Plugin in der DB aktiviert, aber im Verzeichnis nicht vorhanden | Übersprungen mit Warnung (wie `load_enabled_plugins` es heute tut) |
| Plugin mit eigenem Router lazy aktiviert | Methodenbasierte Beiträge funktionieren; Detailansicht meldet „Neustart erforderlich" |

## Sicherheit

- Der Reconcile ändert **nichts** an der Berechtigungsprüfung: `enable_plugin()` validiert weiterhin die in der DB hinterlegten `granted_permissions`.
- Das Gate wird nicht aufgeweicht, sondern nutzt künftig dieselbe Quelle mit unverändertem Fail-Closed-Verhalten.
- Ein deaktiviertes Plugin wird beim Reconcile **aktiv abgeräumt** — bisher blieb es auf einem Worker geladen, bis dieser neu startete. Der Fix schließt also nebenbei die Gegenrichtung: „deaktiviert" wirkt jetzt ebenfalls ohne Neustart.

## Tests

**Der Test, den es bisher nicht gab und der genau diesen Bug gefangen hätte:** zwei `PluginManager`-Instanzen auf **einer** DB — Toggle über Instanz A, Abfrage über Instanz B meldet „aktiviert". Das ist die Mehr-Worker-Situation im Kleinen, ohne echte Prozesse, und es ist der einzige Test, der die Trennung von globaler und lokaler Tatsache tatsächlich prüft.

Dazu:

- **Helper:** liefert die DB-Menge; cacht innerhalb des TTL-Fensters (zweiter Aufruf liest nicht erneut); nach Ablauf wieder; DB-Fehler wird nach oben gereicht statt verschluckt.
- **Lesepfade:** `get_all_plugins()`, `ui/manifest` und `is_enabled()` melden „aktiviert", obwohl `_enabled` des Workers leer ist.
- **Reconcile:** lädt Fehlendes nach; räumt Überzähliges ab; startet Hintergrund-Tasks **nur** wenn Primary; ein werfendes Plugin blockiert die übrigen nicht; ein gescheitertes wird nicht sofort erneut versucht.
- **Regression Gate:** `PluginGateMiddleware` antwortet bei DB-Fehler weiterhin fehlschlagend, nicht durchlassend.
- **Router-Fall:** ein lazy aktiviertes Plugin mit Router wird als „Neustart erforderlich" gemeldet.

## Risiken

- **Reconcile auf dem heißen Pfad.** Er läuft bei jedem Request an den genannten Endpunkten. Im Normalfall ist die Differenz leer und die DB-Antwort gecacht; die Kosten liegen bei einem Mengenvergleich. Wird das je spürbar, ist das TTL die Stellschraube.
- **Nachladen ist nicht kostenlos.** Ein `on_startup()` kann langsam sein; der erste Request nach einem Toggle zahlt das auf einem Worker einmalig.
- **Halbe Aktivierung bei Router-Plugins** bleibt bestehen und ist nur durch Neustart auflösbar. Bewusst dokumentiert statt kaschiert.
