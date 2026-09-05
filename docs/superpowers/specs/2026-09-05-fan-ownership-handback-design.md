# Regelung beim Dienst-Ende an die Board-Automatik zurückgeben

**Status:** Design freigegeben (2026-09-05), nach kritischer Review auf den
Shutdown-Pfad zurückgenommen
**Issue:** #534 (Teilumfang — Punkte 1 und 2 des Issues bleiben offen)
**Branch:** `feat/fan-ownership-handback-534` (von `main`)
**Voraussetzung:** #517/#480 (PR #537), #533 (PR #539), #532 (PR #550) sind gemergt.

## Kontext

BaluHost nimmt die Kontrolle über jeden schreibbaren Lüfter und gibt sie nie
zurück. Beim Dienst-Ende — und das Backend startet bei **jedem Deploy** neu —
bleibt `pwm_enable=1` stehen: die Board-Automatik ist abgeschaltet, der PWM
friert auf dem letzten Wert ein, und bis der Dienst wieder läuft, regelt
niemand.

### Was der Ist-Zustand tatsächlich ist

Der Issue-Text nimmt an, `pwm_enable` werde einmal beim Start auf `1` gesetzt.
Das stimmt nicht: **`set_pwm` schreibt `pwm_enable=1` bei jedem einzelnen
PWM-Write** (`fan_backend_linux.py:182-190`). BaluHost übernimmt die Kontrolle
alle fünf Sekunden neu.

Der Ursprungswert wird nirgends gesichert (`fan_backend_linux.py:510` legt nur
`pwm_enable_path` ab). `stop()` bricht heute ausschliesslich die
Monitoring-Task ab (`fan_control.py:210-219`). Ein Aufhängepunkt existiert:
`_shutdown()` ruft `stop_fan_control()` primary-gegated auf (`lifespan.py:747`
Gate, `:759` Aufruf).

Ein Muster für Sicherung und Rückgabe gibt es bereits, aber nur für den
AMD-Pfad: `AmdManualState` in `fan_gpu_manual.py:24-30`, `:65-78`.

### Die Prämisse ist gemessen, nicht angenommen

Auf BaluNode (2026-09-05), Kanal 1 des nct6798, Dienst gestoppt:

| | `pwm1_enable` | `pwm1` | RPM |
|---|---|---|---|
| BaluHost regelt | 1 | 76 | — |
| nach `echo 5` | 5 | **87** | 508 |
| nach Dienststart | 1 | 87 | — |

`pwm1` wanderte ohne fremden Schreibzugriff von 76 auf 87 — der Chip hat die
Regelung übernommen. Smart Fan IV greift wirklich.

### Warum nur der Shutdown-Pfad

