# GPU-Lüfterakustik über `gpu_od/fan_ctrl` steuerbar machen

Entwurf zu #516, Fassung vom 2026-09-06.

## Kontext

#480 hat festgestellt, dass auf RDNA3 keine Live-PWM-Steuerung möglich ist: `pwm{n}_enable` wird folgenlos geschluckt, `pwm{n}` lehnt mit `EINVAL` ab. Der Fix dort beschränkt sich darauf, das ehrlich zu melden (`pwm_control == FIRMWARE_MANAGED`). Seit #569 zeigt die Lüfterkarte für so einen Kanal keine wirkungslosen Modus-Regler mehr.

Damit ist der GPU-Lüfter korrekt beschrieben — und weiterhin nicht beeinflussbar. Dieser Entwurf schließt das über den Weg, auf dem die Karte ihre Lüftersteuerung tatsächlich anbietet: `/sys/class/drm/card0/device/gpu_od/fan_ctrl/`.

### Die Prämisse ist gemessen, nicht der Kernel-Doku entnommen

Auf BaluNode (RX 7900 XT, Kernel `6.12.74+deb13+1-amd64`), 2026-09-06:

```
$ ls -l /sys/class/drm/card*/device/gpu_od/fan_ctrl/
-rw-r--r-- 1 root root 4096 acoustic_limit_rpm_threshold
-rw-r--r-- 1 root root 4096 acoustic_target_rpm_threshold
-rw-r--r-- 1 root root 4096 fan_curve
-rw-r--r-- 1 root root 4096 fan_minimum_pwm
-rw-r--r-- 1 root root 4096 fan_target_temperature
```

Jeder Knoten meldet Wert **und** Bereich in einheitlicher Form:

```
FAN_TARGET_TEMPERATURE:
95
OD_RANGE:
TARGET_TEMPERATURE: 25 105
```

Schreibweg, Validierung und Speicherung sind belegt:

```
$ echo 200 | sudo tee $F/fan_target_temperature
tee: ...: Das Argument ist ungültig            # EINVAL gegen den gemeldeten Bereich

$ echo 25 | sudo tee $F/fan_target_temperature
$ echo c  | sudo tee $F/fan_target_temperature
$ cat $F/fan_target_temperature
FAN_TARGET_TEMPERATURE:
25                                              # gespeichert und übernommen
```

**Das ist der entscheidende Unterschied zu `pwm_enable`:** dieser Treiber prüft unsere Eingabe und speichert sie. Ein angenommener Write beweist auf dieser Karte sonst nichts — #480 ist der Beleg dafür, dass amdgpu lüfterbezogene Writes wortlos verschlucken kann.

### Zero-RPM begrenzt, was im Leerlauf sichtbar ist

`fan_target_temperature` auf 25 gesetzt, bei Junction ≈ 40 °C: `fan1_input` blieb `0`, `pwm1` blieb `0`. Die Karte schaltet den Lüfter im Leerlauf ab; die Akustikwerte formen das Verhalten erst oberhalb dieser Schwelle.

Ein `fan_zero_rpm_enable` gibt es auf `6.12.74` **nicht** — der Knoten kam erst in späteren Kernelfassungen dazu. BaluHost kann diese Schwelle also nicht verschieben. Sie ist eine Grenze des Entwurfs, keine Aufgabe darin.

## Ziele

- Die vier Akustik-Skalare der Karte aus BaluHost setzen: `fan_target_temperature`, `acoustic_limit_rpm_threshold`, `acoustic_target_rpm_threshold`, `fan_minimum_pwm`.
- Die Werte über Reboots halten, indem BaluHost sie beim Start wieder anwendet.
- Den Zero-RPM-Zustand in der Oberfläche benennen, statt `0 RPM` unkommentiert zu zeigen.
- Auf einen zweiten Verwalter derselben Knoten hinweisen, wenn einer erkannt wird.

## Nicht-Ziele

