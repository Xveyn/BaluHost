# Plugin-Notification-Events + Steam-Session-Poller — Design

**Datum:** 2026-07-23
**Status:** entworfen, abgenommen
**Teilprojekt 3 von 4** — Gesamtschnitt siehe
`docs/superpowers/specs/2026-07-22-status-bar-plugin-pills-steam-gaming-design.md`

## Ziel

Plugins sollen eigene **Notification-Ereignisse** beitragen, die durch dieselbe
Zustellung laufen wie Core-Events (Persistierung, Routing pro Nutzer, Cooldown,
Push + WebSocket). Der erste Konsument ist das `steam_gaming`-Plugin: ein
**primary-only Poller** erkennt Flanken — ein Steam-Spiel startet, ein Spiel
endet — und meldet sie als Benachrichtigung („🎮 Gaming-Session gestartet:
<Spiel>" / „beendet: <Spiel>").

Wie in Teilprojekt 1 und 2 entsteht der Extension-Point **zusammen mit seinem
ersten Konsumenten** — eine API ohne echten Nutzer bekommt fast immer den
falschen Schnitt.

## Ausgangslage

Das Notification-System (`services/notifications/events.py`, 1171 Zeilen) ist
heute nach außen geschlossen, nach innen aber bereits string-offen:

- **`EventType`** ist ein hartes `str`-Enum (`raid.degraded`, `smart.warning`,
  …). **`EVENT_CONFIGS: dict[str, EventConfig]`** hält pro Event Priorität,
  Kategorie, `notification_type`, Titel-/Nachrichten-Template und `action_url`.
  **`_COOLDOWN_SECONDS: dict[str, int]`** hält den Cooldown pro Event.
- **Der Emit-Pfad ist schon offen.** `EventEmitter.emit(event_type, ...)`
  (`events.py:496`) macht `EVENT_CONFIGS.get(event_type)` und meldet bei
  Unbekanntem nur eine Warnung (`events.py:515-518`) — kein Fehler, kein
  Absturz. Die eigentliche Zustellung (`service.create()` →
  Persistierung + Routing pro Nutzer + Cooldown + Push + WebSocket) ist
  **generisch** und string-basiert.
- **Zielwahl** über `emit_for_admins()` (`events.py:854`) und
  `emit_for_all_users()` (`events.py:867`).
- **Plugin-Background-Tasks laufen dank #448 automatisch primary-only**
  (`enable_plugin(..., start_background_tasks=IS_PRIMARY_WORKER)`) — kein neuer
  Mechanismus nötig, um einen Poller nur einmal laufen zu lassen.

Was fehlt, ist allein der Weg, wie ein Plugin seine Event-**Deklaration**
(Config + Cooldown + Kategorie) in die Registry einspeist — und ein erster
Konsument.

## Entscheidungen (im Brainstorming getroffen)

- **Empfänger: nur Admins.** Der Spielname ist eine Information über den
  Box-Besitzer — dieselbe Privatsphäre-Entscheidung wie bei der Pill in
  Teilprojekt 1. `default_target="admins"`, serverseitig durchgesetzt.
- **Flanken: Start + Ende.** Session-Dauer und Dashboard-Historie bleiben
  Teilprojekt 4. Der direkte Spielwechsel (X→Y ohne Pause) wird bewusst
  verschluckt — festgehalten als Maybe-Feature in **#462**.

## Nicht-Ziele

- **Kein neuer Zustellpfad.** Plugin-Events laufen durch exakt dieselbe
  Maschine wie Core-Events; nichts an Routing, Push oder WebSocket wird
  angefasst.
- **Keine per-Nutzer-Kategorie-Preference für Plugin-Events.** Die
  category_preferences (ein Nutzer schaltet eine Kategorie für sich ab) würden
  einen worker-übergreifenden Read der Plugin-Kategorie-Liste brauchen — das
  ist TP4-Gebiet. In TP3 sind die Empfänger admin-fix; die Kategorie steht in
  der Notification, ist aber nicht per Nutzer abschaltbar.
- **Keine clientseitige i18n der Notification-Texte.** Notifications werden
  serverseitig gerendert und persistiert (die Core-Events sind alle deutsch);
  das Plugin liefert Template-Strings in einer Sprache, kein
  `resolvePluginString`-Zweig.
- **Kein `EventType`-Enum-Umbau.** Das Enum bleibt für Core-Autoren; die
  Registry liegt daneben, statt das Enum zu ersetzen (der große Umbau von
  Ansatz C aus dem Brainstorming, bewusst verworfen).
- Session-Dauer, Auto-Displays-aus, Dashboard-Historie → Teilprojekt 4.

## Architektur

