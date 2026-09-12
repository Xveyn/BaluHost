# Geplanter Systemneustart (Scheduler) — Design

**Datum:** 2026-09-12
**Status:** Genehmigt (Abschnitte 1–8 im Chat abgenommen)
**Branch:** `feat/scheduled-system-reboot`
**Basis:** `main` @ `7bacd7b9`

## Problem

BaluNode läuft dauerhaft und schläft nachts. Ein regelmäßiger, echter
Hardware-Neustart — Kernel-Updates wirksam machen, verwaiste Prozesse und
Speicherlecks aufräumen, Treiberzustand zurücksetzen — ist heute nur von Hand
möglich. Im gesamten Backend existiert kein einziger Reboot-Pfad.

Erschwerend: außerhalb der Kernbetriebszeit ist die Box suspendiert. Ein Termin
um 04:00 Uhr würde also schlicht verschlafen. Und wenn die Box sich um 04:00
selbst neu startet, sieht der Nutzer heute nur die generischen Meldungen
„System heruntergefahren" und „System gestartet" — also exakt das Bild eines
Servers, der ohne Grund neu startet.

## Ziel

Ein Admin konfiguriert **einen Wochentag und eine Uhrzeit**. Zu diesem Zeitpunkt
startet die Box vollständig neu — Hardware, nicht nur der Dienst. Liegt der
Termin in einer Phase, in der die Box suspendiert ist, weckt sie sich per RTC
selbst, startet neu und suspendiert danach wieder bis zum regulären
Aufwachzeitpunkt. Die Notifications erzählen die Geschichte lückenlos, sodass
niemand einen ungeplanten Absturz vermutet.

Das Feature ist **standardmäßig deaktiviert** und **nur für Admins** verwaltbar.

## Nicht-Ziele

- **Manueller Sofort-Neustart aus dem UI.** Eigenes Feature, eigene Rechte- und
  Bestätigungsfragen. `can_run_manually` bleibt für diesen Scheduler `false`.
- **Mehrere Neustart-Termine.** Ein Wochentag, eine Uhrzeit. Erweiterbar, aber
  nicht in v1.
- **Herunterfahren statt Neustart.** Eine Box, die sich abschaltet, kommt ohne
  WoL nicht zurück — das ist eine andere Risikoklasse.
- **Neustart als Reaktion auf etwas** (nach Update, bei hoher Uptime,
  bei Speicherdruck). Nur der feste Termin.
- **Abbruch-Fenster für Nutzer.** Die Vorwarnung informiert, sie fragt nicht.
  Wer den Neustart nicht will, schaltet das Feature ab oder setzt sich vor die
  Box (das Display-Gate greift dann).
- **Ein eigenes Power-Recht `can_manage_reboot`.** Admin-Gate genügt.

## Gemessene Ausgangslage

Alles hier ist am Code gelesen, nicht angenommen. Wer einen dieser Punkte
ändert, muss das Design neu prüfen.

**Der Scheduler kennt keine Wochentage.** `SchedulerWorker._add_job()`
(`backend/app/services/scheduler/worker.py:473`) registriert **ausschließlich**
`trigger="interval"`. Kein Cron, kein Wochentag, nirgends. APScheduler könnte
es, der Worker nutzt es nicht.

**Der Worker ist ein eigener Prozess** (`baluhost-scheduler.service`). Die IPC
zum Backend läuft über die Datenbank (`scheduler_executions`,
`scheduler_state`, `scheduler_configs`) plus Loopback-HTTP mit
`X-Service-Token` (Muster: `_register_power_demand`). Der Worker hat **keine**
`SleepManagerService`-Instanz und weiß nichts über Kernbetriebszeit, Displays
oder Suspend-Zustand.

**`scheduler_configs` hat bereits ein JSON-Feld `extra_config`** für
schedulerspezifische Konfiguration; `SchedulerService.update_scheduler_config()`
schreibt es generisch.

**Ein Registry-Eintrag ohne periodischen Job ist etabliert.** `auto_update` ist
in `SCHEDULER_REGISTRY` gelistet, sein `_dispatch_job`-Zweig gibt
`{"checked": True}` zurück und tut nichts — der Eintrag existiert für Sichtbarkeit
und Historie. Das Reboot-Feature nutzt dasselbe Muster.

**Es gibt keinen Reboot-Pfad.** Weder `systemctl reboot` noch `shutdown -r`
kommt im Backend vor. Auch kein passender sudoers-Eintrag.

