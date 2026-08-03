# Always-Awake an Kernbetriebszeit-Fenstern kürzen

**Datum:** 2026-08-03
**Status:** Design freigegeben, Umsetzung ausstehend
**Betrifft:** `always_awake` (Spec 2026-05-07), Kernbetriebszeit (Spec 2026-05-01)

---

## Problem

Always-Awake wird mit einer Dauer gesetzt (1h / 4h / 8h / Custom bis 7 Tage) und
läuft dann bis zum errechneten Zeitpunkt. Die Kernbetriebszeit-Fenster
(`core_uptime_windows`) bleiben dabei unberücksichtigt.

Fällt der Ablaufzeitpunkt **in** ein künftiges Kernbetriebszeit-Fenster, ist der
Rest des Overrides wirkungslos: ab dem Fensterbeginn hält die Kernbetriebszeit
das System ohnehin wach. Der Override läuft trotzdem weiter, überlagert die
reguläre Steuerung länger als nötig und verschleiert in der UI, wer das System
gerade wach hält.

Beispiel: Fenster 19:00–23:30, es ist 15:00, Nutzer wählt „8h" → 23:00. Zwischen
19:00 und 23:00 ändert der Override nichts am Verhalten — er ist reine
Redundanz mit unklarer Zuständigkeit.

## Lösung

Beim Setzen von `always_awake_until` wird der Zeitpunkt auf den **Beginn** des
Kernbetriebszeit-Fensters gekürzt, in dem er liegt — sofern dieser Beginn noch
in der Zukunft liegt. Ab da übernimmt die Kernbetriebszeit; der manuelle
Override schließt sauber ab. Reicht der Zeitpunkt über das Fensterende hinaus,
bleibt er unverändert: dann wird der Override nach dem Fenster noch gebraucht.

Der gekürzte Wert wird persistiert. Damit ist der gespeicherte Wert die
Wahrheit — Countdown, Status-Endpoint und Topbar-Pill funktionieren
unverändert, ohne dass irgendein Consumer eine effektive Zeit nachrechnen muss.

### Verhaltenstabelle

Fenster 19:00–23:30, aktueller Zeitpunkt 15:00, Kernbetriebszeit-Hauptschalter an:

| Situation | Gewählter Ablauf | Gespeichert | UI-Hinweis |
|---|---|---|---|
| Ablauf vor dem Fenster | 17:00 | 17:00 | — |
| Ablauf **im** Fenster | 21:00 | **19:00** | Kürzungshinweis |
| Ablauf hinter dem Fensterende | 01:00 | 01:00 | — |
| Ablauf exakt auf Fensterbeginn | 19:00 | 19:00 | Kürzungshinweis (Wortlaut identisch — das Ergebnis ist dasselbe) |
| Fenster läuft bereits (jetzt 20:00) | 21:00 | 21:00 | „Kernbetriebszeit läuft bis 23:30" |
| „Dauerhaft" (kein Ablauf) | `NULL` | `NULL` | bestehender `hintPermanentClearToResume` |
| Hauptschalter `core_uptime_enabled` aus | 21:00 | 21:00 | — |
| Keine oder nur deaktivierte Fenster | 21:00 | 21:00 | — |

Weitere Festlegungen:

- **Mehrere Fenster:** es zählt das Fenster, das den Zeitpunkt enthält.
  Enthalten ihn mehrere (überlappende Fenster), gewinnt der **früheste Start** —
  bewusst nicht der erste Treffer wie bei `is_in_core_uptime`. Nur so hängt das
  Ergebnis nicht von der Listenreihenfolge ab, und die Frontend-Vorschau, die
  über aufgelöste Termine rechnet, kommt garantiert auf denselben Wert.
- **Laufendes Fenster:** wird nie gekürzt, weil sein Beginn in der Vergangenheit
  liegt. Die Bedingung `start > now` deckt das ohne Sonderfall ab.