- **`fan_curve`** (fünf Stützstellen, Temperatur → Prozent). Braucht eine eigene Editor-Ansicht, weil der vorhandene Kurveneditor mit freien Stützstellen arbeitet und die Firmware genau fünf Punkte mit festen Bereichen vorgibt. Später, wenn die Skalare sich als tragfähig erwiesen haben.
- **Andere GPU-Familien.** Ältere AMD-Karten mit Live-PWM und NVIDIA/nouveau bleiben außen vor. Eine Abstraktion über Hardware, an der niemand messen kann, wäre eine Behauptung statt eines Entwurfs.
- **Zero-RPM abschalten.** Auf diesem Kernel nicht exponiert.
- **Automatisches Zurücksetzen beim Dienst-Ende.** Siehe die Abgrenzung zu #534 unten.

### Warum es hier kein Gegenstück zur Rückgabe aus #534 gibt

#534 gibt `pwm_enable` beim Beenden an die Board-Automatik zurück, weil sonst *niemand* regelt: BaluHost ist weg, und der Chip ist abgeschaltet.

Hier ist die Lage umgekehrt. Ein zurückgelassener Akustikwert lässt den Lüfter **nicht** ungeregelt — die Firmware regelt weiter, nur mit anderen Parametern. Die Werte beim Beenden zurückzusetzen wäre kein Sicherheitsnetz, sondern würde dem Nutzer bei jedem Deploy-Neustart seine Einstellung wegnehmen. Das Muster wird deshalb bewusst nicht gespiegelt.

## Entscheidungen

| Frage | Entscheidung |
|---|---|
| Umfang | Nur die vier Skalare, keine Kurve |
| Konkurrenz mit LACT | BaluHost übernimmt; LACT gibt `pmfw_options` ab. BaluHost erkennt und warnt, greift aber nicht ein |
| Eigentum der Werte | BaluHost verwaltet sie: Datenbank, Anwendung beim Start, ausdrückliche Rücksetz-Aktion |
| Abnahme | Unter Spielelast, weil Zero-RPM den Leerlauf aussagelos macht |

## 1. Datenmodell

`GpuPowerConfigDb` zeigt das Muster dieses Codebase für GPU-Konfiguration: eine Singleton-Zeile mit einem JSON-Feld, validiert durch ein Pydantic-Schema. Übernommen, aber in einer **eigenen** Tabelle — die Akustikwerte gehören nicht in die Power-Konfiguration.

```
gpu_fan_acoustics_config    id (PK, =1), config_json, updated_at, updated_by_pid
```

Im JSON zwei Blöcke desselben Schemas:

```python
class GpuFanAcousticsValues(BaseModel):
    target_temperature:  Optional[int] = None
    acoustic_limit_rpm:  Optional[int] = None
    acoustic_target_rpm: Optional[int] = None
    minimum_pwm:         Optional[int] = None
```

`desired` — was BaluHost anwenden soll.
`baseline` — was auf der Karte stand, bevor BaluHost sie erstmals angefasst hat.

### `None` heißt „nicht verwaltet"

Beim Start wird nur geschrieben, was gesetzt ist. Ein leeres `desired` bedeutet: Finger weg. Damit schreibt BaluHost nicht bei jedem Start Standardwerte über eine Einstellung, die jemand anders gesetzt hat. Dieselbe Semantik wie `pwm_enable_restore` aus #534.

### Die Baseline wird beobachtet, nicht geraten

Vor dem ersten Write auf einen Knoten wird sein Ist-Wert erfasst und in `baseline` abgelegt. Die Aktion „auf Standard zurücksetzen" schreibt diesen Wert.

Damit braucht der Entwurf das `r`-Kommando aus der Kernel-Doku nicht, das nicht verifiziert wurde, und rät keinen Herstellerstandard. Es ist das Prinzip aus #534: zurückgeschrieben wird nur, was BaluHost selbst gelesen hat.

Auf BaluNode erfasst das den Zustand, den LACT hinterlassen hat (`acoustic_limit = 3000`). Das ist gewollt — „wie es vor BaluHost war" ist die ehrliche Bedeutung von Zurücksetzen.

### Nur der Primary wendet an

BaluHost läuft mit vier Uvicorn-Workern. `desired` beim Start auf die Karte zu schreiben, ist ein Hardware-Eingriff und gehört deshalb hinter `IS_PRIMARY_WORKER` — sonst schreiben vier Prozesse dieselben vier Werte gegeneinander.

