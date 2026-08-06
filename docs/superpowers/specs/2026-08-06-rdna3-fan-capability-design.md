# RDNA3-Lüfter: PWM-Fähigkeit erkennen statt ins Leere schreiben

**Datum:** 2026-08-06
**Status:** Design freigegeben, Umsetzung ausstehend
**Betrifft:** Issue #480; Fan-Overhaul (Plan 2026-05-24)

---

## Problem

Auf RDNA3-GPUs (gemessen: RX 7900 XT, `1002:744C`, Kernel 6.12.74, BaluNode)
implementiert der amdgpu-Treiber keine manuelle PWM-Steuerung. BaluHost versucht
sie trotzdem und gibt bei Misserfolg eine Empfehlung, die dort nicht greift.

Messungen vom 2026-08-06, alle als `root` auf
`/sys/class/drm/card0/device/hwmon/hwmon2/`:

| Test | Ergebnis |
|---|---|
| `cat /sys/module/amdgpu/parameters/ppfeaturemask` | `0xffffffff` — Overdrive ist aktiv |
| `echo 1 > pwm1_enable` (lactd läuft) | `rc=0`, Readback bleibt `2` |
| `echo 1 > pwm1_enable` (lactd gestoppt) | `rc=0`, Readback bleibt `2` |
| `echo 128 > pwm1` (lactd gestoppt) | `EINVAL`, `rc=1` |

Daraus folgt dreierlei:

1. **Der Boot-Parameter ist nicht die Ursache.** `amdgpu.ppfeaturemask=0xffffffff`
   steht in `/proc/cmdline` und ist aktiv; PWM scheitert trotzdem. Die heutige
   Meldung („For AMD GPUs: enable manual mode in the UI",
   `fan_backend_linux.py:147-150`) und der ursprüngliche Fix-Vorschlag aus #480
   („setz ppfeaturemask + Reboot") wären beide falsche Selbsthilfe.
2. **Ein Fremd-Controller ist nicht die Ursache.** `lactd` läuft auf BaluNode,
   aber mit gestopptem Dienst ist das Verhalten bitgenau identisch.
3. **`pwm{n}_enable` meldet Erfolg, ohne zu wirken.** Der Write gibt `rc=0`
   zurück, der Wert bleibt `2`. Nur der `pwm{n}`-Write scheitert sichtbar.

Der einzige unterstützte Steuerpfad ist die firmware-verwaltete Kurve unter
`<device>/gpu_od/fan_ctrl/` (`fan_curve`, `fan_minimum_pwm`,
`fan_target_temperature`, `acoustic_limit_rpm_threshold`,
`acoustic_target_rpm_threshold`).

### Folgeschaden im laufenden Betrieb

`fan_control.py:540-541` ruft `set_pwm` in jedem Monitoring-Tick, sobald der
Zielwert vom gelesenen abweicht. Auf BaluNode liest `pwm1` konstant `0`, die
Kurve fordert mindestens `min_pwm_percent` — der Loop schreibt also dauerhaft,
scheitert dauerhaft und schreibt bei jedem Fehlschlag ein `logger.error`
(`fan_backend_linux.py:151`). Zusätzlich protokolliert `fan_sample` einen
Wunsch-PWM, der die Hardware nie erreicht hat.

## Nicht-Ziele

Bewusst ausgeklammert, jeweils mit Begründung:

- **Fehlende Schreibrechte reparieren.** `pwm1`, `pwm1_enable` und
  `gpu_od/fan_ctrl/*` sind `root:root 0644`; die udev-Regel
  (`deploy/scripts/install-amd-gpu-permissions.sh:44-45`) erfasst nur
  `power_dpm_force_performance_level` und `pp_power_profile_mode`, und in keinem
  sudoers-Template steht ein `tee`-Eintrag. Auf der einzigen vorhandenen
  AMD-Karte ist PWM ohnehin tot, der Fix brächte dort also nichts messbares. Er
  fasst `deploy/` an (CODEOWNERS) und braucht einen manuellen Skript-Re-Run auf
  dem Server. Bleibt als Abschnitt in #480 dokumentiert.

  Nicht zu verwechseln mit `PwmControl.NO_PERMISSION` weiter unten: Dieses
  Design **erkennt und benennt** den Rechtezustand, es **behebt** ihn nicht. Der
  Unterschied ist der ganze Punkt — die heutige Meldung behauptet „rejected by
  kernel", obwohl der Kernel in diesem Fall nie gefragt wurde.
- **Die Firmware-Kurve tatsächlich steuern.** Eigenes Feature mit eigenem Design
  (Schreibformat und Commit-Semantik von `fan_curve`, Zero-RPM-Verhalten,
  Wertebereiche, Rücknahme beim Deaktivieren). Bekommt ein eigenes Issue, das
  auf das hier eingeführte `pwm_control`-Feld aufsetzt.

## Lösung

Ein neues Feld `pwm_control` beschreibt pro Lüfter, ob und warum PWM-Schreiben
möglich ist. Loop, API und UI lesen dasselbe Feld.

```python
class PwmControl(str, Enum):
    SUPPORTED        = "supported"          # Default für alle Lüfter
    FIRMWARE_MANAGED = "firmware_managed"   # RDNA3+: Kurve liegt in der Firmware
    NO_PERMISSION    = "no_permission"      # EACCES beim Schreiben beobachtet
```

Das Feld muss an **drei** Stellen getragen werden, die leicht zu verwechseln sind:

| Ort | Typ | Wer liest es |
|---|---|---|
| `_fan_cache[fan_id]["pwm_control"]` | `dict` in `fan_backend_linux.py` | `set_pwm()`, Route-Guard |
| `FanData.pwm_control` | Dataclass, `fan_control.py:37-57` | der Regel-Loop (`get_fans()` liefert `FanData`, nicht `FanInfo`) |
| `FanInfo.pwm_control` | Pydantic-Schema, `schemas/fans.py:72` | die API-Antwort und damit das Frontend |

`get_fans()` in `fan_backend_linux.py:93-110` füllt `FanData` bereits aus dem
Cache und wird um das Feld ergänzt; die Übersetzung `FanData` → `FanInfo` folgt
dem Muster der bestehenden Felder `is_gpu_fan` / `last_write_error`. Der
Dev-Backend baut `FanData` eigenständig und braucht denselben Default.

### Erkennung

Neue Funktion in `backend/app/services/power/fan_gpu_manual.py`:

```python
def probe_amd_pwm_control(hwmon_dir: Path, drm_root: Optional[Path] = None) -> PwmControl
```

Sie nutzt das dort bereits vorhandene `_device_from_hwmon()`, das von der
hwmon-Directory zum PCI-Device hochläuft — genau dort liegt `gpu_od/`.
Existiert `<device>/gpu_od/fan_ctrl/fan_curve`, ist das Ergebnis
`FIRMWARE_MANAGED`, sonst `SUPPORTED`.

Aufgerufen in `_scan_pwm_fans()` (`fan_backend_linux.py:301-348`), ausschließlich
für `gpu_vendor == "amd"`. Das Ergebnis wird als `pwm_control` im
`_fan_cache`-Eintrag abgelegt, neben `is_gpu_fan` und `gpu_vendor`. Kosten: ein
Dateisystem-Check pro AMD-GPU je Scan.

**Festlegung:** `NO_PERMISSION` wird bei der Erkennung *nicht* vergeben. Ein
`os.access()`-Test würde ein falsches Urteil fällen, solange der
`sudo tee`-Fallback theoretisch greifen könnte. Stattdessen stuft der
Schreibpfad den Wert herab, sobald er tatsächlich `EACCES` beobachtet. Das Feld
mischt damit statische Hardware-Eigenschaft und beobachteten Laufzeitzustand.
Das ist gewollt: UI und Fehlermeldung stellen genau diese kombinierte Frage
(„darf ich schreiben, und wenn nein, warum nicht?").

### Zustandstabelle

| Lüfter | `gpu_od/fan_ctrl/fan_curve` | Beobachteter Fehler | `pwm_control` |
|---|---|---|---|
| CPU/Board-Lüfter | — (kein GPU-Lüfter) | keiner | `supported` |
| AMD pre-RDNA3 | fehlt | keiner | `supported` |
| AMD pre-RDNA3, Rechte fehlen | fehlt | `EACCES` | `no_permission` |
| AMD RDNA3+ | vorhanden | — (wird nicht mehr versucht) | `firmware_managed` |
| nouveau / andere | nicht geprüft | keiner | `supported` |

## Regel-Loop

In `_monitor_and_control_fans` direkt nach dem Clamp auf `min/max`
(`fan_control.py:538`):

```python
if fan.pwm_control is PwmControl.FIRMWARE_MANAGED:
    target_pwm = fan.pwm_percent   # Firmware besitzt die Kurve
```

Die bestehende Bedingung `if target_pwm != fan.pwm_percent` greift dadurch von
selbst nicht mehr — kein zusätzlicher Zweig an der Schreibstelle. Zwei
gewünschte Nebeneffekte: `fan_sample` protokolliert den tatsächlichen statt
eines nie angekommenen Wunschwerts, und das Error-Logging pro Tick verschwindet.

Emergency-Benachrichtigungen bei GPU-Übertemperatur bleiben unverändert
erhalten. Sie sind auch ohne Steuerhoheit wertvoll, und der Code-Pfad dorthin
liegt vor der Änderung.

## Schreibpfad und Meldungen

In `fan_backend_linux.py`:

1. `set_pwm()` bricht bei `FIRMWARE_MANAGED` sofort ab, ohne sysfs anzufassen,
   und setzt `last_write_error` auf den Firmware-Text. Das deckt auch den
   direkten API-Weg über `POST /api/fans/pwm` ab, der nicht durch den Loop geht.
2. `_write_hwmon_file()` gibt statt `bool` künftig `(ok, errno)` zurück. Es hat
   genau zwei Aufrufstellen, beide in `set_pwm` (Zeilen 130 und 135) — die
   Signaturänderung ist damit vollständig lokal. Heute verschluckt ein
   gemeinsames `except` den Unterschied zwischen `EACCES` und `EINVAL`.
3. Bei `EACCES` wird `pwm_control` im Cache auf `NO_PERMISSION` herabgestuft.

Die Meldungstexte bleiben englisch, wie alle bestehenden `last_write_error`-Texte:

| Zustand | Aussage |
|---|---|
| `firmware_managed` | Firmware-verwaltete Kurve auf RDNA3+; Live-PWM wird vom Treiber nicht unterstützt — **ausdrücklich mit dem Zusatz, dass `amdgpu.ppfeaturemask` daran nichts ändert** |
| `no_permission` | Kein Schreibrecht auf den konkreten Pfad (`EACCES`), unter Nennung des Dienst-Users |
| `EINVAL` sonst | Kernel lehnt den Wert ab, mit `driver=` und `pwm_enable=` wie bisher |

Der Zusatz zu `ppfeaturemask` ist kein Beiwerk: Er ist der Grund, aus dem #480
ursprünglich falsch diagnostiziert wurde, und verhindert, dass jemand denselben
Weg noch einmal geht.

## API

`POST /api/fans/{fan_id}/gpu-manual-mode` antwortet bei `FIRMWARE_MANAGED` mit
**400** und klarer Begründung, statt `enable_amd_manual()` aufzurufen.

Zusätzlich wird `enable_amd_manual()` gegen halb angewendete Zustände
abgesichert: Es schreibt erst `performance_level=manual` und dann `pwm_enable`.
Scheitert der zweite Write, propagiert die Exception heute als 500, die GPU
bleibt in `manual` stehen, und `_gpu_manual_state[fan_id]` wurde nie gesetzt.
Künftig rollt ein `try/except` den ersten Write zurück und meldet den Fehler
sauber.

## Frontend

- `client/src/api/fan-control.ts` — `pwm_control` im Fan-Typ ergänzen.
- `FanCard.tsx` — Badge „Firmware" neben dem bestehenden GPU-Badge, wenn
  `pwm_control === 'firmware_managed'`.
- `FanDetails.tsx` — `GpuManualModeToggle` wird in diesem Fall nicht gerendert;
  Kurveneditor und PWM-Regler laufen über das vorhandene `isReadOnly`-Konzept
  mit. An die Stelle des Toggles tritt ein Erklärpanel.
- i18n `de` und `en`, Namespace `system`, unter `fanControl.gpu.*`.

Die Karte bleibt sichtbar. Lesen funktioniert auf RDNA3 einwandfrei — Drehzahl
und Temperatur sind weiterhin nützlich, nur Schreiben ist unmöglich.

## Dev-Mode

`fan_backend_dev.py` meldet für alle simulierten Lüfter `SUPPORTED`, damit sich
in der Dev-Umgebung nichts am bestehenden Verhalten ändert. Zusätzlich wird ein
simulierter firmware-verwalteter GPU-Lüfter aufgenommen, sonst ist der neue
UI-Pfad nur auf BaluNode prüfbar und auf der Windows-Entwicklungsmaschine
unsichtbar.

## Tests

Backend, mit `tmp_path`-sysfs-Bäumen im Stil des vorhandenen
`test_fan_gpu_manual_mode.py`:

- **neu** `test_fan_pwm_control_probe.py` — Baum mit und ohne
  `gpu_od/fan_ctrl/fan_curve`, plus Nicht-AMD-Fall und fehlendes Device.
- **erweitern** `test_fan_einval_diagnostic.py` — die drei Meldungsvarianten;
  explizit, dass „enable manual mode in the UI" bei `firmware_managed` **nicht**
  mehr vorkommt und `ppfeaturemask` erwähnt wird.
- **Loop** — firmware-verwalteter Lüfter, `set_pwm` wird nicht aufgerufen, und
  der geschriebene Sample trägt den tatsächlichen PWM-Wert.
- **Route** — `gpu-manual-mode` liefert 400 statt 500; Rollback-Pfad in
  `enable_amd_manual` stellt `performance_level` wieder her.

Frontend: unter `client/src/__tests__` existiert bisher kein Fan-Test. Es
entsteht einer für Badge und ausgeblendeten Toggle.

Vor dem PR lokal: die betroffenen pytest-Dateien gezielt, dazu `npx vitest run`,
`eslint .` und `npm run build`. Die vollständige Backend-Suite läuft auf Windows
nicht durch und bleibt CI überlassen.

## Risiken

- **Cache-Aktualität.** `pwm_control` wird beim Scan bestimmt. Wechselt die
  Hardware-Situation zur Laufzeit (Treiber-Reload, GPU-Hotplug), bleibt der Wert
  bis zum nächsten Scan stehen. Für eine Eigenschaft, die sich faktisch nur mit
  der Karte ändert, ist das vertretbar; der Fehlerpfad korrigiert
  `NO_PERMISSION` ohnehin nachträglich.
- **Erkennung nur über einen Pfad.** Die Zuordnung „`gpu_od/fan_ctrl/fan_curve`
  vorhanden ⇒ PWM unmöglich" ist an einer Karte gemessen (RX 7900 XT). Sie
  entspricht dem SMU13-Verhalten, ist aber nicht über die gesamte RDNA3-Reihe
  verifiziert. Fällt eine Karte auf, die beides kann, verliert sie durch diese
  Änderung die PWM-Steuerung — sichtbar am Badge, und über den
  Fehlermeldungstext zurückverfolgbar.
- **Nicht gemessen:** ob `gpu_od/` ohne `amdgpu.ppfeaturemask=0xffffffff`
  verschwindet. Auf BaluNode ist der Parameter gesetzt; der Gegenfall ließe sich
  nur mit einem Reboot ohne Parameter prüfen. Die Implementierung darf deshalb
  **nicht** aus einem fehlenden `gpu_od/` auf „Overdrive fehlt" schließen und
  daraus eine Handlungsempfehlung ableiten — das wäre exakt der Fehler, den
  dieses Design behebt.