**Suspend läuft an logind vorbei.** `LinuxSleepBackend.suspend_system()`
(`sleep_backend_linux.py:60`) ruft mit `wake_at` ein
`sudo rtcwake -m mem -t <ts>`. Das schreibt direkt an den Kernel; fremde
logind-Inhibitoren schützen nicht davor (bewiesen, Issue #602). Deshalb prüft
BaluHost fremde Block-Inhibitoren selbst.

**`wake_at` wird bereits geklemmt.** `enter_true_suspend()`
(`sleep.py:1101`) rechnet `next_core_uptime_start()` aus und zieht `wake_at`
darauf vor, falls das früher liegt. Genau hier dockt der Reboot-Termin an.

**Der RTC-Guard armt auch bei fremden Suspends.** `CoreUptimeRtcGuard`
(`core_uptime_rtc_guard.py`) hängt an loginds `PrepareForSleep` und setzt bei
einem Suspend, den *nicht* BaluHost ausgelöst hat, die RTC auf den nächsten
Kernbetriebszeit-Start. Die Quelle dafür ist
`SleepManagerService._next_core_start_for_guard()` (`sleep.py:368`).

**Fünf Suspend-Suppressoren existieren**, alle im 60-Sekunden-Tick
`_schedule_check_loop()` (`sleep.py:607`) und noch einmal defensiv in
`enter_true_suspend()`: Always-Awake, Kernbetriebszeit, Web-Presence, Gaming,
fremde logind-Block-Inhibitoren. Dazu `_is_system_idle()` über CPU, Disk-I/O,
aktive Uploads und HTTP-Rate.

**Kernbetriebszeit** liegt in `core_uptime_windows` (Wochentags-CSV plus
`start_time`/`end_time` als "HH:MM", server-lokal). Die reinen Helfer in
`services/power/core_uptime.py` sind zustandslos und getestet;
`next_core_uptime_start()` iteriert bewusst `day_offset 0..7` — bei
`0..6` fände ein Ein-Tages-Fenster seinen nächsten Termin nicht, wenn die
heutige Startzeit schon vorbei ist.

**`lifecycle.shutdown` und `lifecycle.startup` feuern bei jedem Backend-Stop
und -Start**, bewusst ohne Cooldown
(`core/lifespan.py:_emit_lifecycle_shutdown` / `_emit_lifecycle_startup`,
Zeilen 311 und 357). Die Downtime der Startmeldung wird aus der letzten
`shutdown`-Zeile in `system_lifecycle_events` berechnet.

**`gaming_presence.displays_on()` liefert im Dev-Mode hart `True`** — auf einem
Windows-Rechner gibt es keine DRM-Connectors, und für das Gaming-Gate ist
„immer an" die harmlose Richtung. Für ein Reboot-Gate ist es die **fatale**
Richtung: das Feature wäre lokal nie auslösbar.

**Zustand muss in die Datenbank.** Der Prod-Deploy macht `git reset --hard`,
und die Unit läuft mit `PrivateTmp` — eine Datei in `/tmp` überlebt den Neustart
nicht.

**`conftest` setzt `SKIP_APP_INIT=1`**, `_startup()` läuft in Tests also nie.
Ein Test, der Lifespan-Verdrahtung über den `TestClient` prüft, ist grün, ohne
dass die Verdrahtung existiert.

## Verworfene Ansätze

**Alles im Scheduler-Worker (Cron-Trigger nachrüsten).** Der Worker müsste
Kernbetriebszeit, Display-Zustand und Suspend-Status über HTTP erfragen und die
Weckzeit dem Backend mitteilen — alle Entscheidungen lägen dann ohnehin dort.
Das Wecken kann er prinzipiell nicht selbst leisten, weil `wake_at` nur beim
Suspend gesetzt wird und der Suspend im Backend passiert.

**Eigenständiges Subsystem neben dem Scheduler.** Verschenkt Historie, Toggle
und Dashboard-Darstellung und widerspricht der Vorgabe, dass das Feature zum
Scheduler gehört.

## Architektur

Die Logik lebt in einem neuen, eigenständig testbaren Modul
`backend/app/services/power/scheduled_reboot.py`. Der 60-Sekunden-Tick in
`_schedule_check_loop()` ruft es mit einem einzigen Aufruf auf — dasselbe
Verhältnis, das die Schleife heute zum RTC-Guard hat. `sleep.py` hat bereits
1690 Zeilen; das Feature darf sie nicht weiter aufblähen.

Im Scheduler erscheint es als Registry-Eintrag `system_reboot`. Dadurch
funktionieren Toggle, Konfiguration, Historie und Dashboard-Karte ohne
Sonderweg. Der Worker registriert dafür **keinen** APScheduler-Job.

```
Scheduler-Sicht                    Power-Layer (Ausführung)
────────────────                   ────────────────────────
SCHEDULER_REGISTRY["system_reboot"]
scheduler_configs (Konfig+Toggle) ──┐
scheduler_executions (Historie)   ←─┤
                                    │
                          scheduled_reboot.py
                                    │  gelesen/geschrieben im 60s-Tick
                          scheduled_reboot_state (Zustand über den Reboot)
                                    │
                      ┌─────────────┼─────────────┐
              enter_true_suspend  Gates    lifespan (Boot)
              (wake_at-Klemmung)
```

## 1. Datenmodell

### 1.1 Registry-Eintrag

In `SCHEDULER_REGISTRY` (`backend/app/schemas/scheduler.py`):

```python
"system_reboot": {
    "display_name": "Geplanter Neustart",
    "description": "Startet das System zu einem festen Wochentermin vollständig neu",
    "config_key": None,
    "default_interval": 604800,   # nur Formalie, s. Abschnitt 9
    "can_run_manually": False,
},
```

### 1.2 Konfiguration — `scheduler_configs`, Zeile `system_reboot`

Kein neues Table. `is_enabled` ist der Feature-Schalter; **kein Row bedeutet
deaktiviert**, deshalb bekommt `SchedulerService._check_scheduler_enabled()`
(und das Pendant `SchedulerWorker._is_scheduler_enabled()`) einen expliziten
`system_reboot`-Zweig, der `False` zurückgibt. Ohne diesen Zweig greift der
`return True`-Fallback am Ende beider Funktionen und das Feature wäre ab
Installation scharf.

`extra_config` (JSON):

| Feld | Typ | Default | Bedeutung |
|---|---|---|---|
| `weekday` | int 0–6 | `6` (Sonntag) | Mo=0 … So=6, wie `CoreUptimeWindow.weekdays` |
| `time` | "HH:MM" | `"04:00"` | server-lokal, wie die Kernbetriebszeit |
| `retry_window_hours` | int 1–24 | `6` | Nachholfrist ab dem Termin |
| `warning_lead_minutes` | int 0–120 | `10` | Vorwarnung; `0` schaltet sie ab |

Validierung über ein Pydantic-Schema `RebootScheduleConfig` in
`backend/app/schemas/scheduler.py`, das der Config-Route für diesen einen
Scheduler-Namen vorgeschaltet wird. `extra_config` bleibt für alle anderen
Scheduler ein freies Dict.

### 1.3 Zustand — neue Tabelle `scheduled_reboot_state` (Singleton, `id=1`)

Bewusst getrennt von `extra_config`: Konfiguration ist, was der Admin gesetzt
hat; Zustand ist, wo der Automat gerade steht. Und bewusst getrennt von
`scheduler_executions`: der Zustand wird beim Boot in `lifespan` gelesen, bevor
irgendein Scheduler-Code läuft.

| Spalte | Typ | Bedeutung |
|---|---|---|
| `id` | int PK | immer 1 |
| `phase` | str(24) | `idle` \| `armed` \| `executing` \| `resuspend_pending` |
| `due_at` | timestamptz? | konkreter Termin, auf den gerade gezielt wird |
| `deadline_at` | timestamptz? | `due_at + retry_window_hours` |
| `woke_for_reboot` | bool | die Box wurde für diesen Termin aus dem Suspend geholt |
| `resuspend_wake_at` | timestamptz? | der vom Termin verdrängte reguläre Weckzeitpunkt; `NULL` = keiner |
| `execution_id` | int? | zugehörige `scheduler_executions.id` |
| `last_skip_reason` | str(64)? | Gate, das zuletzt blockiert hat |
| `warned_for_due_at` | timestamptz? | verhindert eine zweite Vorwarnung pro Termin |
| `phase_entered_at` | timestamptz | Timeout-Basis für `resuspend_pending` |
| `updated_at` | timestamptz | |

Alembic-Migration. **Achtung:** die neue Revision muss auf den echten
`alembic heads` aufsetzen, nicht auf den Head der lokalen Dev-DB — das hat
schon einmal einen Multi-Head-Deploy-Fehler verursacht (PR #123 → #124).

Alle Zeitspalten `timezone=True`, konsistent mit `sleep_state_logs` und
`system_lifecycle_events`. Die Termin-Berechnung selbst arbeitet in
**server-lokaler naiver Zeit**, wie die Kernbetriebszeit; die Umrechnung nach
UTC passiert genau an der Speichergrenze.

## 2. Terminberechnung

Zwei reine Helfer in `scheduled_reboot.py`, gespiegelt von
`next_core_uptime_start()`. Beide arbeiten in server-lokaler naiver Zeit.

```python
def next_weekday_occurrence(now: datetime, weekday: int, time_hhmm: str) -> datetime:
    """Nächstes Vorkommen von (Wochentag, Uhrzeit) strikt NACH `now`."""

def due_occurrence(
    now: datetime, weekday: int, time_hhmm: str, within: timedelta
) -> Optional[datetime]:
    """Jüngstes Vorkommen <= `now`, sofern es höchstens `within` zurückliegt."""
```

`next_weekday_occurrence` iteriert `day_offset` von `0` bis **einschließlich 7**.
Die Sieben ist kein Schreibfehler: fällt `now` auf den Zieltag, aber nach der
Zielzeit, liegt das nächste Vorkommen exakt sieben Tage später — mit `0..6` käme
`None` heraus. Dieselbe Falle ist in `next_core_uptime_start()` dokumentiert.

Die Trennung ist nötig, weil der Automat zwei verschiedene Fragen stellt:
`next_weekday_occurrence` beantwortet „wann muss ich wecken und wann warnen",
`due_occurrence` beantwortet „ist gerade ein Termin fällig, den ich noch
nachholen darf". Die zweite Frage über die erste zu beantworten geht nicht —
sie liefert per Definition nur Zukunft.

## 3. Zustandsautomat

Getaktet im 60-Sekunden-Tick von `_schedule_check_loop()`, eingefügt **nach**
dem Kernbetriebszeit-Block (der `in_core` berechnet und den Inhibitor
abgleicht) und **vor** der `if not config or not config.schedule_enabled:
continue`-Zeile — sonst wäre das Feature an den Sleep-Zeitplan gekoppelt, den
es gar nicht braucht.

Der gesamte Tick ist in `try/except` gekapselt und darf die Schleife nie
abreißen lassen; ein Fehler wird geloggt und der Zustand unverändert gelassen.

### `idle`

1. Feature aus → nichts tun.
2. `due = next_weekday_occurrence(now, weekday, time)`.
3. **Vorwarnung:** ist die Box wach, `warning_lead_minutes > 0`,
   `due - now <= lead` und `warned_for_due_at != due` → `lifecycle.reboot_scheduled`
   senden, `warned_for_due_at = due` speichern.
   Ist die Box suspendiert, entfällt die Vorwarnung ersatzlos. Die Alternative
   wäre, die Box zehn Minuten früher zu wecken, um um 3:50 Uhr ein Push aufs
   Handy zu schicken — Lärm ohne Empfänger, plus unnötige Wachzeit.
4. **Fälligkeit:** `fällig = due_occurrence(now, weekday, time, retry_window)`.
   Ist das nicht `None`, wird gearmt: `phase=armed`, `due_at = fällig`,
   `deadline_at = fällig + retry_window`, `scheduler_executions`-Zeile anlegen
   (`trigger_type="scheduled"`, `status="running"`), `execution_id` merken.

   Dass die Fälligkeit über `due_occurrence` statt über einen Vergleich mit
   `next_weekday_occurrence` läuft, ist der Kern der Nachholmechanik: ein
   Termin, der um 04:00 blockiert war und um 04:00:30 durch einen Neustart des
   Backends seinen Zustand verloren hätte, wird um 04:01 wieder als fällig
   erkannt, solange die Frist läuft.

### `armed`

1. `now > deadline_at` → Execution auf `cancelled` mit
   `error_message = last_skip_reason`, `lifecycle.reboot_skipped` senden,
   `phase=idle`, `woke_for_reboot` und `resuspend_wake_at` löschen.
   Wurde die Box für diesen Termin geweckt und ist er dann verfallen, bleibt
   sie wach — die normale Auto-Idle- bzw. Suspend-on-Exit-Mechanik schickt sie
   wieder schlafen, sobald sie idle ist. Ein eigener Sonderweg dafür wäre
   doppelte Logik.
2. Gates prüfen (Abschnitt 4). Blockiert → `last_skip_reason` schreiben, warten.
3. Gates offen → ausführen (Abschnitt 5).

### Boot

`lifespan` liest den Zustand, bevor die Lifecycle-Startmeldung rausgeht
(Abschnitt 7).

### `resuspend_pending`

Der Sleep-Loop suspendiert, sobald das System idle und unbeaufsichtigt ist, mit
`wake_at = resuspend_wake_at` und dem neuen Trigger
`SleepTrigger.SCHEDULED_REBOOT`. `resuspend_wake_at` darf dabei `None` sein —
dann suspendiert die Box ohne RTC-Alarm, weil es ohne Kernbetriebszeit-Fenster
schlicht keinen regulären Aufwachzeitpunkt gibt. Gelingt das binnen 30 Minuten nach
`phase_entered_at` nicht, wird `phase=idle` gesetzt und eine Logzeile
geschrieben — die normale Auto-Idle- und Suspend-on-Exit-Mechanik übernimmt
dann. Ohne dieses Timeout bliebe die Box im Sonderzustand hängen, falls
dauerhaft Last anliegt.

## 4. Gates

Der Reihe nach; der erste Treffer gewinnt, wird als `last_skip_reason`
gespeichert und in der Skip-Meldung im Klartext genannt.

| # | Gate | Quelle | Grund |
|---|---|---|---|
| 1 | Kernbetriebszeit aktiv | `core_uptime_helpers.is_in_core_uptime(now, windows)` | Das Fenster ist eine Verfügbarkeitszusage. Ein Neustart bricht SMB-Sessions, Sync und Uploads ab, auch wenn kein Monitor an ist. |
| 2 | Display an | eigene Abfrage, s. u. | Jemand sitzt an der Box. Einziges Nutzungssignal — bewusst nicht Presence, nicht Gaming, nicht Session-Lock. |
| 3 | Laufender Scheduler-Job | `scheduler_executions.status == "running"`, eigene Zeile ausgenommen | Ein Neustart mitten im automatischen Backup hinterlässt ein halbes Backup. |
| 4 | Aktiver Upload | `_get_activity_metrics().active_uploads > 0` | Abgebrochener Upload ist Datenverlust für den Nutzer. |

**Display-Abfrage.** Nicht `gaming_presence.displays_on()` direkt aufrufen:
die Funktion liefert im Dev-Mode hart `True` (für das Gaming-Gate die harmlose
Richtung, hier die fatale). `scheduled_reboot.py` bekommt ein eigenes
`_displays_block()`, das im Dev-Mode `False` liefert und in Prod
`get_active_display_count_sync() > 0` auswertet. Eine unlesbare sysfs-Angabe
zählt hier als **„Display an"** und blockiert — die Gegenrichtung zum
Gaming-Gate. Ein Neustart ist die eingreifendere Aktion; bei Unwissen wird er
verschoben, nicht durchgezogen.

Bewusst **nicht** als Gate: Web-Presence, laufendes Spiel, fremde
logind-Inhibitoren, Session-Lock. Ein laufendes Spiel bedeutet zwingend ein
eingeschaltetes Display und ist damit von Gate 2 abgedeckt.

## 5. Ausführung

```
1. lifecycle.reboot_started senden (best effort, 3s Timeout — wie
   emit_system_suspend es vor dem Kernel-Suspend macht)
2. phase = "executing", phase_entered_at  →  COMMIT
3. sudo systemctl reboot
```

`resuspend_wake_at` wird hier **nicht** berechnet — es steht schon in der Zeile
(Abschnitt 6a). Wurde die Box für diesen Termin aus dem Suspend geholt, hat der
Suspend-Pfad dort den Weckzeitpunkt hinterlegt, den der Termin verdrängt hat.
War die Box ohnehin wach, ist `woke_for_reboot` falsch und sie bleibt nach dem
Neustart wach — „erneut suspenden" gilt nur für den Fall, aus dem sie geholt
wurde. Die normale Auto-Idle- und Suspend-on-Exit-Mechanik greift danach wie
sonst auch.

Schritt 2 **vor** Schritt 3, und mit eigenem Commit. Nach dem Reboot ist diese
Zeile der einzige Beweis, dass es ein geplanter Neustart war; wird sie erst
danach geschrieben, wird sie nie geschrieben.

Scheitert Schritt 4 (fehlender sudoers-Eintrag, `systemctl` nicht gefunden),
wird `phase=idle` gesetzt, die Execution auf `failed` mit der stderr-Ausgabe,
und `lifecycle.reboot_skipped` mit dem technischen Grund gesendet. Fail-closed:
lieber kein Neustart als ein halber Zustand.

Die Reboot-Ausführung selbst liegt hinter einer kleinen Abstraktion, damit sie
im Dev-Mode nur loggt — dasselbe Muster wie `DevSleepBackend`.

## 6. Weck- und Wieder-Suspend-Choreografie

Drei Eingriffe, alle an bestehenden Stellen:

**a) Gemeinsame Weckzeit — und das Merken des verdrängten Termins.**
`enter_true_suspend()` klemmt heute auf `next_core_uptime_start()`. Neu:

```
regulär  = min(wake_at des Aufrufers, next_core_uptime_start(now))   # heutiges Ergebnis
reboot   = next_weekday_occurrence(...)  falls Feature aktiv, sonst None

wenn reboot ist nicht None und (regulär ist None oder reboot < regulär):
    wake_at = reboot
    scheduled_reboot_state.woke_for_reboot   = True
    scheduled_reboot_state.resuspend_wake_at = regulär    # darf None sein
sonst:
    wake_at = regulär
```

Der Neustart-Termin stiehlt die Weckzeit und legt die gestohlene daneben. Genau
das ist „bis zum regulären Aufwachzeitpunkt": nicht ein nach dem Neustart neu
geratener Wert, sondern derselbe, der ohne den Neustart gegolten hätte.

`woke_for_reboot` und `resuspend_wake_at` werden zurückgesetzt, sobald der
Automat nach `idle` zurückkehrt — auch auf dem Deadline-Pfad. Sonst würde ein
später eintreffender, ganz anderer Termin den alten Weckzeitpunkt erben.

**b) RTC-Guard.** `SleepManagerService._next_core_start_for_guard()` gibt
denselben Helper zurück. Ohne das verschläft die Box den Termin genau dann,
wenn PowerDevil den Suspend ausgelöst hat statt BaluHost — und das ist auf einer
KDE-Gaming-Box kein Randfall.