Das ist keine Vorsichtsmaßnahme auf Verdacht: #555 und #559 haben an derselben Stelle gezeigt, was passiert, wenn ein Sekundär-Worker Hardware anfasst. Der `PUT`-Endpunkt schreibt dagegen von dem Worker, der die Anfrage bedient — ein einzelner, ausdrücklich angeforderter Write, kein Dauerbetrieb.

### Warum JSON statt vier Spalten

Ein fünfter Regler — etwa `fan_curve`, wenn er später dazukommt — ist dann eine Schema-Änderung ohne Migration.

## 2. Das Modul

`backend/app/services/power/fan_gpu_acoustics.py`, neben `fan_gpu_manual.py`.

```python
def parse_node(text: str) -> ParsedNode
def find_fan_ctrl_dir(hwmon_dir: Path) -> Optional[Path]
async def read_acoustics(fan_ctrl_dir: Path) -> Dict[str, ParsedNode]
async def write_acoustic(fan_ctrl_dir: Path, key: str, value: int, write) -> bool
```

### `parse_node` liest positionell, nicht über Schlüsselnamen

Der Wert ist die Zeile nach dem ersten `…:`, der Bereich sind die zwei Zahlen nach `OD_RANGE:`.

Grund: die Namen sind nicht einheitlich — `FAN_TARGET_TEMPERATURE` gegen `TARGET_TEMPERATURE`, `OD_ACOUSTIC_LIMIT` gegen `ACOUSTIC_LIMIT`. Auf Namen zu parsen hieße, eine Inkonsistenz des Treibers in unseren Code zu übernehmen.

Die Funktion ist rein und ohne Hardware testbar — wie `fan_restore.py` aus #534.

### `find_fan_ctrl_dir` erbt vorhandene Arbeit

`fan_gpu_manual._device_from_hwmon()` findet bereits den Weg von einem hwmon-Verzeichnis zum amdgpu-Gerät, samt der in #480 gelernten Fallstricke (der `device`-Symlink ist der Primärweg; der Aufwärtslauf funktioniert nur in synthetischen Bäumen).

### `write_acoustic` bekommt die Schreibfunktion übergeben

Statt die Leiter aus direktem Write und `sudo tee`-Fallback nachzubauen, wird `LinuxFanControlBackend._write_hwmon_file` hineingereicht. Sie bleibt der einzige Ort, an dem diese Leiter existiert — #554 hat gezeigt, wohin das Duplizieren führt.

Ablauf je Wert: Bereichsprüfung, Wert schreiben, `c` schreiben, **zurücklesen zur Kontrolle**.

Die Baseline erfasst **nicht** dieses Modul, sondern die aufrufende Dienstschicht: sie liest vor dem ersten Write und legt den Wert in der Konfiguration ab. Das Modul bleibt zustandslos und kennt die Datenbank nicht — dieselbe Trennung wie zwischen `fan_restore.py` (reine Regel) und `fan_control.py` (Persistenz) in #534. Der Rücklese-Schritt spiegelt `release_to_board` aus #534: ein angenommener Write beweist auf dieser Karte nichts.

Die Bereichsprüfung ist Doppelung zum Kernel (belegt: `EINVAL` bei 200). Sie bleibt, weil eine Fehlermeldung aus der UI besser ist als eine aus `dmesg`.

## 3. Rechte

Alle fünf Knoten sind `root:root 0644`; der Dienst läuft unprivilegiert.

Der Mechanismus existiert: `deploy/install/templates/70-baluhost-amd-gpu.rules` setzt für `power_dpm_force_performance_level` und `pp_power_profile_mode` bereits `chgrp video` plus `g+w`, und `install-amd-gpu-permissions.sh` nimmt den Dienstnutzer in die `video`-Gruppe auf. Die Regel läuft bei `add|change`, also auch nach Reboot und Resume.

**Der Entwurf erweitert die vorhandene Regel um `device/gpu_od/fan_ctrl/*`.** Kein neuer Mechanismus, keine neue Datei.

### Die offene Stelle

`gpu_od/` legt amdgpu erst beim Initialisieren des Overdrive-Teils an, nicht zwingend zum Zeitpunkt von `ACTION=="add"`. Feuert die Regel zu früh, greift der `[ -e "$f" ]`-Schutz und es passiert **stillschweigend nichts**.

