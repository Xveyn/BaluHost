# Regelung beim Dienst-Ende an die Board-Automatik zurückgeben

**Status:** Design freigegeben (2026-09-05); zweimal überarbeitet — zuerst auf
den Shutdown-Pfad zurückgenommen, dann nach einer zweiten Review auf
„nur beobachtete Werte" umgestellt
**Issue:** #534 (Teilumfang — Punkte 1 und 2 des Issues bleiben offen)
**Branch:** `feat/fan-ownership-handback-534` (von `main`)
**Voraussetzung:** #517/#480 (PR #537), #533 (PR #539), #532 (PR #550) sind gemergt.

## Kontext

BaluHost nimmt die Kontrolle über jeden geregelten Lüfter (`pwm_enable=1`) und
gibt sie nie zurück. Beim Dienst-Ende — und das Backend startet bei **jedem
Deploy** neu — bleibt die Board-Automatik abgeschaltet, der PWM friert auf dem
letzten Wert ein, und bis der Dienst wieder läuft, regelt niemand.

### Was der Ist-Zustand tatsächlich ist

Der Issue-Text nimmt an, `pwm_enable` werde einmal beim Start auf `1` gesetzt.
Das stimmt nicht: **`set_pwm` schreibt `pwm_enable=1` bei jedem einzelnen
PWM-Write** (`fan_backend_linux.py:182-190`). BaluHost übernimmt die Kontrolle
alle fünf Sekunden neu.

Der Ursprungswert wird nirgends gesichert (`fan_backend_linux.py:510` legt nur
`pwm_enable_path` ab). `stop()` bricht heute ausschliesslich die Monitoring-Task
ab (`fan_control.py:210-219`). Ein Aufhängepunkt existiert: `_shutdown()` ruft
`stop_fan_control()` primary-gegated auf (`lifespan.py:747` Gate, `:759` Aufruf).

Es gibt heute **keinen Weg**, `pwm_enable` auf etwas anderes als `1` zu
schreiben: `_write_hwmon_file` ist privat, `set_pwm` schreibt den Literal `"1"`
(`fan_backend_linux.py:183`).

### Die Prämisse ist gemessen

Auf BaluNode (2026-09-05), Kanal 1 des nct6798, Dienst gestoppt:

| | `pwm1_enable` | `pwm1` | RPM |
|---|---|---|---|
| BaluHost regelt | 1 | 76 | — |
| nach `echo 5` | 5 | **87** | 508 |
| nach Dienststart | 1 | 87 | — |

`pwm1` wanderte ohne fremden Schreibzugriff von 76 auf 87 — der Chip hat die
Regelung übernommen. **Belegt ist damit: Modus 5 wird auf diesem Chip
angenommen und wirkt.** Nicht belegt ist, dass 5 der Board-Default ist — die
Messung lief nach BaluHost-Betrieb, der BIOS-Ausgangswert wurde nie beobachtet.
Diese Unterscheidung trägt den gesamten Entwurf (siehe Abschnitt 2).

### Warum nur der Shutdown-Pfad

Der erste Entwurf deckte alle drei Punkte des Issues ab; zwei Reviews fanden
acht blockierende Befunde, **sechs davon ausschliesslich an den beiden
Laufzeit-Auslösern**, ebenso beide sicherheitsrelevanten Fälle. Die Befunde
sind in #534 dokumentiert.

## Ziele

- Beim Dienst-Ende die Kontrolle an die Board-Automatik zurückgeben — aber nur
  auf einen Wert, den BaluHost am selben Chip **selbst beobachtet** hat.

## Nicht-Ziele

- **Keine Laufzeit-Rückgabe** (Punkte 1 und 2 des Issues).
- **Kein Treiber-Fallback, kein geratener Modus.** Siehe Abschnitt 2 — die
  frühere Fassung hatte einen; die Review hat ihn auf drei Ebenen zerlegt.