**c) Ein scharfer Neustart verdrängt einen Auto-Suspend.** Steht der Automat auf
`armed` und sind die Gates offen, wird neu gestartet statt suspendiert. Ohne
diese Regel suspendiert die Box und weckt sich per RTC eine Sekunde später
wieder auf, nur um dann neu zu starten. Umgesetzt dadurch, dass der
`scheduled_reboot`-Tick **vor** den Suspend-Entscheidungen der Schleife läuft
und im Erfolgsfall gar nicht mehr zurückkehrt (der Prozess ist weg).

Neuer Enum-Wert `SleepTrigger.SCHEDULED_REBOOT = "scheduled_reboot"` in
`backend/app/schemas/sleep.py`, plus deutsches Label in
`notifications/lifecycle_helpers.py:_TRIGGER_LABELS_DE`. Der Trigger ist
**nicht** `MANUAL` — die bestehenden Defensiv-Guards in `enter_true_suspend()`
(Kernbetriebszeit, Presence, Gaming, fremde Inhibitoren) sollen für den
Wieder-Suspend ausdrücklich gelten.

## 7. Notifications

Vier neue Ereignistypen in der **bestehenden** Kategorie `lifecycle`, damit das
vorhandene Routing über `receive_lifecycle` ohne Migration greift. Eine neue
Kategorie würde einen Eintrag in `_CATEGORY_FIELD_MAP`
(`services/notification_routing.py`) plus Modell- und Schema-Änderung verlangen,
ohne dass ein Nutzer sie getrennt abbestellen wollen dürfte.