Der ursprüngliche Entwurf deckte alle drei Punkte des Issues ab. Zwei kritische
Reviews fanden darin acht blockierende Befunde; **sechs davon entfielen
ausschliesslich auf die zwei Laufzeit-Auslöser** („nicht steuerbar",
„Regelung ausgefallen"), und beide sicherheitsrelevanten Fälle ebenfalls.

Der Shutdown-Pfad braucht keinen Eingriff in den Regelkreis, keine
Backoff-Introspektion, keinen Rückhol-Endpunkt und **keine UI-Anzeige** — und
damit auch nicht den worker-übergreifenden Zustand, an dem die zwei
Laufzeit-Auslöser scheitern (siehe #552: prozesslokale Flags erzeugen ein
flackerndes Read-Only-Banner, weil `get_status()` in einem beliebigen Worker
läuft).

Die Befunde zu den beiden verbleibenden Punkten sind in #534 dokumentiert.

## Ziele

- Beim Dienst-Ende die Kontrolle an die Board-Automatik zurückgeben.

## Nicht-Ziele

- **Keine Laufzeit-Rückgabe** (Punkte 1 und 2 des Issues). Bleiben offen.
- Keine UI-Anzeige und kein neues Feld in `FanInfo`.
- Keine Änderung an Regelkreis, Kurvenauswertung, Notfallpfad oder dem Backoff
  aus #533.
- **Keine Rückgabe für AMD-GPU-Lüfter.** Für sie existiert mit
  `AmdManualState` / `disable_amd_manual` (`fan_gpu_manual.py:65-78`) bereits
  ein eigener Rückgabeweg, der zusätzlich `power_dpm_force_performance_level`
  zurücksetzt. Zwei konkurrierende Mechanismen auf demselben Knoten wären ein
  Fehler. Ausgeschlossen wird über `gpu_vendor == "amd"`, nicht über
  `FIRMWARE_MANAGED` — Letzteres deckt Pre-RDNA3-Karten nicht ab.

### Die Grenze, die keine Lösung beseitigt

Bei `SIGKILL` gibt es keine Rückgabe. `systemctl stop` und der Deploy-Neustart
senden `SIGTERM`, dort greift der Shutdown-Pfad. Ein hartes Kill oder ein
Stromausfall hinterlässt die Lüfter auf dem letzten Wert — das ist der heutige
Zustand und im Prozess selbst nicht behebbar.

---

## 1. Besitz

Ein Lüfter gilt als **besessen**, sobald ein `pwm_enable=1`-Write auf ihm
gelungen ist. Nicht der Wert-Write — der `pwm_enable`-Write *ist* die
Übernahme, er schaltet die Board-Automatik ab.

Der Unterschied ist nicht akademisch: gelingt `pwm_enable=1` und scheitert der
Wert-Write, hat BaluHost die Automatik abgeschaltet, ohne selbst regeln zu
können. Genau dieser Lüfter muss zurückgegeben werden.

### Besitz wird nur im Primary-Worker erworben

**Nicht** am `monitoring`-Flag festgemacht, sondern hart an
`getattr(lifespan, "IS_PRIMARY_WORKER", False)` — als Attributzugriff auf das
Modul, nie als `from ... import` (das Flag wird erst zur Laufzeit gesetzt;
Muster wie in `fan_control.py:250`).

Grund: `set_pwm` ist auf **jedem** Worker erreichbar, über drei Wege:

1. `POST /api/fans/pwm` (`routes/fans.py:167` → `fan_control.py:1003`) — läuft
   im bedienenden Worker, bei vier Workern also meist auf einem Sekundär.
2. `POST /api/admin/services/fan_control/stop` (`routes/service_status.py:174`
   → `service_registry.py:207`) — ruft `stop_fan_control()` im bedienenden
   Worker.
3. `.../restart` bzw. `/start` (`service_status.py:292`, `:438`) — ruft
   `start_fan_control()` **ohne Argument**, also mit `monitoring=True`
   (`fan_control.py:1287`); ein Sekundär-Worker startet dann eine vollwertige
   zweite Regelschleife.

Ohne das Primary-Gate erwürbe ein Sekundär-Worker über Weg 1 Besitz, und Weg 2
gäbe die Lüfter dann ans Board zurück, während der Primary weiterregelt.

Weg 3 ist ein eigenständiger, vorbestehender Fehler — zwei konkurrierende
Regelschleifen — und **nicht Gegenstand dieser Arbeit**; er ist als
Nebenbefund festzuhalten.

### Der Zustand

Neues Modul `backend/app/services/power/fan_ownership.py`, prozesslokal,
`fan_id → besessen`. Prozesslokal ist hier ausreichend und richtig, weil der
Zustand **nirgends ausgelesen** wird: keine API, keine UI. Er dient
ausschliesslich dazu, beim Beenden zu wissen, was zurückzugeben ist.

---

## 2. Der Rückgabewert

### Gesichert wird beim Scan, persistiert wird im Service

`_scan_pwm_fans` liest `pwm_enable` in den Cache (`pwm_enable_at_scan`) —
**mehr nicht**. `LinuxFanControlBackend` kennt keine Datenbank
(`fan_backend_linux.py:45-58`), und der Scan läuft in jedem Worker, vor dem
Identitäts-Abgleich und vor der Anlage-Schleife.

Persistiert wird in `_load_fan_configs`, **im Primary**, **nach** dem
Reconcile-Commit (`fan_control.py:351`) und **nach** dem Primary-Gate
(`:426`), ausschliesslich als **UPDATE auf existierende Zeilen — nie als
INSERT**.

Ein Upsert an dieser Stelle legte eine frische Zeile mit `updated_at="jetzt"`
an, die im nächsten Identitäts-Abgleich gegen die echte Nutzerkurve gewönne
(`fan_reconcile.py:151`) — genau der Datenverlust, den #532 beseitigt hat.
`test_fan_reconcile_wiring.py:202-275` bewacht diesen Fall.

Dass der Wert beim allerersten Erscheinen eines Lüfters einen Startzyklus
später ankommt, ist der richtige Preis. Der Docstring von `_load_fan_configs`
(„Existing configs are NOT modified", `:310-311`) gilt dann nicht mehr und ist
mitzuziehen.

### Gültige Zielwerte

**Weder `0` noch `1`.** `1` ist Handsteuerung. `0` bedeutet nach
hwmon-Konvention „keine Regelung durch den Chip" — beim nct6775 Vollgas, also
gerade **nicht** Board-Automatik. Ein persistiertes `0` fährt die Lüfter nach
jedem Dienst-Ende auf Anschlag und zementiert das über die Sicherung.

Dass `1` kein Board-Default sein kann, ist eine **Entscheidung**, keine
Tatsache: BIOS-Profile („Manual", „Full Speed") hinterlassen durchaus `1` mit
fester Duty. Die Regel bleibt richtig — ein solcher Lüfter wird eben nicht
zurückgegeben —, aber sie behauptet nicht, der Fall existiere nicht.

### Herkunft mitspeichern

Zwei Spalten in `fan_configs`:

```
pwm_enable_restore         Integer, nullable
pwm_enable_restore_source  String(10), nullable   -- "observed" | "fallback"
```

Die zweite Spalte ist nicht Buchhaltung, sie schliesst ein Loch. Ohne sie hält
die Invariante „der Fallback wird nie gespeichert" **genau einen Neustart**:
der Shutdown schreibt den Fallback `5`, der nächste Scan liest `5` und
persistiert ihn als vermeintliche Beobachtung — der Scan kann unseren eigenen
Write nicht von einem BIOS-Wert unterscheiden. Die Annahme würde sich selbst
zementieren.

### Die Auflösungsregel

```
gelesener Wert in {0, 1}  ->  keine Beobachtung
                              gespeicherten Wert benutzen, falls vorhanden
                              sonst Treiber-Fallback benutzen, NICHT speichern

gelesener Wert sonst      ->  ist er gleich dem gespeicherten Wert mit
                              source="fallback"?  -> unveraendert lassen
                                 (das ist sehr wahrscheinlich unser eigener
                                  Rueckgabe-Write, keine Beobachtung)
                              sonst -> als Ziel benutzen und mit
                                       source="observed" persistieren

kein Fallback bekannt     ->  keine Rueckgabe, WARNING mit Treibernamen
```

Der mittlere Zweig ist der Kern: ein einmal geratener Fallback kann **nie** zur
Beobachtung aufsteigen. Deckt sich der echte Board-Wert zufällig mit dem
Fallback, bleibt er als `fallback` markiert — der Wert stimmt trotzdem.

### Der Fallback, als Annahme dokumentiert

| Treiber | Wert | Belegt durch |
|---|---|---|
| `nct6775` (deckt nct6798 ab) | `5` — Smart Fan IV | Messung oben: `pwm1` 76 → 87, 508 RPM |
| alles andere | keiner | keine Rückgabe, WARNING |

`amdgpu` steht bewusst **nicht** in der Tabelle (siehe Nicht-Ziele).

Dass für unbekannte Treiber nichts passiert, ist Absicht: ein geratener Modus
auf fremder Hardware ist schlechter als der heutige Zustand, und der heutige
Zustand ist bekannt.

Fehlt `pwm_enable_path`, gibt es weder Übernahme noch Rückgabe.

### Migration

Beide Spalten brauchen eine Alembic-Migration. **Die Elternrevision ist zum
Zeitpunkt der Umsetzung frisch über `alembic heads` zu prüfen**, nicht aus
diesem Dokument zu übernehmen — das Projekt hatte einen Deploy-Fehler durch
mehrere Heads.

---

## 3. Die Rückgabe

### Neue Backend-Methode

Heute gibt es **keinen Weg**, `pwm_enable` auf etwas anderes als `1` zu
schreiben: `_write_hwmon_file` ist privat, `set_pwm` schreibt den Literal `"1"`
(`fan_backend_linux.py:183`). Die Rückgabe braucht deshalb eine neue Methode
auf `FanControlBackend` (ABC: `fan_control.py:86-123`):

```python
async def release_to_board(self, fan_id: str, enable_value: int) -> bool: ...
```

Linux-Implementierung: schreibt den Wert, **liest ihn zurück** und meldet nur
dann Erfolg, wenn er anliegt. Das Rücklesen ist billig (`_read_hwmon_file`
existiert) und schliesst zwei Fälle: einen abgelehnten Modus (nicht jeder
nct67xx kennt `5` — bei gleichem Chip an gleicher ISA-Adresse ergibt ein
Board-Tausch dieselbe `fan_id`, aber nicht zwingend dieselbe Modus-Semantik)
und einen stillschweigend ignorierten Write.

Dev-Implementierung: no-op, gibt `True` zurück.

### Das Besitz-Signal

`set_pwm` verwirft heute das Ergebnis des `pwm_enable`-Writes:
`ok_enable, _ = ...` wird nur für eine DEBUG-Zeile benutzt
(`fan_backend_linux.py:183-186`), und der Rückgabewert von `set_pwm` spiegelt
ausschliesslich den Wert-Write (`:190`, `:199`, `:246`).

**Entscheidung: `set_pwm` markiert den Besitz selbst**, direkt nach einem
gelungenen `pwm_enable`-Write, über `fan_ownership`. Kein Zyklus —
`fan_backend_linux` importiert bereits aus `fan_control`, ein blattseitiges
`fan_ownership` ist unkritisch.

Die Alternative — den Rückgabetyp von `set_pwm` erweitern — zöge die ABC, das
Dev-Backend (`fan_backend_dev.py:138`) und mehrere Test-Doubles
(`test_fan_pwm_backoff.py:253`, `test_fan_firmware_managed_loop.py:28`) nach
sich, ohne dass irgendein anderer Aufrufer die Unterscheidung braucht.

### `stop()`

Reihenfolge: erst die Monitoring-Task abbrechen (heutiges Verhalten), **dann**
die Rückgabe. Umgekehrt schriebe die Schleife gegen die Rückgabe.

Für jeden besessenen Lüfter: Zielwert nach der Regel aus Abschnitt 2
auflösen, `release_to_board` aufrufen, Ergebnis pro Lüfter auf INFO,
Zusammenfassung am Ende. Schlägt eine Rückgabe fehl, ist das eine
**WARNING mit Treibername und Zielwert** — es ist der Fall, in dem niemand
regelt, und er darf nicht im Rauschen untergehen.

`stop()` ist mehrfach aufrufbar (Admin-Stop, danach Shutdown). Nach der
Rückgabe wird der Besitz geleert; ein zweiter Lauf findet nichts mehr und
schreibt nichts.

### `switch_backend`

`fan_control.py:1064-1090` tauscht das Backend aus, ohne zurückzugeben. Ein
Wechsel Linux → dev lässt jeden Kanal auf `pwm_enable=1` zurück, während
niemand mehr regelt — derselbe Zustand, den diese Arbeit beseitigt, nur über
einen Admin-Endpunkt. Die Rückgabe läuft deshalb auch dort, vor dem Tausch,
und der Besitz-Zustand wird geleert.

---

## 4. Tests und Verifikation

### Reine Einheiten

Die Auflösung des Rückgabewerts fasst weder sysfs noch Datenbank an und ist als
Tabelle prüfbar:

| gelesen | gespeichert (Wert / Herkunft) | Ergebnis | persistiert? |
|---|---|---|---|
| `5` | — | `5` | ja, `observed` |
| `5` | `5` / `fallback` | `5` | **nein** (bleibt `fallback`) |
| `5` | `2` / `observed` | `5` | ja, `observed` |
| `1` | `5` / beliebig | `5` | nein |
| `1` | — | Treiber-Fallback | **nein** |
| `0` | — | Treiber-Fallback | **nein** |
| `1` | — , Treiber unbekannt | keine Rückgabe + WARNING | nein |

Zeile 2 und Zeile 6 sind die wichtigsten: die eine verhindert, dass ein
geratener Fallback zur Beobachtung aufsteigt, die andere, dass „Vollgas" als
Board-Automatik festgeschrieben wird.

### Besitz

- `pwm_enable`-Write gelingt, Wert-Write scheitert → **besessen**. Der Fall,
  der die Definition trägt.
- `pwm_enable`-Write scheitert → **nicht besessen**, kein Rückgabe-Write bei
  `stop()`.
- **Sekundär-Worker: `POST /api/fans/pwm` erwirbt keinen Besitz.** Nicht über
  ein leeres Dict prüfen — das wäre tautologisch —, sondern über den echten
  Weg: Flag auf `False`, `set_pwm` aufrufen, danach `stop()`, und die
  `pwm1_enable`-Datei muss unverändert sein.

### Rückgabe

- Besessener Lüfter → nach `stop()` steht der Zielwert in der Datei.
- Nicht besessener Lüfter → Datei unverändert.
- **Rücklesen schlägt fehl** (Write geht durch, Wert liegt nicht an) →
  `release_to_board` meldet `False`, WARNING, kein stiller Erfolg.
- Zweiter `stop()`-Aufruf schreibt nichts.
- AMD-GPU-Lüfter wird nie zurückgegeben.

Aufbau über echte `tmp_path`-sysfs-Bäume, platform-förmig und doppelpunktfrei
(NTFS verbietet Doppelpunkte in Verzeichnisnamen — Lehre aus #532). Muster
liegen in `test_fan_pwm_backoff.py:28-51` und `test_fan_scan_stable_ids.py`.

### Persistenz

- Der Restore-Write ist ein **UPDATE**; für eine nicht existierende `fan_id`
  entsteht **keine** Zeile. Das ist der Test gegen die #532-Kollision.
- Er läuft nur im Primary und nur nach dem Reconcile-Commit.

### Gates

`pytest -k "fan or power"`, `ruff check`, `eslint .`, `npm run build`,
`vitest run`. Die Messlatte ist unmittelbar vor der Umsetzung einmal zu messen
und mit Datum zu notieren — die Zahl aus einem früheren Lauf ist keine
Messlatte. Volle Backend-Suite in der CI.

Frontend-Gates laufen mit, obwohl diese Arbeit das Frontend nicht anfasst.

### Feldverifikation

1. **Der Kern.** `systemctl stop baluhost-backend`, dann
   `cat /sys/class/hwmon/hwmon3/pwm{1,2,3,7}_enable`. Erwartung: viermal `5`
   statt viermal `1`. Heute steht dort `1`; das ist die Lücke.
2. **Die Herkunft.** Dienst starten, dann
   `SELECT fan_id, pwm_enable_restore, pwm_enable_restore_source FROM fan_configs WHERE is_active`.
   Erwartung: `5 / fallback` — **nicht** `5 / observed`. Steht dort `observed`,
   ist die Regel aus Abschnitt 2 verletzt und der Fallback hat sich selbst zur
   Beobachtung befördert. Das ist der Test, den die erste Fassung dieser Spec
   fälschlich als Erfolgsbeleg geführt hat.
3. **Der echte Wert.** Erst ein Kaltstart mit gestopptem Backend kann eine
   echte Beobachtung liefern: Rechner booten, Backend vor dem ersten
   Regelzyklus stoppen, `pwm_enable` lesen. Steht dort der BIOS-Wert, ist er
   die Beobachtung, die die Spalte dauerhaft füllen soll. Optional — der
   Fallback tut es bis dahin.

---

## Risiken

- **Der Treiber-Fallback ist eine Annahme**, für `nct6775` durch Messung
  gedeckt. Für alles andere wird bewusst nichts getan.
- **Die Rückgabe kann scheitern.** Sie wird zurückgelesen und im Fehlerfall als
  WARNING gemeldet; der Zustand ist dann derselbe wie heute.
- **Ob das Board nach der Rückgabe tatsächlich regelt**, ist auf BaluNode
  gemessen und für andere Hardware nicht garantiert. Da nur bei bekanntem
  Treiber zurückgegeben wird, ist das Risiko auf einen Fall begrenzt.
- **`SIGKILL` bleibt ungedeckt** (siehe Nicht-Ziele).
- **Zwei Regelschleifen über `/api/admin/services/fan_control/restart`** sind
  ein vorbestehender Fehler, den diese Arbeit nicht behebt und der als
  Nebenbefund festzuhalten ist.