- Keine UI-Anzeige, kein neues Feld in `FanInfo`.
- Keine Änderung an Regelkreis, Kurvenauswertung, Notfallpfad oder Backoff (#533).
- **Keine Rückgabe für GPU-Lüfter.** Für AMD existiert mit `AmdManualState` /
  `disable_amd_manual` (`fan_gpu_manual.py:25-30`, `:65-78`) bereits ein eigener
  Weg, der zusätzlich `power_dpm_force_performance_level` zurücksetzt; zwei
  Mechanismen auf demselben Knoten wären ein Fehler. Ausgeschlossen wird über
  `gpu_vendor is not None` — das deckt auch `nouveau`, das gar keinen
  Rückgabeweg hat, und anders als `FIRMWARE_MANAGED` auch Pre-RDNA3-Karten.

### Die Grenze, die keine Lösung beseitigt

Bei `SIGKILL` gibt es keine Rückgabe. `systemctl stop` und der Deploy-Neustart
senden `SIGTERM`, dort greift der Shutdown-Pfad. Ein hartes Kill oder ein
Stromausfall hinterlässt die Lüfter auf dem letzten Wert — der heutige Zustand,
im Prozess selbst nicht behebbar.

---

## 1. Kein Besitz-Modell — der Zustand steht in sysfs

Die frühere Fassung verfolgte, welche Lüfter BaluHost „besitzt", und gab beim
Beenden genau die zurück. Das trug nicht:

Ein Lüfter im **MANUAL**-Modus wird vom Regelkreis nie geschrieben — `target_pwm`
ist dort gleich `fan.pwm_percent` (`fan_control.py:670`), und geschrieben wird
nur unter `if target_pwm != fan.pwm_percent` (`:740`). Sein einziger Schreibweg
ist `POST /api/fans/pwm` (`routes/fans.py:167`), und der landet bei vier Workern
meist auf einem Sekundär. Ein primary-gebundener Besitz hätte ihn nie erfasst —
er stünde am Dienstende auf `pwm_enable=1`, und niemand regelte. Genau der
Zustand, den diese Arbeit beseitigen soll.

**Stattdessen: beim Beenden den tatsächlich anliegenden Wert lesen.** Der
Zustand steht in sysfs, prozessübergreifend, ohne Buchführung. Ein Lüfter wird
zurückgegeben, wenn

1. für ihn ein **beobachteter** Rückgabewert bekannt ist (Abschnitt 2), **und**
2. `pwm_enable` gerade **nicht** auf diesem Wert steht.

Damit entfallen die Besitzverfolgung, das Primary-Gate als Besitzkriterium und
die gesamte Argumentation darüber, welcher Worker `set_pwm` aufrufen darf.
Geblieben ist ein Gate an genau einer Stelle: **zurückgegeben wird nur im
Primary-Worker**, gelesen als `getattr(lifespan, "IS_PRIMARY_WORKER", False)` —
Modul-Attribut, nie `from ... import` (das Flag wird erst zur Laufzeit gesetzt;
Muster wie `fan_control.py:250`).

### Ein Lesehinweis zu `pwm_enable`

Der Treiber meldet Manual-Modus mit Duty 255 als **`0`**, nicht als `1`:

```c
static enum pwm_enable reg_to_pwm_enable(int pwm, int mode)
{
	if (mode == 0 && pwm == 255)
		return off;
	return mode + 1;
}
```

Ein Lüfter, den BaluHost auf 100 % fährt, liest sich also als `0`. Die Bedingung
„steht nicht auf dem Rückgabewert" deckt das ab, ohne Sonderfall — aber jede
Prüfung von Hand (und die Feldverifikation) muss es wissen.

---

## 2. Nur beobachtete Werte — kein Fallback

### Warum der Treiber-Fallback gestrichen ist

Die frühere Fassung schrieb bei unbekanntem Ursprungswert einen hartkodierten
Modus (`nct6775 → 5`). Die Review hat ihn auf drei Ebenen zerlegt:

- **Der Schlüssel existierte nicht.** Der einzige Treiberwert im Code ist
  `device_driver`, und das ist wörtlich der Inhalt von `hwmonN/name` —
  beim `nct6775`-Treiber der **Chip**name. Auf BaluNode steht dort `nct6798`
  (belegt durch die eigene Messung und durch die Fan-ID
  `nct6798-isa-0290:pwm1`). Ein Lookup auf `nct6775` hätte nie getroffen.
- **Die Begründung war falsch.** `store_pwm_enable()` prüft `data->kind` nur
  für Modus 4 (Smart Fan III, NCT6775F only); Modus 5 ist chip-unabhängig
  erlaubt. Dafür lehnt `check_trip_points()` Modus 5 ab, wenn die
  BIOS-Stützstellen nicht monoton sind — zustandsabhängig, auf demselben Chip,
  und als **EINVAL beim Schreiben**, nicht als abweichender Rücklesewert.
- **Die Messung belegte ihn nicht.** Sie zeigt, dass 5 *angenommen wird und
  wirkt* — nicht, dass 5 der Board-Default ist. Als Rückgabewert taugt sie
  damit nicht.

**Entscheidung: zurückgegeben wird ausschliesslich ein Wert, den BaluHost am
selben Chip selbst gelesen hat.** Das kostet etwas Konkretes (siehe unten) und
ist die einzige Variante, die keine Annahme über fremde Hardware trifft.

### Wann ein Wert beobachtet werden kann

`_scan_pwm_fans` läuft aus `is_available()` heraus beim Backend-Init — **einmal
pro Start und vor dem ersten `set_pwm`**. `get_fans()` rescannt nicht
(`fan_backend_linux.py:109-147`, reine Cache-Lesung). Der Scan ist damit der
einzige Moment, in dem der Board-Wert überhaupt sichtbar sein kann.

Was er sieht, hängt davon ab, wie der Prozess davor endete:

| Vorgeschichte | Scan liest | Bedeutung |
|---|---|---|
| Kaltstart | den BIOS-Wert | **echte Beobachtung** |
| sauberer Shutdown, dann Neustart | den zurückgegebenen Wert | Beobachtung, wertgleich |
| `SIGKILL`, dann Neustart | `1` bzw. `0` | keine Beobachtung |
| laufender Betrieb | `1` bzw. `0` | keine Beobachtung |

### Die Regel

```
gelesener Wert >= 2  ->  beobachteter Automatikmodus:
                         als Rueckgabewert speichern (ueberschreibt einen
                         aelteren Wert -- die juengere Beobachtung gilt)

gelesener Wert 0/1   ->  keine Beobachtung: gespeicherten Wert unveraendert
                         lassen. Ist keiner gespeichert, gibt es fuer diesen
                         Luefter keine Rueckgabe.
```

`0` und `1` sind beide keine Automatik. `1` ist Handsteuerung. `0` heisst laut
generischer hwmon-Konvention „**no fan speed control (i.e. fan at full
speed)**", und der Treiber setzt dabei zusätzlich Duty 255 — also gerade nicht
Board-Automatik.

Dass `1` kein Board-Default sein *kann*, ist eine Entscheidung, keine Tatsache:
BIOS-Profile („Manual", „Full Speed") hinterlassen durchaus `1` mit fester Duty.
Ein solcher Lüfter wird dann eben nie zurückgegeben — richtig, denn dorthin
zurückzuschalten hiesse, die Automatik nicht wiederherzustellen.

### Der Preis, ausdrücklich

**Auf BaluNode passiert nach dem Deploy zunächst nichts.** Alle vier Kanäle
stehen auf `1`, es gibt keine Beobachtung und keinen gespeicherten Wert. Erst
der **nächste Kaltstart** liefert den BIOS-Wert; ab dann ist die Rückgabe
scharf.

Das ist die ehrliche Alternative zu einem geratenen Modus, und der einzige
Preis ist ein Reboot. Wer nicht warten will, kann den Wert einmal von Hand
setzen (`echo 5 > .../pwm1_enable` bei gestopptem Dienst) — der nächste Start
liest ihn als Beobachtung. Das gehört in die Doku, nicht in den Code.

### Persistenz

Eine neue Spalte in `fan_configs`:

```
pwm_enable_restore  Integer, nullable
```

**Keine Herkunftsspalte.** Die frühere Fassung brauchte sie, um einen geratenen
Fallback vom beobachteten Wert zu trennen; ohne Fallback gibt es nichts zu
trennen. (Sie war ohnehin defekt: die Regel „Fallback nicht speichern" liess
den Wert `fallback` nie entstehen.)

Geschrieben wird **im Primary**, in `_load_fan_configs`, **nach** dem
Reconcile-Commit (`fan_control.py:351`) und **nach** dem Primary-Gate (`:426`):

- Für eine **neu angelegte** Zeile wird der Wert am `FanConfig(...)`-Objekt
  mitgesetzt (`fan_control.py:428-468`). Das erzeugt keine zusätzliche Zeile —
  die Zeile entsteht dort ohnehin — und ist die **einzige** Gelegenheit, die
  Erstbeobachtung eines neuen Lüfters festzuhalten. Die frühere Fassung
  verwarf sie mit einer UPDATE-only-Regel, deren Begründung (#532-Kollision)
  sachlich nicht zutraf.
- Für eine **bestehende** Zeile wird das Attribut nur gesetzt, wenn der Wert
  sich unterscheidet.

**`updated_at` darf dabei nicht wandern.** Die Spalte trägt
`onupdate=func.now()` (`models/fans.py:107-112`), und der Identitäts-Abgleich
benutzt sie als Rangkriterium (`fan_reconcile.py:151`, mit einem Snapshot
davor bei `:101-103`). Ein Schreibvorgang bei jedem Start setzte jede Zeile auf
„gerade angefasst" und entwertete das Kriterium. Deshalb: nur bei echter
Änderung schreiben, und beim expliziten `update()` `updated_at` mitführen.

Der Wert wird beim Start in den Speicher geladen, sodass `stop()` keine
Datenbank braucht.

Die Spalte braucht eine Alembic-Migration; **die Elternrevision ist zum
Zeitpunkt der Umsetzung frisch über `alembic heads` zu prüfen** — das Projekt
hatte einen Deploy-Fehler durch mehrere Heads. Kein Backfill: bestehende Zeilen
bleiben `NULL`, bis eine Beobachtung anfällt.

---

## 3. Die Rückgabe

### Neue Backend-Methode

Auf `FanControlBackend` (ABC: `fan_control.py:86-123`):

```python
async def release_to_board(self, fan_id: str, enable_value: int) -> bool: ...
```

Linux-Implementierung:

- schreibt den Wert, **unter Umgehung des Write-Backoffs aus #533**. Läge sie
  hinter dem Backoff, unterbliebe die Rückgabe ausgerechnet bei den Kanälen,
  die zuvor Schreibfehler hatten — den kritischsten;
- **liest zurück** und meldet nur bei anliegendem Wert Erfolg.

Was das Rücklesen leistet und was nicht: Es fängt den **still ignorierten**
Write. Ein vom Treiber **abgelehnter** Modus kommt dagegen als `EINVAL` aus dem
Write selbst zurück — etwa wenn `check_trip_points()` nicht-monotone
BIOS-Stützstellen findet. Beide Fälle sind zu unterscheiden und zu loggen.

Vorsicht bei der Fehlermeldung: `_write_hwmon_file` (`fan_backend_linux.py:548-592`)
gibt nach einem gescheiterten `sudo tee`-Fallback `EACCES` zurück, nicht den
echten Kernel-Fehler — eine `EINVAL`-Ablehnung kann sich so als Rechteproblem
tarnen. Die Meldung sollte das nicht als Tatsache behaupten.

Dev-Implementierung: no-op, `True`.

### `stop()`

Reihenfolge: erst die Monitoring-Task abbrechen (heutiges Verhalten), **dann**
die Rückgabe — umgekehrt schriebe die Schleife dagegen.

Für jeden Lüfter mit gespeichertem Rückgabewert, der kein GPU-Lüfter ist:
aktuellen `pwm_enable`-Wert lesen; weicht er ab, `release_to_board` aufrufen.
Ergebnis pro Lüfter auf INFO, Zusammenfassung am Ende. Eine **fehlgeschlagene**
Rückgabe ist eine WARNING mit Chipname, Zielwert und `errno` — es ist der Fall,
in dem niemand regelt, und er darf nicht im Rauschen untergehen.

Zur Idempotenz: über den realen Weg kann `stop()` nicht zweimal laufen —
`stop_fan_control()` setzt `_fan_control_service = None` (`fan_control.py:1303`),
der Shutdown findet danach `None` vor. Die Rückgabe ist trotzdem
wiederholungssicher zu bauen (direkte `service.stop()`-Aufrufe, Tests): sie
prüft den Ist-Wert und schreibt nur bei Abweichung, ist also von sich aus
idempotent.

### `switch_backend`

`fan_control.py:1065-1090` tauscht das Backend aus, ohne die Monitoring-Task
abzubrechen und ohne zurückzugeben. Ein Wechsel Linux → dev lässt jeden Kanal
auf `pwm_enable=1` zurück, während niemand mehr regelt — derselbe Zustand, den
diese Arbeit beseitigt, über einen Admin-Endpunkt.

Dort gilt dieselbe Reihenfolge wie in `stop()`: **Task abbrechen → Rückgabe →
tauschen.** Wichtig auch der Scan-Zeitpunkt: bei `use_linux=True` baut die
Methode zuerst ein neues Backend und ruft `is_available()` → `_scan_pwm_fans()`
(`:1074-1075`), danach `_load_fan_configs()` (`:1078`). Die Rückgabe muss davor
liegen, damit der neue Scan den zurückgegebenen Wert sieht — das ist dann eine
gültige Beobachtung, wertgleich mit dem gespeicherten.

---

## 4. Tests und Verifikation

### Die Regel (rein, ohne sysfs und DB)

| gelesen | gespeichert | Ergebnis |
|---|---|---|
| `5` | — | speichern: `5` |
| `2` | `5` | speichern: `2` (jüngere Beobachtung gilt) |
| `1` | `5` | unverändert `5` |
| `0` | `5` | unverändert `5` |
| `1` | — | kein Rückgabewert — keine Rückgabe |
| `0` | — | kein Rückgabewert — keine Rückgabe |

Zeile 5 und 6 sind der Kern des Entwurfs: ohne Beobachtung passiert nichts.

### Rückgabe

- Gespeicherter Wert `5`, `pwm_enable` steht auf `1` → Datei enthält danach `5`.
- Gespeicherter Wert `5`, `pwm_enable` steht bereits auf `5` → **kein Write**.
- Kein gespeicherter Wert → kein Write, egal was anliegt.
- `pwm_enable` liest sich als `0` (Manual bei 100 %) → wird als Abweichung
  behandelt, Rückgabe erfolgt.
- Write geht durch, Rücklesen liefert einen anderen Wert → `False`, WARNING.
- Write scheitert mit `EINVAL` → `False`, WARNING, und die Meldung behauptet
  **nicht** „keine Rechte".
- GPU-Lüfter (`gpu_vendor` gesetzt) → nie zurückgegeben.
- Zweiter `stop()`-Aufruf schreibt nichts (Ist-Wert stimmt bereits).

Aufbau über echte `tmp_path`-sysfs-Bäume, platform-förmig und doppelpunktfrei
(NTFS verbietet Doppelpunkte in Verzeichnisnamen — Lehre aus #532). Muster:
`test_fan_pwm_backoff.py:28-51`, `test_fan_scan_stable_ids.py`.

### Persistenz

- **Neuer Lüfter:** Scan liest `5`, die Zeile wird angelegt, `pwm_enable_restore`
  ist `5`. Das ist der Test gegen die verworfene UPDATE-only-Regel.
- **Bestehende Zeile, unveränderter Wert:** kein Schreibvorgang, `updated_at`
  bleibt gleich. Der Test dazu vergleicht `updated_at` vor und nach dem Lauf —
  ohne ihn bliebe die Entwertung des Reconcile-Rangkriteriums unbemerkt.
- **Bestehende Zeile, neue Beobachtung:** Wert wird ersetzt.
- Läuft nur im Primary.

### Der Round-Trip

Ein Test über die Naht, den keine Tabellenzeile ersetzt: Scan liest `5` →
Persistenz → `stop()` schreibt `5` → **neuer Scan auf demselben Baum** →
gespeicherter Wert weiterhin `5`, keine Zeile doppelt, `updated_at` unverändert.

### Gates

`pytest -k "fan or power"`, `ruff check`, `eslint .`, `npm run build`,
`vitest run`. Die Messlatte ist unmittelbar vor der Umsetzung einmal zu messen
und mit Datum zu notieren — eine Zahl aus einem früheren Lauf ist keine
Messlatte. Volle Backend-Suite in der CI.

### Feldverifikation

1. **Nach dem Deploy:**
   `SELECT fan_id, pwm_enable_restore FROM fan_configs WHERE is_active`.
   Erwartung: **`NULL`** für alle. Es gab keinen Kaltstart, also keine
   Beobachtung. Steht dort ein Wert, ist die Regel verletzt.
2. **Nach einem Reboot:** dieselbe Abfrage. Erwartung: der BIOS-Wert, für die
   vier nct6798-Kanäle vermutlich `5`. **Das ist die erste echte Messung des
   Board-Defaults auf dieser Maschine** — bisher wurde er nie beobachtet.
3. **Dann der Kern:** `systemctl stop baluhost-backend`, danach
   `cat /sys/class/hwmon/hwmon3/pwm{1,2,3,7}_enable`. Erwartung: der in Schritt 2
   gelesene Wert. Heute steht dort `1` — das ist die Lücke.
   Hinweis: ein Lüfter, der bei 100 % lief, zeigt vorher `0`, nicht `1`.
4. **Gegenprobe:** Dienst wieder starten, eine Minute warten, `pwm_enable`
   erneut lesen. Erwartung `1` — BaluHost hat die Kontrolle zurückgenommen.

---

## Risiken

- **Auf einer laufenden Installation tut die Funktion zunächst nichts.** Sie
  armiert sich beim nächsten Kaltstart. Bewusst gewählt gegenüber einem
  geratenen Modus.
- **Die Rückgabe kann scheitern** — abgelehnter Modus (`EINVAL`, etwa bei
  nicht-monotonen Trip Points) oder still ignorierter Write. Beides wird
  erkannt und gemeldet; der Zustand ist dann derselbe wie heute.
- **`SIGKILL` bleibt ungedeckt.**
- **Zwei Regelschleifen über `/api/admin/services/fan_control/restart`** sind
  ein vorbestehender, unabhängiger Fehler — als #555 festgehalten, nicht Teil
  dieser Arbeit.

## Quellen

- [Kernel driver NCT6775](https://docs.kernel.org/hwmon/nct6775.html)
- [`drivers/hwmon/nct6775-core.c`](https://raw.githubusercontent.com/torvalds/linux/master/drivers/hwmon/nct6775-core.c)
  — `store_pwm_enable`, `check_trip_points`, `reg_to_pwm_enable`
- [`Documentation/hwmon/sysfs-interface.rst`](https://docs.kernel.org/hwmon/sysfs-interface.html)