Deshalb gehört in den Plan eine Messung statt einer Annahme: nach Deploy **und nach einem Reboot** prüfen, ob die Knoten `root:video` mit `g+w` tragen. Tun sie es nicht, ist die Antwort ein systemd-Oneshot nach `multi-user.target` — gebaut wird der erst, wenn die Messung ihn verlangt.

### Was ausdrücklich nicht vorgeschlagen wird

Die sudoers-Regel um `tee /sys/class/drm/*` zu erweitern. Das wäre der bequeme Ausweg und eine echte Ausweitung der Root-Angriffsfläche für ein Problem, von dem noch nicht feststeht, ob es existiert. Die Reviewer-Checkliste in `.claude/rules/ci-cd-security.md` fragt genau danach.

### Betriebsschritt

`deploy/` steht in CODEOWNERS — der PR wird owner-markiert. Die Installationsskripte erreichen die Box nur über den `SYNC_PERMISSIONS`-Block von `ci-deploy.sh`; der Deploy muss dafür einmal mit gesetztem Schalter laufen.

## 4. API

Zwei Endpunkte unter den Fans-Routen, weil der Nutzer die Einstellung dort sucht.

**`GET /api/fans/gpu-acoustics`** liefert je Wert den aktuellen Stand und den vom Treiber gemeldeten Bereich, dazu:

- `available` — hat die Karte diese Schnittstelle überhaupt? Fehlt sie, kommt `available: false` statt eines Fehlers, und die UI blendet das Panel aus.
- `zero_rpm` — steht der Lüfter gerade still?
- `competing_manager` — wurde ein zweiter Verwalter erkannt?

**`PUT /api/fans/gpu-acoustics`** setzt einen oder mehrere Werte. Admin-only, Pydantic-Schema, Rate-Limit über `admin_operations`.

**`null` für ein Feld bedeutet „nicht mehr verwalten"** und schreibt die Baseline zurück. Der Zurücksetzen-Knopf ist damit ein `PUT` mit lauter `null` und braucht keinen eigenen Endpunkt — die API bildet exakt die Semantik des Datenmodells ab.

Gibt es für ein Feld keine Baseline, weil BaluHost den Knoten nie angefasst hat, passiert nichts. Kein Rückfall auf einen Herstellerstandard: derselbe Verzicht wie in #534 — zurückgeschrieben wird nur ein selbst gelesener Wert.

### Erkennung eines zweiten Verwalters

Über die Konfigurationsdatei: existiert `/etc/lact/config.yaml` und enthält sie `pmfw_options`, meldet der GET das als Warnung.

Bewusst ein Dateilesen und kein `pgrep` — kein Subprozess, keine Testflakiness, und die Warnung verschwindet von selbst, sobald der Block entfernt wird. Blockiert wird nichts: die Entscheidung ist, dass BaluHost übernimmt.

## 5. UI

### Das Panel wohnt in `FirmwareFanNotice`

Die Komponente wird heute genau dann gezeigt, wenn ein AMD-GPU-Lüfter firmware-verwaltet ist. Sie erklärt bisher nur, dass die Firmware regelt; künftig erklärt sie es **und** bietet die vier Regler an. Gleiche Stelle, gleiche Bedingung, kein neuer Ort in der Navigation.

Vier Schieber mit den vom Treiber gemeldeten Grenzen, ein Speichern, ein „Auf Standard zurücksetzen". Keine Voreinstellungen wie „Leise / Ausgewogen": dafür müssten RPM- und Temperaturkombinationen erfunden werden, die niemand validiert hat.

### Zero-RPM wird ein benannter Zustand

Auf der Lüfterkarte ersetzt bei firmware-verwalteter Karte mit 0 RPM ein benannter Zustand die nackte Null. Heute liest sich `RPM 0 / PWM 0%` wie ein Defekt.

Im Akustik-Panel steht dazu, dass diese Werte erst greifen, wenn der Lüfter läuft — sonst setzt man einen Wert, sieht keine Wirkung und schließt auf einen Fehler. Dieselbe Sorte lügender Anzeige, die #552 beseitigt hat.

Beides bleibt als **Ableitung** formuliert: einen `fan_zero_rpm_enable`-Knoten gibt es auf `6.12` nicht, geschlossen wird aus „firmware-verwaltet **und** 0 RPM".

## 6. Tests und Verifikation

### Ohne Hardware