| EventType | Prio | Wann | Inhalt |
|---|---|---|---|
| `lifecycle.reboot_scheduled` | 1 | `lead` Minuten vorher, nur wenn wach | „Geplanter Neustart um 04:00" |
| `lifecycle.reboot_started` | 2 | unmittelbar vor `systemctl reboot` | „Wartungsneustart läuft" |
| `lifecycle.reboot_completed` | 1 | beim Boot | „Neustart abgeschlossen", mit Downtime |
| `lifecycle.reboot_skipped` | 1 | bei Deadline-Ablauf oder Ausführungsfehler | „Neustart verschoben — Displays aktiv" |

Kein Cooldown, wie bei `shutdown`/`startup`: ein geplanter Neustart muss immer
melden.

**Verdrängung der generischen Meldungen.** `_emit_lifecycle_shutdown()` und
`_emit_lifecycle_startup()` in `core/lifespan.py` lesen
`scheduled_reboot_state.phase`. Steht sie auf `executing`, senden sie die
spezifische Variante statt „System heruntergefahren" / „System gestartet".

Zwei Dinge bleiben dabei unangetastet:

- Die Zeilen in `system_lifecycle_events` werden weiter geschrieben. Aus ihnen
  berechnet der nächste Start die Downtime; entfielen sie, wäre die Angabe in
  `reboot_completed` falsch.