- **Kurze Restdauer:** die Kürzung darf beliebig kurze Restlaufzeiten erzeugen
  (18:57 + „1h" → 3 Minuten). Bewusst zugelassen; die UI kündigt es vorher an.
  Der 5-Minuten-Mindestabstand des Custom-Pickers gilt für die **Eingabe**, nicht
  für das Kürzungsergebnis.
- **Nachträgliche Fensteränderung:** ein bereits gesetzter Override wird nicht
  neu bewertet, wenn danach Fenster geändert werden. Bewusste Vereinfachung —
  die Alternative (dynamische Auswertung) lässt Anzeige und Wirkung
  auseinanderlaufen.
- **Kein Einfluss auf den Sleep-Zeitplan** (`schedule_sleep_time` /
  `schedule_wake_time`). Der bleibt unangetastet.

## Backend

### Neue reine Helper — `backend/app/services/power/core_uptime.py`

Die Datei ist bereits die Heimat der Fensterlogik (lokal-naive Zeiten,
`start` inklusiv, `end` exklusiv, Mitternachtsüberlauf). Drei Ergänzungen:

```python
def current_window_start(now: datetime, w) -> datetime:
    """Beginn des aktuell aktiven Fensters. Gegenstück zu current_window_end.
       Caller stellt sicher, dass `now` tatsächlich in `w` liegt."""

def window_start_containing(dt: datetime, windows: Sequence) -> Optional[datetime]:
    """Beginn des Fensters, das `dt` enthält — sonst None."""

def expand_occurrences(
    now: datetime, windows: Sequence, days: int = 7,
) -> list[tuple[datetime, datetime]]:
    """Konkrete (start, end)-Paare aller aktivierten Fenster im Horizont."""
```

- `current_window_start` spiegelt `current_window_end` (Zeile 95 ff.): bei
  Mitternachtsüberlauf und `now >= start_today` ist der Beginn heute, sonst
  gestern.
- `window_start_containing` baut auf `is_in_core_uptime`/`_window_active_at` auf,
  erbt damit Wochentags- und Mitternachtssemantik ohne Duplikat.
- `expand_occurrences` iteriert `day_offset` von **-1** bis `days` (das `-1`
  fängt ein über Mitternacht laufendes Fenster von gestern ein), erzeugt je
  Treffer `start` und `end` (`end` +1 Tag bei Mitternachtsüberlauf), verwirft
  Vorkommen mit `end <= now` und sortiert nach `start`.

### Kürzung — `backend/app/services/power/sleep.py`

In `update_config()` (Zeile 1339 ff.), nachdem `always_awake_until` gesetzt und
bevor `db.commit()` aufgerufen wird:

1. Nur aktiv, wenn `config.always_awake_until is not None` **und** der nach dem
   Update gültige `config.core_uptime_enabled` wahr ist (der Wert kann im selben
   Request mitgeändert worden sein — deshalb erst nach dem Anwenden prüfen).
2. Fenster in derselben Session laden:
   `db.query(CoreUptimeWindowModel).filter(CoreUptimeWindowModel.enabled.is_(True))`
   — `.is_(True)` statt `== True`, damit ein Ruff-E712-Autofix die Query nicht
   zerlegt (bekannte Landmine in diesem Repo: E711/E712-Fixes brechen
   SQLAlchemy-Filter).
3. Zeitzonengrenze — der einzige heikle Punkt: `always_awake_until` ist
   **UTC-aware**, die Fensterlogik durchgängig **lokal-naiv**.

```python
until_local = config.always_awake_until.astimezone().replace(tzinfo=None)
now_local = datetime.now()
start_local = core_uptime_helpers.window_start_containing(until_local, windows)
if start_local is not None and start_local > now_local:
    config.always_awake_until = start_local.astimezone(timezone.utc)
```

`datetime.astimezone()` interpretiert einen naiven Wert als lokale Zeit — die
Rückkonvertierung ist damit korrekt und braucht keine externe TZ-Bibliothek.

4. Die Kürzung sitzt bewusst im Service, nicht im Route-Handler: sie greift
   damit für jeden Schreibpfad, auch für direkte API-Aufrufe außerhalb der
   Web-UI.

Der bestehende Audit-Log-Eintrag `always_awake_toggled` in
`backend/app/api/routes/sleep.py` protokolliert bereits das Ergebnis-`until` aus
der Service-Antwort und zeichnet den gekürzten Wert damit automatisch auf. Keine
Änderung nötig.

Der Ablauf-Aufräumpfad in `_schedule_check_loop` (Zeile 552 ff.) bleibt
unverändert: er sieht schlicht ein früheres `until` und räumt entsprechend
früher auf.

### Kein Schema- oder Migrations-Bedarf

`SleepConfig`, `AlwaysAwakeStatus` und `SleepConfigResponse` bleiben unverändert.
Der ursprünglich gewünschte Zeitpunkt wird **nicht** gespeichert — der
Kürzungshinweis in der UI wird stattdessen aus „`until` fällt exakt auf einen
Fensterbeginn" abgeleitet (siehe Frontend). Damit entfällt eine Alembic-Migration
vollständig.

## API

Ein neuer Endpoint neben den bestehenden Kernbetriebszeit-Routen in
`backend/app/api/routes/sleep.py`, exakt nach deren Muster
(`Depends(get_current_admin)` + `@user_limiter.limit(get_limit("admin_operations"))`):

```
GET /api/system/sleep/core-uptime/occurrences?days=7
→ 200 list[CoreUptimeOccurrence]
```

```python
class CoreUptimeOccurrence(BaseModel):
    window_id: int
    label: Optional[str] = None
    start: datetime   # absolut, UTC-aware
    end: datetime     # absolut, UTC-aware
```

- `days`: `Query(7, ge=1, le=7)` — deckt exakt den 7-Tage-Cap des Custom-Pickers ab.
- Der Server rechnet lokal (`expand_occurrences`) und liefert UTC-aware
  Zeitstempel aus, damit das Frontend sie direkt mit `always_awake_until`
  vergleichen kann.
- Liefert `[]`, wenn keine aktivierten Fenster existieren. Der
  Hauptschalter `core_uptime_enabled` filtert **nicht** — das entscheidet der
  Aufrufer; so bleibt der Endpoint für andere Consumer brauchbar.

## Frontend

### API-Client

`client/src/api/sleep.ts`: `getCoreUptimeOccurrences(days = 7)` plus
`CoreUptimeOccurrence`-Typ, analog zu den bestehenden Fenster-Funktionen.

### Reiner Helper

Neu, als eigene Datei mit eigenem Vitest-Test (keine Logik im Panel):

```ts
export function clampToCoreUptime(
  untilIso: string,
  occurrences: CoreUptimeOccurrence[],
  now = new Date(),
): { until: string; clampedTo: CoreUptimeOccurrence | null }
```

Reiner Intervallvergleich — dieselbe Semantik wie im Backend, ohne dessen
Wochentags- und Mitternachtslogik nachzubauen:
Treffer ist die erste Occurrence mit `start > now && until >= start && until < end`.

Zweite, ebenso reine Funktion für den Sonderfall „läuft gerade":
`findRunningOccurrence(occurrences, now)` → erste mit `start <= now < end`.

### `AlwaysAwakePanel.tsx`

- `refresh()` lädt die Occurrences zusätzlich, aber nur wenn
  `cfg.core_uptime_enabled` — sonst leeres Array, alle Hinweise entfallen.
- **Vorher-Hinweis, Touch-tauglich:** Preset-Buttons, deren Wert gekürzt würde,
  bekommen einen dezenten Marker (Icon + abweichende Randfarbe) sowie ein
  `title`-Attribut. Zusätzlich erscheint unter der Preset-Reihe eine Detailzeile
  für den gerade gehoverten **oder fokussierten** Button (Maus und Tastatur).
  Auf reinen Touch-Geräten trägt der Marker die Information; die Detailzeile ist
  Ergänzung, nicht Voraussetzung.
- **Custom-Picker:** derselbe Hinweis live bei jeder Änderung des
  `datetime-local`-Werts, neben der bestehenden Validierung. Die Kürzung ist
  **kein** Fehler — der Apply-Button bleibt aktiv.
- **Nachher-Hinweis:** im aktiven Bereich, abgeleitet aus
  `occurrences.some(o => o.start === until)`. Überlebt damit den Reload, ohne den
  ursprünglich gewünschten Zeitpunkt zu persistieren.
- **Läuft gerade:** liefert `findRunningOccurrence` einen Treffer, ersetzt dessen
  Hinweis den Kürzungshinweis („Kernbetriebszeit läuft bis 23:30 — bis dahin
  bleibt das System ohnehin wach").
- **Optimistisches Update:** `setPreset()` und `setCustomPreset()` müssen den
  **gekürzten** Wert in `setUntil`/`setExpiresIn` schreiben und senden, sonst
  springt die Anzeige nach dem nächsten `refresh()` sichtbar zurück.
- Die Preset-Erkennung in `refresh()` (Toleranz ±5 min gegen 1h/4h/8h) ordnet
  einen gekürzten Wert korrekterweise `custom` zu — gewolltes Verhalten, keine
  Anpassung nötig.

`AlwaysAwakePill.tsx` (Topbar) zeigt den gespeicherten Wert und damit automatisch
den gekürzten — dort ist nichts zu ändern.

### i18n

Neue Keys unter `sleep.alwaysAwake` in `client/src/i18n/locales/{de,en}/system.json`:

| Key | DE |
|---|---|
| `clampPreview` | „Wird auf {{time}} gekürzt — ab dann übernimmt die Kernbetriebszeit (wach bis {{end}})." |
| `clampActive` | „Endet um {{time}} mit dem Beginn der Kernbetriebszeit (wach bis {{end}})." |
| `clampBadge` | „Wird gekürzt" (title/aria am Preset-Button) |
| `coreUptimeRunning` | „Kernbetriebszeit läuft bis {{end}} — bis dahin bleibt das System ohnehin wach." |

EN-Block parallel dazu.

## Tests

**pytest — Helper (`backend/tests/`, rein, ohne DB):**
- `current_window_start`: normales Fenster; Mitternachtsüberlauf in der späten
  Hälfte (Beginn heute) und in der frühen Hälfte (Beginn gestern)
- `window_start_containing`: Treffer, kein Treffer, deaktiviertes Fenster wird
  ignoriert, leere Liste
- `expand_occurrences`: Wochentagsfilter, Mitternachtsüberlauf, laufendes
  Fenster von gestern erscheint, abgelaufene Vorkommen fehlen, Sortierung,
  `days`-Horizont

**pytest — Kürzung in `update_config`:** je ein Fall pro Zeile der
Verhaltenstabelle, plus:
- UTC↔lokal-Grenze: gekürzter Wert kommt UTC-aware zurück und entspricht dem
  lokalen Fensterbeginn
- `core_uptime_enabled` wird im selben Request eingeschaltet → Kürzung greift
- `always_awake_enabled: false` → `until` wird geleert, keine Kürzung

**Vitest:**
- `clampToCoreUptime` / `findRunningOccurrence` als reine Funktionen entlang
  derselben Tabelle
- Panel: Kürzungshinweis erscheint, und `updateSleepConfig` wird mit dem
  gekürzten Wert aufgerufen

## Nicht Teil dieser Änderung

- Der Sleep-Zeitplan (`schedule_sleep_time`/`schedule_wake_time`) bleibt
  unberührt — die Kürzung gilt ausschließlich für Kernbetriebszeit-Fenster.
- Kein Neubewerten bereits gesetzter Overrides beim Ändern von Fenstern.
- Kein Speichern des ursprünglich gewünschten Zeitpunkts (keine Migration).