- `parse_node` gegen die tatsächlichen Ausgabeformate aller fünf Knoten, inklusive der uneinheitlichen Schlüsselnamen.
- Bereichsprüfung: Werte außerhalb `OD_RANGE` werden vor dem Write abgelehnt.
- `write_acoustic`: Wert, dann `c`, dann Rücklesen; ein abweichender Rücklesewert ist ein Fehlschlag.
- Baseline: wird beim ersten Write erfasst und danach nicht überschrieben.
- `None` in `desired` schreibt nichts.
- `PUT` mit lauter `null` stellt die Baseline her.
- Verdrahtung: der Start wendet `desired` tatsächlich an. Gegenprobe ausführen — die Aufrufstelle entfernen und rot sehen.

### Auf der Hardware, unter Last

Zero-RPM macht den Leerlauf aussagelos. Gemessen wird mit einem Spiel als Last, Hebel ist `fan_target_temperature` von 95 auf 75 — die sichere Richtung: mehr Kühlung, nicht weniger.

Die Sensor-Zuordnung ist gemessen, sie muss im Test nicht ermittelt werden:

```
hwmon2/temp1_input = edge        hwmon2/temp2_input = junction        hwmon2/temp3_input = mem
```

| | junction | fan1_input | pwm1 |
|---|---|---|---|
| Leerlauf, unverwaltet | 40–52 | 0 | 0 |
| Last, unverwaltet | | | |
| Last, `target_temperature = 75` | | | |
| nach „Zurücksetzen" | | | |

**Die Last muss hoch genug sein.** Display eingeschaltet und Steam-Client geöffnet bringen die Karte auf 52 °C Junction — und der Lüfter stand immer noch (gemessen 2026-09-06). Der Client allein genügt also nicht, es braucht ein laufendes Spiel. Die Zero-RPM-Schwelle dieser Karte liegt darüber; ein Messpunkt, an dem `fan1_input` noch `0` ist, sagt über die Akustikwerte nichts aus. Erste Bedingung jeder Lastmessung ist deshalb: **der Lüfter dreht.**

Erwartet zwischen Zeile 2 und 3: **RPM steigt, Junction sinkt.** Bleibt beides gleich, ist der Regler auch unter Last wirkungslos — dann ist das Feature kosmetisch, und das gehört gesagt statt ausgeliefert.

Die Gegenprobe in die andere Richtung (`acoustic_limit` senken, RPM deckeln, Junction steigt) ist aussagekräftiger, lässt die Karte aber wärmer laufen. Nur, falls die erste Messung uneindeutig ausfällt.

### Drei weitere Zusagen, ohne Last prüfbar

- **Backend-Neustart** → die gesetzten Werte stehen wieder auf der Karte.
- **Reboot** → dasselbe, **und** die Knoten tragen `root:video` mit `g+w`. Hier fällt die offene udev-Frage aus Abschnitt 3.
- **Zurücksetzen** → die Baseline steht wieder da, `desired` ist leer.

## 7. Risiken

| Risiko | Umgang |
|---|---|
| udev feuert vor dem Anlegen von `gpu_od/` | Nach Reboot messen; falls ja, systemd-Oneshot statt Ausweitung der sudoers-Regel |
| Die Werte wirken auch unter Last nicht | Der Abnahmetest deckt es auf, bevor das Feature als brauchbar gilt |
| LACT schreibt weiter mit | Erkennung meldet es sichtbar; die Lösung ist das Entfernen von `pmfw_options`, nicht ein Wettschreiben |
| Kernel-Wechsel ändert Knoten oder Format | `parse_node` liest positionell und die Bereiche kommen vom Treiber — ein zusätzlicher Knoten bricht nichts, ein entfernter führt zu `available: false` |

## Bezug

- #516 — dieses Feature
- #480 — hat `pwm_control` und die RDNA3-Feststellung eingeführt
- #534 / #556 — Herkunft der Prinzipien „nur beobachtete Werte" und „Rücklesen zur Kontrolle"
- #536 — die Grundsatzfrage Firmware gegen Software; dieser Entwurf ist unabhängig davon, weil für den GPU-Lüfter keine Software-Alternative existiert
- #569 — hat die wirkungslosen Modus-Regler entfernt; dieses Panel füllt die entstandene Lücke