- Die Reihenfolge „Row zuerst, Push danach" bleibt. Der Push ist auf 3 Sekunden
  begrenzt und darf den Shutdown nie aufhalten.

`_emit_lifecycle_startup()` schaltet nach der Abschlussmeldung den Automaten
weiter: Execution auf `completed`, dann `phase = resuspend_pending`, falls
`woke_for_reboot` gesetzt ist, sonst `idle`. Maßgeblich ist das Flag, nicht
`resuspend_wake_at` — letzteres darf legitim `None` sein (Suspend ohne
RTC-Alarm), und eine Prüfung darauf würde genau diesen Fall wach lassen.

## 8. API und Rechte

Keine neue Schreibroute. `PUT /api/schedulers/system_reboot/config` und
`POST /api/schedulers/system_reboot/toggle` hängen bereits an
`Depends(deps.get_current_admin)` und sind über
`@user_limiter.limit(get_limit("admin_operations"))` ratenbegrenzt. Damit ist
„nur Admins verwalten" ohne neue Rechte-Logik erfüllt.

Die Konfigurations-Route validiert `extra_config` für diesen Scheduler-Namen
gegen `RebootScheduleConfig` und beantwortet ungültige Werte mit 422 statt sie
als freies Dict zu speichern.

Jede Änderung an Termin oder Toggle wird über `get_audit_logger_db()`
protokolliert — ein automatischer Hardware-Neustart ist eine
sicherheitsrelevante Konfiguration.