```
backend/app/plugins/base.py            + PluginEventSpec, get_notification_events()
backend/app/services/notifications/
  plugin_events.py                     NEU: PluginEventRegistry, emit_plugin_event()
  events.py                            emit() konsultiert die Plugin-Registry als Fallback
backend/app/plugins/installed/steam_gaming/
  __init__.py                          + get_notification_events(), get_background_tasks()
  poller.py                            NEU: Flankenerkennung Start/Ende, primary-only
```

### Deklaration

```python
class PluginEventSpec(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]+$")   # plugin-lokal, z. B. "session_started"
    category: str                               # z. B. "steam_gaming"
    notification_type: Literal["info", "warning", "critical"] = "info"
    priority: int = Field(default=0, ge=0, le=3)
    title_template: str                          # "Gaming-Session gestartet: {game}"
    message_template: str
    action_url: Optional[str] = None
    cooldown_seconds: int = 0
    default_target: Literal["admins", "all_users"] = "admins"
```

```python
# PluginBase
def get_notification_events(self) -> List[PluginEventSpec]:
    """Notification-Ereignisse dieses Plugins. Default: keine."""
    return []
```

### Registry

`PluginEventRegistry` (`services/notifications/plugin_events.py`) sammelt die
Specs aller **aktivierten** Plugins über denselben `iter_enabled_plugins()`-Seam
wie der Pill-Katalog. Die öffentliche Event-ID lautet
`plugin:<plugin_name>:<suffix>`, gebildet vom **Core**, nicht vom Plugin — eine
Kollision mit Core-IDs (`raid.degraded` etc.) ist ausgeschlossen.

Die Registry liefert für eine gegebene öffentliche ID ein `EventConfig`
(gebaut aus der Spec) plus den Cooldown und das Target. Damit muss der
Emit-Pfad die beiden Core-Dicts nicht umbauen.

### Emit

`EventEmitter.emit()` bekommt **eine** Änderung: findet es die ID nicht in
`EVENT_CONFIGS`, fragt es die Plugin-Registry, bevor es die
„unbekanntes Event"-Warnung ausgibt. Ab da ist der Pfad identisch — dasselbe
`service.create()`, dieselbe Persistierung, dasselbe Routing, derselbe
Cooldown, dieselbe Zustellung. Analog erhält `_check_cooldown` /`_set_cooldown`
den Cooldown-Wert aus der Registry, wenn die ID nicht in `_COOLDOWN_SECONDS`
steht.

Das Plugin emittiert nicht direkt, sondern über einen Core-Helper:

```python
async def emit_plugin_event(plugin_name: str, event_id: str, **kwargs) -> None:
    """Namespaced die ID zu plugin:<plugin_name>:<event_id>, zieht Config und
    Target aus der Registry und stellt an das deklarierte default_target zu."""
```

Damit liefert das Plugin **Daten** (welches Ereignis, welche kwargs), nie das
Zustellziel zur Laufzeit — `default_target` steht in der Deklaration.

### Der Poller

`steam_gaming` deklariert einen `BackgroundTaskSpec` über das vorhandene
`get_background_tasks()`. Der Task läuft dank #448 automatisch primary-only.
`poller.py` hält den zuletzt gesehenen Spielzustand **prozess-lokal**
(unbedenklich, weil nur ein Poller existiert) und vergleicht bei jedem Tick:

| vorher | jetzt | Aktion |
|---|---|---|
| kein Spiel | Spiel X | **Start** → `emit_plugin_event("steam_gaming", "session_started", game=X)` |
| Spiel X | kein Spiel | **Ende** → `emit_plugin_event("steam_gaming", "session_ended", game=X)` |
| Spiel X | Spiel X | nichts |
| Spiel X | Spiel Y | nichts, aber Zustand auf Y nachziehen (damit ein späteres Ende korrekt greift) |

Der Poller nutzt `detect_running_app_id()` + `resolve_name()` aus Teilprojekt 1
wieder und ruft `detect_running_app_id()` direkt auf (nicht den 3-s-Pill-Cache)
— er braucht den frischen Wert für die Flanke. **Poll-Intervall: 30 s.**

## Flanken, Cooldown, Zwei Schutzschichten

Die **Flanke** verhindert Wiederholung bei stabilem Zustand (ein laufendes
Spiel meldet nicht bei jedem Tick). Der **Cooldown** liegt darüber:
`cooldown_seconds = 60`, `entity_id = app_id`. Er fängt das Flattern ab, wenn
Steam kurz zuckt — ein Spiel crasht und startet in Sekunden neu, oder der
`reaper`-Prozess erscheint durch den mangohud-Wrapper doppelt (aus TP1
bekannt). Ohne diese Schicht käme ein „beendet"+„gestartet"-Paar bei einem
3-Sekunden-Crash-Neustart. Verschiedene Spiele haben verschiedene `entity_id`,
melden also unabhängig.

## Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| Poller wirft (z. B. `/proc` kurz unlesbar) | Exception-Guard im Task-Loop, geloggt, nächster Tick läuft weiter |
| Plugin-Event-ID nicht in der Registry | `emit()` loggt eine Warnung und kehrt zurück (heutiges Core-Verhalten), kein 5xx, kein Absturz |
| Template-Platzhalter fehlt | Bereits im Core abgefangen (`emit()` fällt auf das rohe Template zurück, `events.py:524`) |
| Firebase/Push nicht verfügbar | Bereits Core-Sache: In-App-Notification wird persistiert und per WebSocket zugestellt |
| Dev-Modus (kein `/proc`) | Poller findet nie ein Spiel → nie eine Flanke → nie ein Event |
| Plugin deaktiviert | Background-Task wird bei `disable_plugin()` gecancelt (vorhandener Mechanismus); die Registry-Einträge fallen mit dem Plugin aus dem Katalog |

Leitlinie: ein Plugin-Fehler stört niemals die Zustellung anderer Events oder
den Worker.

## Sicherheit

- Empfänger **admin-fix** (`default_target="admins"`), serverseitig über
  `emit_for_admins` durchgesetzt. Der Spielname erreicht keinen Nicht-Admin.
- Das Plugin liefert **Daten**, nie das Zustellziel zur Laufzeit — es kann seine
  Reichweite nicht ausweiten.
- Event-ID regexbeschränkt (`^[a-z0-9_]+$`) **und** vom Core namespaced —
  keine Kollision mit Core-IDs.
- Kein `subprocess`, kein sudo, keine neuen Sudoers-Regeln. Der Poller liest nur
  `/proc` (wie die Pill in TP1), kein neuer Systemzugriff.
- Template-Strings werden serverseitig gerendert und persistiert; die einzigen
  Platzhalter sind die vom Plugin gelieferten kwargs (Spielname), keine
  ausführbaren Pfade.

## Tests

**Extension-Point (Core).** `PluginEventSpec.id` weist Großbuchstaben, Punkte
und Pfadanteile ab. Registry: aktiviertes Plugin → Events auffindbar,
deaktiviert → weg. `emit()` findet ein Plugin-Event über die Registry (nicht in
`EVENT_CONFIGS`) und persistiert es korrekt (Kategorie, Typ, Priorität,
gerendertes Template). Unbekannte ID → Warnung, kein Crash; ein bekanntes
**Core**-Event läuft unverändert durch `EVENT_CONFIGS` (Regression — der offene
Pfad darf den Bestand nicht verändern). ID-Namespace `plugin:<name>:<suffix>`
kollidiert nicht mit Core-IDs; `default_target` wird serverseitig durchgesetzt,
ein Plugin kann das Ziel beim Emit nicht überschreiben.

**Poller / Flankenlogik** (gegen einen injizierten Detektor, kein echtes
`/proc`): die vier Übergänge — Start, Ende, kein-Event-bei-gleich,
kein-Event-bei-Wechsel-aber-Zustand-nachgezogen (verifiziert durch ein
anschließendes Y→None, das ein Ende liefert); werfender Poll wird geloggt, der
nächste Tick läuft; dauerhaft kein Spiel → nie ein Event.

**Cooldown:** zweimal Start desselben Spiels binnen 60 s → nur eine
Notification; zwei verschiedene Spiele → beide.

**Frontend:** keine Änderung — Notifications laufen durch die vorhandene
In-App-Liste + WebSocket. Nur gegenprüfen, dass die Notification-API-Form
unberührt bleibt.

## Offener Messpunkt

Dass der Poller auf der Box eine **echte** Steam-Session-Flanke erkennt und die
Notification real in App/Web ankommt, ist Zusammenspiel, kein Unit-Test. Es
gehört als expliziter Smoketest-Schritt auf BaluNode, bevor der PR als fertig
gilt: Spiel starten → „gestartet"-Notification; Spiel beenden →
„beendet"-Notification; beide nur für Admins sichtbar.

## Risiken

- **Steam ändert den `reaper`-Aufruf.** Dann bräche die Erkennung still — aber
  dasselbe Signal trägt schon die Pill aus TP1, ein Bruch wäre also an einer
  bekannten, getesteten Stelle (`detect_running_app_id`) und beträfe beide.
- **Poller-Intervall vs. sehr kurze Sessions.** Eine Session, die zwischen zwei
  30-s-Ticks beginnt und endet, wird nicht gemeldet. Für eine Anwesenheits-
  Benachrichtigung akzeptabel; kürzere Intervalle kosten `/proc`-Last ohne
  echten Gewinn.
- **Erster Notification-emittierender Extension-Point.** Bisher lieferten
  Plugins Anzeigedaten (Pills) oder lösten eine Admin-Aktion aus (Menü). Hier
  erzeugen sie eine persistierte, zugestellte Benachrichtigung. Kompensiert
  durch das admin-fixe Ziel, den unveränderten Core-Zustellpfad und den
  primary-only Poller (kein Multi-Worker-Duplikat).
