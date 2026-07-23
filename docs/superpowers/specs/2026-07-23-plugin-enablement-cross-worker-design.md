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

- Die UI zeigt den Zustand, der in der DB steht — unabhängig davon, welcher Worker antwortet (verbleibende Staleness TTL-begrenzt auf wenige Sekunden, statt wie heute unbegrenzt bis zum Restart).
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
services/plugin_enablement.py     NEU: enabled_plugins() -> Mapping[name, granted_permissions]
                                       (DB + TTL-Cache, Refresh off-loop)
                                       refresh(force=False) -> None      (async, to_thread)
                                       reconcile_worker() -> None        (async, single-flight)
plugins/manager.py                 Status-Lesepfade konsumieren den Cache;
                                   _enabled bedeutet nur noch "lokal geladen"
middleware/plugin_gate.py          nutzt denselben Helper statt eigener Kopie
api/routes/plugins.py              refresh + reconcile an den async-Einstiegspunkten
services/status_bar/service.py     dito vor dem Pill-Collect
```

### Eine Wahrheitsquelle

Der Helper liest `installed_plugins` und cacht **`name -> granted_permissions`** für ein kurzes TTL-Fenster; die Menge der aktivierten Namen ist davon abgeleitet.

**Warum ein Mapping und kein Set:** `PluginGateMiddleware` braucht aus demselben DB-Read zwei Dinge — den Aktivierungszustand *und* die granted permissions, die sie gegen `get_required_permissions()` prüft (`plugin_gate.py:49-68`, Rückgabe heute `(bool, List[str])`). Ein reines Namens-Set würde die Middleware zwingen, ihre eigene Abfrage zu behalten — und das „eine Stelle"-Versprechen wäre von Anfang an gebrochen. Mit dem Mapping wird sie tatsächlich zweiter Nutzer statt zweiter Implementierung; ihr Fail-Closed-Verhalten (DB-Fehler → 500) bleibt unverändert.

**Wer liest wie:** Der DB-Zugriff passiert ausschließlich im async `refresh()` und läuft per `asyncio.to_thread` — dieselbe Konvention, mit der die Middleware heute ihren Read vom Event-Loop fernhält. **Synchrone Leser (`get_all_plugins()`, `is_enabled()`) konsumieren nur den warmen Cache und fassen die DB nie selbst an.** Das ist keine Nebensächlichkeit: `get_all_plugins()` hat keine Session (auch die Route `list_plugins` hat heute kein `db`-Dependency), und ein synchroner DB-Read im Getter würde den Event-Loop blockieren — genau die Fehlerklasse, die beim `kscreen-doctor`-Fix gerade erst beseitigt wurde. Die async Einstiegspunkte rufen `refresh()` vor dem Getter auf.

`_enabled` bleibt bestehen, verliert aber seine Doppelrolle: es beantwortet ausschließlich „dieser Worker hat die Instanz geladen und gestartet" und wird nie wieder als Aktivierungszustand nach außen gegeben.

**Zwei Sorten Lesepfade, zwei Semantiken.** Reine Statusanzeigen (`get_all_plugins()`-`is_enabled`-Flag, `is_enabled()`) beantworten aus dem Cache — der DB-Wahrheit. `iter_enabled_plugins()` und `get_ui_manifest()` dagegen brauchen **Instanzen** (`manager.py:859-862` yieldet `self.get_plugin(name)`), und eine Instanz kann nur aus dem lokalen Zustand kommen: ihre Semantik ist **DB ∩ lokal geladen**. Nach dem Reconcile konvergieren beide Mengen; die Formulierung steht hier, damit niemand versucht, aus einer DB-Zeile eine Instanz zu yielden.

**Verbleibende Staleness ist begrenzt, nicht null.** Nach einem Toggle ist der behandelnde Worker sofort frisch (`invalidate_plugin_cache` bleibt prozess-lokal und wird um die Invalidierung des neuen Caches ergänzt); die übrigen Worker sind bis zum TTL-Ablauf stale. Aus „falsch bis zum Restart" wird „maximal ~5 s" — das ist das ehrliche Versprechen dieses Entwurfs, kein absolutes.

### Selbstheilung statt Signalisierung

```python
async def reconcile_worker() -> None:
    """Gleicht die lokal geladenen Plugins an die DB an. Single-flight."""
```

Die Funktion refresht den Cache, bildet die Differenz zwischen der DB-Menge und `manager._enabled` und gleicht sie lokal an: fehlende werden über `enable_plugin()` nachgeladen (mit den `granted_permissions` aus dem Cache-Mapping), überzählige über `disable_plugin()` abgeräumt.

**Single-flight pro Worker.** Zwei gleichzeitige Requests (Statusleisten-Poll und Plugin-Liste treffen realistisch zusammen) sehen sonst beide dieselbe Differenz und rufen beide `enable_plugin()` für dasselbe Plugin — `on_startup()` liefe doppelt und parallel. Ein `asyncio.Lock` um den Reconcile genügt; wer den Lock nicht bekommt, wartet nicht, sondern läuft mit dem aktuellen Zustand weiter (der Reconcile des anderen ist gleich fertig).

Aufgerufen wird sie an den **async** Einstiegspunkten, die den Zustand brauchen:

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

- **Helper:** liefert das Mapping `name -> granted_permissions`; cacht innerhalb des TTL-Fensters (zweiter Aufruf liest nicht erneut); nach Ablauf wieder; DB-Fehler wird nach oben gereicht statt verschluckt; synchrone Leser lösen **keinen** DB-Read aus (nachweisbar: Cache warm, DB-Fixture entfernt, Leser funktioniert weiter).
- **Lesepfade:** `get_all_plugins()` und `is_enabled()` melden „aktiviert", obwohl `_enabled` des Workers leer ist; `iter_enabled_plugins()`/`get_ui_manifest()` liefern das Plugin erst **nach** dem Reconcile (DB ∩ geladen).
- **Reconcile:** lädt Fehlendes nach (mit den Permissions aus dem Mapping); räumt Überzähliges ab; startet Hintergrund-Tasks **nur** wenn Primary; ein werfendes Plugin blockiert die übrigen nicht; ein gescheitertes wird nicht sofort erneut versucht; **zwei gleichzeitige Reconciles aktivieren nur einmal** (Single-Flight — `on_startup()`-Zählung unter parallelem Aufruf).
- **Middleware:** bezieht Zustand und Permissions aus dem Helper und verhält sich unverändert (aktiviert+Permissions → durch, deaktiviert → 403, fehlende Permission → 403).
- **Regression Gate:** `PluginGateMiddleware` antwortet bei DB-Fehler weiterhin fehlschlagend, nicht durchlassend.
- **Router-Fall:** ein lazy aktiviertes Plugin mit Router wird als „Neustart erforderlich" gemeldet.

## Risiken

- **Reconcile auf dem heißen Pfad.** Er läuft bei jedem Request an den genannten Endpunkten. Im Normalfall ist die Differenz leer und die DB-Antwort gecacht; die Kosten liegen bei einem Mengenvergleich. Wird das je spürbar, ist das TTL die Stellschraube.
- **Nachladen ist nicht kostenlos.** Ein `on_startup()` kann langsam sein; der erste Request nach einem Toggle zahlt das auf einem Worker einmalig.
- **Halbe Aktivierung bei Router-Plugins** bleibt bestehen und ist nur durch Neustart auflösbar. Bewusst dokumentiert statt kaschiert.