**Neue Leseroute** `GET /api/schedulers/system_reboot/preview` (Admin):

```json
{
  "enabled": true,
  "next_due_at": "2026-09-13T04:00:00+02:00",
  "in_core_uptime": true,
  "window_label": "Wochentags 08:00–22:00",
  "window_ends_at": "2026-09-13T22:00:00+02:00",
  "retry_deadline_at": "2026-09-13T10:00:00+02:00",
  "reachable": false
}
```

Serverseitig gerechnet, weil die Kollisionsregel dieselbe sein muss wie die im
Tick. Zwei Implementierungen derselben Regel driften auseinander; die
Kernbetriebszeit-Helfer sind bereits reine Funktionen und direkt
wiederverwendbar.

`reachable: false` ist der Fall, den die Warnung im UI erklären muss: der
Termin liegt im Fenster, und das Fenster endet **nach** der Nachholfrist — der
Neustart läuft also nie.

## 9. Frontend

**`SchedulerConfigModal.tsx`** bekommt einen `system_reboot`-Zweig:
Wochentag-Auswahl, Uhrzeit, Nachholfrist, Vorwarnzeit. Bestehende
Intervall-Steuerung wird für diesen Scheduler ausgeblendet — er hat kein
Intervall.

**Die Kernbetriebszeit-Warnung** wird live beim Wählen aus dem
Preview-Endpunkt geholt und ist **nicht blockierend** (das Fenster kann später
geändert werden). Der Text nennt die Rechnung konkret, nicht nur den Konflikt:

> Dieser Termin liegt in der Kernbetriebszeit „Wochentags 08:00–22:00". Der
> Neustart wird jede Woche übersprungen. Das Fenster endet um 22:00 — das sind
> 12 Stunden nach dem Termin und damit außerhalb der Nachholfrist von 6
> Stunden. **Der Neustart läuft so nie.**

Bei Kollision mit erreichbarer Nachholphase entsprechend milder: „… wird
übersprungen und um 22:00 nachgeholt."

**`SchedulerCard`**: `interval_display` würde für diesen Eintrag „Alle 7 Tage"
zeigen — nicht falsch, aber nutzlos. `SchedulerService._get_scheduler_status()`
leitet die Anzeige für `system_reboot` stattdessen aus `extra_config` ab
(„Sonntag 04:00"). `can_run_manually: false`, also kein „Jetzt ausführen"-Knopf:
er liefe durch den Scheduler-Worker, der den Reboot gar nicht ausführt.

**i18n**: `de` und `en`, im vorhandenen Scheduler-Namespace. Die
Warnung enthält Platzhalter — ein fehlender `{{platzhalter}}` in einer
Locale-Datei ist nur über einen Vertragstest gegen die JSON-Datei selbst
auffindbar, weil der `react-i18next`-Mock Interpolation erfindet.

## 10. Deployment

Neue Zeile in `deploy/install/templates/sudoers-baluhost-power`:

```
# BaluHost: geplanter Wartungsneustart (services/power/scheduled_reboot.py).
# Genau ein Verb, genau eine Form, keine Argumente, keine Wildcards.
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/systemctl reboot
```

Die Zeile erreicht eine bestehende Box **nur** über einen
`SYNC_PERMISSIONS=1`-Deploy oder den manuellen Aufruf des zugehörigen
`install-*-sudoers.sh`. Ein Routine-Deploy rendert die Templates nicht neu. Bis
dahin schlägt der Neustart sauber fehl (Execution `failed`, Notification mit
Grund) — fail-closed, kein halber Zustand.

Der Eintrag ist der weitreichendste in dieser Datei: er beendet jeden Dienst auf
der Box. Er wird deshalb als eigener Punkt in „Known Gaps & Accepted Risks" in
`.claude/rules/ci-cd-security.md` dokumentiert, mit dem Hinweis, dass die
Auslösung hinter dem Admin-Gate, dem Default-Aus und den vier Gates liegt.

Der Neustart lässt keine Zeit für einen sauberen Dienst-Stopp jenseits dessen,
was systemd ohnehin macht. Das ist akzeptabel: `systemctl reboot` fährt die
Units geordnet herunter, und `_emit_lifecycle_shutdown()` läuft dabei als
normaler Shutdown-Pfad des Backends.

## 11. Tests

**Reine Helfer** (`tests/services/test_scheduled_reboot_helpers.py`):
`next_weekday_occurrence` über die Wochengrenze, am Zieltag vor und nach der
Zielzeit (der `day_offset=7`-Fall), und `next_scheduled_wakeup` als Minimum aus
Kernbetriebszeit und Reboot-Termin, inklusive der Fälle „nur eines von beiden
konfiguriert" und „keines".

**Zustandsautomat** (`tests/services/test_scheduled_reboot_state.py`), im Stil
von `test_sleep_core_uptime_integration.py`: armen bei Fälligkeit; jedes der
vier Gates blockiert einzeln und schreibt seinen Grund; Deadline-Ablauf setzt
`cancelled` und sendet die Skip-Meldung; ein blockierter Termin feuert beim
ersten offenen Tick innerhalb der Frist; Feature aus armt nie.

**Suspend-Verdrängung**: bei `phase=armed` und offenen Gates wird neu gestartet
statt suspendiert.

**Klemmung und Merken**: `enter_true_suspend(wake_at=None)` mit einem
Reboot-Termin vor dem nächsten Kernbetriebszeit-Start ergibt den Reboot-Termin
als `wake_at`, setzt `woke_for_reboot=True` und legt den
Kernbetriebszeit-Start als `resuspend_wake_at` ab. Umgekehrt (Termin liegt
später) bleibt `wake_at` der Kernbetriebszeit-Start und `woke_for_reboot`
falsch. Dritter Fall: Feature aktiv, aber keine Kernbetriebszeit-Fenster
konfiguriert → `wake_at` ist der Reboot-Termin, `resuspend_wake_at` ist `None`.

**Boot-Übergabe**: `phase=executing` führt zu `reboot_completed` statt
`lifecycle.startup`, setzt die Execution auf `completed` und schaltet je nach
`woke_for_reboot` auf `resuspend_pending` oder `idle` — inklusive des Falls
`woke_for_reboot=True` bei `resuspend_wake_at=None`. Der Test läuft
**direkt gegen `_emit_lifecycle_startup()`**, nicht über den `TestClient`:
`conftest` setzt `SKIP_APP_INIT=1`, `_startup()` läuft in Tests nie, und ein
TestClient-Test wäre grün, ohne dass die Verdrahtung überhaupt existiert.

**Dev-Mode**: `_displays_block()` liefert im Dev-Mode `False`, damit das Feature
lokal auslösbar ist; die Reboot-Abstraktion loggt nur.

**Frontend** (Vitest): der Warntext erscheint bei `reachable: false`, in der
milderen Variante bei erreichbarer Nachholphase, und gar nicht ohne Kollision.
Dazu ein Vertragstest, dass die Platzhalter der Warnung in `de.json` und
`en.json` tatsächlich vorhanden sind.

## Offene Punkte für die Implementierung

- Der Prod-Provisioning-Schritt (`SYNC_PERMISSIONS=1`-Deploy für den
  sudoers-Eintrag) ist ein einmaliger Ops-Schritt und gehört in die PR-
  Beschreibung, nicht in den Code.
- Die Nachholfrist läuft bewusst nicht über einen Suspend hinweg neu an: wacht
  die Box innerhalb der Frist auf, wird der Termin nachgeholt; wacht sie später
  auf, ist er verfallen. Das ist gewollt und wird so getestet.
