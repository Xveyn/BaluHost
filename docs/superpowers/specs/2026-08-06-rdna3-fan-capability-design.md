# RDNA3-Lüfter: PWM-Fähigkeit erkennen statt ins Leere schreiben

**Datum:** 2026-08-06 (überarbeitet 2026-08-07 nach kritischem Review + Hardware-Verifikation)
**Status:** Design freigegeben, Umsetzung ausstehend
**Betrifft:** Issue #480; Kurven-Bug #517 (im selben PR); Folge-Feature #516

---

## Problem

Auf RDNA3-GPUs (gemessen: RX 7900 XT, `1002:744C`, Kernel 6.12.74, BaluNode)
implementiert der amdgpu-Treiber keine manuelle PWM-Steuerung. BaluHost versucht
sie trotzdem und gibt bei Misserfolg eine Empfehlung, die dort nicht greift.

Messungen vom 2026-08-06, als `root` auf
`/sys/class/drm/card0/device/hwmon/hwmon2/`:

| Test | Ergebnis |
|---|---|
| `cat /sys/module/amdgpu/parameters/ppfeaturemask` | `0xffffffff` — Overdrive ist aktiv |
| `echo 1 > pwm1_enable` (lactd läuft) | `rc=0`, Readback bleibt `2` |
| `echo 1 > pwm1_enable` (lactd gestoppt) | `rc=0`, Readback bleibt `2` |
| `echo 128 > pwm1` (lactd gestoppt) | `EINVAL`, `rc=1` |

Daraus folgt:

1. **Der Boot-Parameter ist nicht die Ursache.** `amdgpu.ppfeaturemask=0xffffffff`
   ist gesetzt und aktiv; PWM scheitert trotzdem. Die heutige Meldung („For AMD
   GPUs: enable manual mode in the UI", `fan_backend_linux.py:147-150`) und der
   ursprüngliche Fix-Vorschlag aus #480 wären beide falsche Selbsthilfe.
2. **Ein Fremd-Controller ist nicht die Ursache.** `lactd` läuft auf BaluNode,
   aber mit gestopptem Dienst ist das Verhalten bitgenau identisch.
3. **`pwm{n}_enable` meldet Erfolg, ohne zu wirken** (`rc=0`, Wert bleibt `2`).
   Nur der `pwm{n}`-Write scheitert sichtbar.

Der einzige unterstützte Steuerpfad ist die firmware-verwaltete Kurve unter
`<device>/gpu_od/fan_ctrl/` (`fan_curve`, `fan_minimum_pwm`,
`fan_target_temperature`, `acoustic_limit_rpm_threshold`,
`acoustic_target_rpm_threshold`).

### Folgeschaden im laufenden Betrieb

`fan_control.py:540-541` ruft `set_pwm` in jedem Monitoring-Tick, sobald der
Zielwert vom gelesenen abweicht. Auf BaluNode liest `pwm1` konstant `0` — der
Loop schreibt dauerhaft, scheitert dauerhaft und schreibt bei jedem Fehlschlag
ein `logger.error` (`fan_backend_linux.py:151`). Zusätzlich protokolliert
`fan_sample` einen Wunsch-PWM, der die Hardware nie erreicht hat.

## Nicht-Ziele

- **Fehlende Schreibrechte reparieren.** `pwm1`, `pwm1_enable` und
  `gpu_od/fan_ctrl/*` sind `root:root 0644`; die udev-Regel
  (`deploy/scripts/install-amd-gpu-permissions.sh:44-45`) erfasst nur
  `power_dpm_force_performance_level` und `pp_power_profile_mode`, und in keinem
  sudoers-Template steht ein `tee`-Eintrag. Kein Anfassen von `deploy/`.

  Nicht zu verwechseln mit `PwmControl.NO_PERMISSION`: Dieses Design **erkennt
  und benennt** den Rechtezustand, es **behebt** ihn nicht.
- **Die Firmware-Kurve tatsächlich steuern.** Eigenes Feature, eigenes Design —
  Issue #516.

## Lösung

Ein Feld `pwm_control` beschreibt pro Lüfter, ob und warum PWM-Schreiben möglich
ist. Loop, API und UI lesen dasselbe Feld.

```python
class PwmControl(str, Enum):
    SUPPORTED        = "supported"          # Default für alle Lüfter
    FIRMWARE_MANAGED = "firmware_managed"   # RDNA3+: Kurve liegt in der Firmware
    NO_PERMISSION    = "no_permission"      # EACCES beim Schreiben beobachtet
```

Das Feld wird an drei leicht zu verwechselnden Stellen getragen:

| Ort | Typ | Wer liest es |
|---|---|---|
| `_fan_cache[fan_id]["pwm_control"]` | `dict` in `fan_backend_linux.py` | `set_pwm()`, Route-Guards |
| `FanData.pwm_control` | Dataclass, `fan_control.py:37-57` | der Regel-Loop (`get_fans()` liefert `FanData`, nicht `FanInfo`) |
| `FanInfo.pwm_control` | Pydantic-Schema, `schemas/fans.py:72` | die API-Antwort und damit das Frontend |

`get_status()` baut die Lüfterliste an **zwei** Stellen auf (`fan_control.py:707`
und `:755`); beide brauchen das Feld, sonst verschwindet es je nach Codepfad.

### Erkennung — an der Hardware verifiziert

```python
(hwmon_dir / "device" / "gpu_od" / "fan_ctrl" / "fan_curve").exists()
```

Jede hwmon-Directory hat einen `device`-Symlink auf ihr PCI-Gerät. Auf BaluNode
verifiziert:

```
$ ls -d /sys/class/hwmon/hwmon2/device/gpu_od/fan_ctrl
/sys/class/hwmon/hwmon2/device/gpu_od/fan_ctrl
```

**Verworfener Ansatz — nicht wieder einführen.** Der erste Entwurf wollte
`_device_from_hwmon()` aus `fan_gpu_manual.py:71-82` wiederverwenden. Diese
Funktion macht `hwmon_dir.resolve()` und sucht dann eine Pfadkomponente namens
`device`. Auf echter Hardware gibt es die nicht:

```
$ readlink -f /sys/class/hwmon/hwmon2
/sys/devices/pci0000:00/0000:00:01.1/0000:01:00.0/0000:02:00.0/0000:03:00.0/hwmon/hwmon2
```

`_device_from_hwmon` liefert dort `None`. Die Erkennung hätte konstant
`SUPPORTED` gemeldet und der gesamte Fix wäre wirkungslos in Produktion
gegangen — unbemerkt, weil `tmp_path`-Tests `device` als echtes Verzeichnis
anlegen.

**Folgefehler gleicher Ursache, hier mitbehoben:** `enable_amd_manual()` und
`disable_amd_manual()` nutzen denselben Resolver. Der „Manual Mode"-Toggle
scheitert auf echter Hardware also seit jeher mit
`RuntimeError: Could not locate amdgpu device` → HTTP 500. `_device_from_hwmon`
wird auf den `device`-Symlink umgestellt, mit Rückfall auf den bisherigen
Aufwärtslauf, damit vorhandene Tests mit synthetischen Bäumen grün bleiben.

Aufgerufen wird die Erkennung in `_scan_pwm_fans()`, nur für
`gpu_vendor == "amd"`. Kosten: ein `stat` pro AMD-GPU je Scan.

### Zustandstabelle

| Lüfter | `device/gpu_od/fan_ctrl/fan_curve` | Beobachteter Fehler | `pwm_control` |
|---|---|---|---|
| CPU/Board-Lüfter | — (kein GPU-Lüfter) | keiner | `supported` |
| AMD pre-RDNA3 | fehlt | keiner | `supported` |
| AMD pre-RDNA3, Rechte fehlen | fehlt | `EACCES` | `no_permission` |
| AMD RDNA3+ | vorhanden | — (wird nicht versucht) | `firmware_managed` |
| nouveau / andere | nicht geprüft | keiner | `supported` |

### Lebenszyklus von `NO_PERMISSION`

`_scan_pwm_fans()` hat genau einen Aufrufer, `is_available()`, und der läuft nur
bei `_initialize_backend()` (Start) und `switch_backend(use_linux=True)`. **Es
gibt keinen periodischen Scan.** Daraus folgt:

- Die Erkennung setzt nur `SUPPORTED` oder `FIRMWARE_MANAGED`. Ein
  `os.access()`-Test würde lügen, solange der `sudo tee`-Fallback greifen könnte.
- Der Schreibpfad stuft bei beobachtetem `EACCES` auf `NO_PERMISSION` **herab**
  und bei einem später erfolgreichen Write wieder auf `SUPPORTED` **hoch**.
  Ohne diesen Rückweg bliebe der Zustand bis zum Service-Neustart stehen, auch
  wenn die Rechte zur Laufzeit korrigiert werden.
- `FIRMWARE_MANAGED` wird nie herabgestuft — es ist eine Hardware-Eigenschaft.

**Bekannte Einschränkung (Mehr-Worker):** Produktion läuft mit vier
Uvicorn-Workern, jeder mit eigenem `_fan_cache`. `FIRMWARE_MANAGED` ist
scan-abgeleitet und daher in allen Workern gleich. `NO_PERMISSION` und
`last_write_error` entstehen nur im schreibenden Worker und flackern deshalb
über die round-robin bediente Status-Route. Für `last_write_error` gilt das
heute schon. Deshalb hängt **keine UI-Sperre an `NO_PERMISSION`** — der Wert
informiert nur die Meldung.

### Verhältnis zu `permission_status`

`permission_status` (`fan_control.py:772-776`) ist global, wird nur am ersten
Lüfter des Caches geprüft und ist monoton. Es beantwortet eine andere Frage als
`pwm_control`. Festlegung, damit keine zweite Wahrheit entsteht:

- Die UI sperrt Schreib-Bedienelemente bei `isReadOnly` (global) **oder**
  `pwm_control === 'firmware_managed'` (pro Lüfter).
- `no_permission` sperrt nichts, sondern liefert nur den Meldungstext.

## Regel-Loop

In `_monitor_and_control_fans` nach dem Clamp auf `min/max`
(`fan_control.py:538`):

```python
if fan.pwm_control is PwmControl.FIRMWARE_MANAGED:
    target_pwm = fan.pwm_percent   # Firmware besitzt die Kurve
```

Die bestehende Bedingung `if target_pwm != fan.pwm_percent` greift dadurch von
selbst nicht mehr. `fan_sample` protokolliert den tatsächlichen statt eines nie
angekommenen Wunschwerts, und das Error-Logging pro Tick verschwindet.

**Emergency-Sonderfall.** Der Loop schreibt bei Übertemperatur
`config.mode = "emergency"` in die DB (`:544-546`), und **nichts setzt das je
zurück** — in `EMERGENCY` greift der `AUTO/SCHEDULED`-Zweig nicht mehr, und
`POST /api/fans/mode` akzeptiert `emergency` nicht als Eingabe. Für einen
firmware-verwalteten Lüfter wäre das ein Dauerzustand ohne jeden Nutzen: Die
Regelung kann ohnehin nichts ausrichten. Deshalb wird für
`FIRMWARE_MANAGED` die **Mode-Persistierung übersprungen**, die
Temperatur-Benachrichtigung aber ausgelöst. Die Warnung bleibt, der
Karteileichen-Zustand entsteht nicht.

## Schreibpfad und Meldungen

In `fan_backend_linux.py`:

1. `set_pwm()` bricht bei `FIRMWARE_MANAGED` sofort ab, ohne sysfs anzufassen.
2. `_write_hwmon_file()` gibt statt `bool` künftig `(ok, errno)` zurück. Es hat
   genau zwei Aufrufstellen, beide in `set_pwm` (`:130`, `:135`) — die
   Signaturänderung bleibt lokal. Der bestehende Catch-all für Nicht-`OSError`
   bleibt erhalten, damit nichts Neues in den Monitoring-Loop propagiert.
3. Bei `EACCES` → `NO_PERMISSION`, bei erfolgreichem Write zurück auf
   `SUPPORTED`.

Der `sudo tee`-Fallback bekommt `-n`. Ohne das läuft jeder fehlgeschlagene Write
in den Fünf-Sekunden-Timeout — bei einem Fehlschlag pro Tick ist das kein
Detail. `_check_write_permission` nutzt `-n` bereits; die Schreibstelle war die
Ausnahme.

Meldungstexte bleiben englisch wie alle bestehenden:

| Zustand | Aussage |
|---|---|
| `firmware_managed` | Firmware-verwaltete Kurve auf RDNA3+; Live-PWM vom Treiber nicht unterstützt — **mit dem ausdrücklichen Zusatz, dass `amdgpu.ppfeaturemask` daran nichts ändert** |
| `no_permission` | Kein Schreibrecht auf den konkreten Pfad (`EACCES`), unter Nennung des Dienst-Users |
| `EINVAL` sonst | Kernel lehnt ab, mit `driver=` und `pwm_enable=` wie bisher |

Der `ppfeaturemask`-Zusatz ist der Grund, aus dem #480 ursprünglich falsch
diagnostiziert wurde, und verhindert, dass jemand denselben Weg noch einmal geht.

## API

Zwei Routen brauchen einen Guard, nicht eine:

- `POST /api/fans/{fan_id}/gpu-manual-mode` — 400 bei `FIRMWARE_MANAGED`,
  **aber nur für `enable=true`**. Ein Guard vor der Fallunterscheidung würde
  auch das Abschalten blockieren; wer den Toggle je benutzt hat, käme dann nie
  wieder aus `performance_level=manual` heraus.
- `POST /api/fans/pwm` — heute liefert die Route bei `success=False` pauschal
  „Failed to set PWM (fan not in manual mode or not found)"
  (`routes/fans.py:158-162`). Der frisch gesetzte `last_write_error` erreicht
  die Antwort nie. Ohne eigenen Guard bliebe genau die Sorte irreführender
  Auskunft bestehen, die dieses Design abschaffen soll.

Zusätzlich wird `enable_amd_manual()` gegen halb angewendete Zustände
abgesichert: Scheitert der `pwm_enable`-Write, rollt ein `try/except` den
`performance_level`-Write zurück.

## Frontend

- `api/fan-control.ts` — `pwm_control` im `FanInfo`-Typ.
- `FanCard.tsx` — Badge „Firmware"; der **PWM-Slider** wird gesperrt.
- `FanDetails.tsx` — statt `GpuManualModeToggle` ein Erklärpanel; Kurveneditor,
  `CurveTypeSelector`, `AdvancedFanSettings`, Profile und Zeitpläne werden über
  ein per-Lüfter-Read-only gesperrt.
- `CurveEditorSync.tsx` — firmware-verwaltete Lüfter aus der Auswahlliste
  filtern. Ein Lüfter, der sich per `sync` an die GPU koppelt, würde sonst
  dauerhaft auf `min_pwm_percent` festgenagelt, weil `pwm1` konstant `0` liest.
- i18n `de` und `en`, Namespace `system`, unter `fanControl.gpu.firmware.*`.

**Die Modus-Buttons (AUTO / SCHEDULED / MANUAL) bleiben bedienbar.** Der Modus
ist reine DB-Konfiguration und kein Hardware-Write. Sie zu sperren würde einen
Lüfter, der aus früherer Zeit in `MANUAL` oder `EMERGENCY` feststeckt,
unrettbar machen — der AUTO-Button ist der einzige Ausweg aus `EMERGENCY`.

Die Karte bleibt sichtbar: Lesen funktioniert auf RDNA3 einwandfrei, Drehzahl
und Temperatur sind weiterhin nützlich.

## Dev-Mode

`fan_backend_dev.py` meldet für alle simulierten Lüfter `SUPPORTED` und bekommt
zusätzlich einen simulierten firmware-verwalteten GPU-Lüfter, damit der neue
UI-Pfad auf der Windows-Entwicklungsmaschine sichtbar ist.

`backend/tests/services/test_fan_control.py:45`, `:73` und `:372` prüfen auf
genau vier simulierte Lüfter und müssen mitgezogen werden.

Der Route-Guard ist im Dev-Mode **nicht** erreichbar: `routes/fans.py:1001`
prüft `hasattr(backend, "_fan_cache")`, und der Dev-Backend hat `_fans`. Die
Sichtprüfung im Dev-Mode zeigt Badge, Sperren und Erklärpanel — den 400er
bestätigt nur der Test.

## Mitbehoben: Kurven-Bug #517

Beim Nachrechnen einer Testerwartung aufgefallen und verifiziert:
`fan_control.py:533-536` übergibt `_calculate_pwm_with_hysteresis` eine **leere**
Kurvenliste. Die Funktion verwirft das von `evaluate_curve` berechnete Ziel und
holt sich über `_calculate_pwm_from_curve` (`:557-560`) den Hardcode-Wert `50`.
Für jeden Lüfter mit `curve_type="graph"` — dem Default — ist die konfigurierte
Kurve damit wirkungslos.

Fix: `_calculate_pwm_with_hysteresis` **dämpft** das bereits berechnete Ziel,
statt es neu zu berechnen. Parameter `curve_points` und der Aufruf von
`_calculate_pwm_from_curve` entfallen; letzteres wird tot und fällt weg (seine
Interpolation dupliziert ohnehin `fan_curve_eval.py`). Beide Helfer haben je
genau einen Aufrufer und werden von keinem Test direkt gerufen.

Auf Wunsch im selben PR wie #480, obwohl inhaltlich unabhängig.

## Tests

| Datei | Deckt ab |
|---|---|
| `test_fan_pwm_control_probe.py` (neu) | Erkennung über den `device`-Symlink, inkl. Nicht-AMD und fehlendem Symlink |
| `test_fan_einval_diagnostic.py` | die drei Meldungsvarianten; `EACCES`-Herabstufung und Rückweg |
| `test_fan_firmware_managed_loop.py` (neu) | Loop schreibt nicht, Sample trägt den echten Wert, kein `emergency`-Persist |
| `test_fan_curve_hysteresis.py` (neu) | #517: Kurve wirkt, statt 50 zurückzugeben |
| `test_fan_gpu_manual_mode.py` | Rollback; Guard nur bei `enable=true`; `device`-Symlink-Auflösung |
| `tests/services/test_fan_control.py` | Lüfterzahl im Dev-Backend nachziehen |
| `client/src/__tests__/components/fan-control/FanCard.test.tsx` (neu) | Badge, gesperrter Slider, **bedienbare** Modus-Buttons |

Vor dem PR lokal: die betroffenen pytest-Dateien gezielt, dazu `npx vitest run`,
`eslint .` und `npm run build`. Die vollständige Backend-Suite läuft auf Windows
nicht durch und bleibt CI überlassen.

## Risiken

- **Erkennung an einer Karte gemessen.** Die Regel „`gpu_od/fan_ctrl/fan_curve`
  vorhanden ⇒ PWM unmöglich" stammt von einer RX 7900 XT. Sie entspricht dem
  SMU13-Verhalten, ist aber nicht über die gesamte RDNA3-Reihe verifiziert.
  Fällt eine Karte auf, die beides kann, verliert sie die PWM-Steuerung —
  sichtbar am Badge und über den Meldungstext zurückverfolgbar.

  **Eine Fehlerkennung hat keinen Selbsthilfe-Weg.** Die Modus-Buttons retten
  nur das DB-Feld `mode`. Bei einer fälschlich als `FIRMWARE_MANAGED`
  erkannten Karte sind gleichzeitig zu: der Slider, Kurve/Zeitplan/Advanced,
  `POST /api/fans/pwm` (400), `gpu-manual-mode enable` (400), und der Loop
  schreibt nie. Es gibt keinen Config-Schalter und kein UI-Override. Erholung
  hieße Dienst stoppen und sysfs von Hand schreiben. Ein Konfigurationsschalter
  zum Abschalten der Erkennung ist als Folgearbeit vorgesehen (eigenes Issue).

  **Zweiter Ordnungseffekt.** Stand ein solcher Lüfter zuvor auf
  `pwm_enable=1`, hört der Loop einfach auf zu schreiben, und **nichts stellt
  `pwm_enable=2` wieder her** — der Lüfter bleibt beim letzten PWM-Wert stehen,
  während die Auto-Regelung des Treibers weiterhin deaktiviert ist. Auf echter
  RDNA3-Hardware ist das gegenstandslos (der Treiber ignoriert `pwm_enable=1`
  ohnehin, siehe Messtabelle oben); bei einer Fehlerkennung auf einer Karte,
  die PWM tatsächlich unterstützt, ist das ein thermisches Risiko.
- **Nicht gemessen:** ob `gpu_od/` ohne `amdgpu.ppfeaturemask=0xffffffff`
  verschwindet. Die Implementierung darf deshalb **nicht** aus einem fehlenden
  `gpu_od/` auf „Overdrive fehlt" schließen und daraus eine Handlungsempfehlung
  ableiten — das wäre exakt der Fehler, den dieses Design behebt.
- **Cache-Aktualität.** `pwm_control` wird beim Scan bestimmt; ein
  Treiber-Reload zur Laufzeit wird erst beim nächsten Start berücksichtigt.
