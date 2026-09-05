# Stabile Lüfter- und Sensor-Identität statt hwmon-Index

**Status:** Design freigegeben (2026-09-05)
**Issue:** #532
**Branch:** `feat/stable-fan-identity-532` (von `main`)
**Voraussetzung:** #517/#480 (PR #537) und #533 (PR #539) sind gemergt.

## Kontext

`fan_id` wird heute aus dem hwmon-Index gebildet (`fan_backend_linux.py`:
`fan_id = f"{hwmon_dir.name}_pwm{pwm_num}"`), `temp_sensor_id` analog
(`hwmon<N>_temp<M>`). Der hwmon-Index ist über Reboots, Kernel-Updates und
Änderungen der Modul-Ladereihenfolge nicht stabil. Bei jeder Umnummerierung
erkennt BaluHost dieselben physischen Lüfter als neue, legt einen frischen Satz
`fan_configs` an, und die vorher eingestellte Kurve ist für den Nutzer verloren.

Auf BaluNode liegen dadurch **16 Config-Zeilen für 4 physische Lüfter** vor, alle
`is_active=True`, in vier Generationen:

```
2026-01-25   hwmon5_pwm{1,2,3,7}   temp_sensor_id=hwmon5_temp6
2026-07-06   hwmon1_pwm1           temp_sensor_id=hwmon3_temp1
2026-07-20   hwmon2_pwm{1,2,3,7}   temp_sensor_id=hwmon3_temp1
2026-08-07   hwmon3_pwm{1,2,3,7}   temp_sensor_id=hwmon4_temp1   <- aktuell live
```

Dazu drei `dev_*`-Zeilen aus Dev-Läufen. Einen Aufräummechanismus gibt es nicht.

Bis #517 war der Verlust folgenlos, weil die Kurve ohnehin nicht wirkte. Seit dem
Deploy von PR #537 regelt sie nachweislich (gemessen 2026-09-05: `pwm` bewegt
sich bei 76–79 statt starr auf 128) — damit ist eine vom Nutzer eingestellte
Kurve zum ersten Mal etwas wert, und ihr Verlust ein echter Schaden.

## Ziele

- Lüfter- und Sensor-Identität so bilden, dass sie ein Renumbering überlebt.
- Bestehende Konfigurationen auf die neue Identität überführen, ohne eine Kurve
  dem falschen Lüfter zuzuordnen.
- Verwaiste Generationen deaktivieren statt sie unbegrenzt als `is_active`
  liegen zu lassen.

## Nicht-Ziele

- Kein Löschen von Altzeilen. Deaktivieren genügt; eine falsch zugeordnete Kurve
  muss nachvollziehbar bleiben.
- Keine Erhaltung der Lüfter-Historie (`fan_sample`). Bewusst akzeptiert: alte
  Samples behalten ihre alte ID und laufen über die bestehende Retention aus,
  der Verlaufsgraph beginnt zum Umstellungszeitpunkt neu.
- Keine Änderung an Kurvenauswertung, Zeitplänen, Profilen oder Presets.
- Keine UI-Änderung (siehe Abschnitt 4 — es ist keine nötig).

---

## 1. Identität und ihre Ableitung

### Gewählter Anker: der libsensors-Chipname

`sensors.conf(5)` definiert Chip-Namen als `<prefix>-<bus>-<adresse>`. Das ist
eine dokumentierte, außerhalb von BaluHost gültige Konvention, und sie ist auf
der Zielhardware bereits sichtbar — es sind exakt die Überschriften, die
`sensors` ausgibt.

```
Lüfter:  nct6798-isa-0290:pwm1
Sensor:  hwmon:k10temp-pci-00c3:temp1
```

Der `hwmon:`-Präfix bei Sensoren bleibt, weil `fan_sources.py` die Namensräume
`hwmon:` / `gpu:` / `disk:` / `mix:` bereits so führt; ersetzt wird nur der Teil
dahinter.

**Warum nicht der Gerätepfad (fancontrol-Stil).** `fancontrol` speichert
`DEVPATH`/`DEVNAME` aus `readlink -f /sys/class/hwmon/hwmonN/device`. Das ist
einfacher zu bilden, hat aber zwei Nachteile: bei PCI steckt die ganze
Bridge-Kette drin (`0000:00:01.1/0000:01:00.0/0000:02:00.0/0000:03:00.0`), und
für NVMe enthält der Pfad den Instanzindex `nvmeN` — selbst wieder instabil, auf
BaluNode sogar gekreuzt (`hwmon0 → nvme1`, `hwmon1 → nvme0`). libsensors löst
beides bereits, indem es zum Bus-Gerät aufsteigt.

**Warum keine Indirektionstabelle.** Eine `fan_identity`-Tabelle (stabile Kennung
↔ aktueller hwmon-Pfad) würde die Datenmigration sparen, aber zwei Wahrheiten
über dieselbe Sache schaffen und das Aufräumproblem nur verschieben.

### Ableitungsregeln

Verifiziert gegen `lm-sensors/lib/sysfs.c` (nicht aus den beobachteten Werten
zurückgeschlossen):

```c
/* PCI */
entry.chip.addr = (domain << 16) + (bus << 8) + (slot << 3) + fn;
/* platform / of_platform -> ISA */
if (sscanf(dev_name, "%*[a-zA-Z0-9_-]%*1[.:]%d", &entry.chip.addr) == 1);
else if (sscanf(dev_name, "%x.%*s", &entry.chip.addr) == 1);
else entry.chip.addr = 0;
```

Zwei Details, die man sonst falsch rät: die PCI-Domain geht mit `<<16` **in** die
Adresse ein, und der Platform-Suffix wird **dezimal** gelesen (`nct6775.656` →
656 → als Hex ausgegeben `0290`).

Ableitung in dieser Reihenfolge:

1. Vom hwmon-Verzeichnis über `..` aufwärts bis zum ersten Elter, dessen
   `subsystem`-Symlink auf `pci` oder `platform` zeigt.
2. Präfix = Inhalt von `hwmon<N>/name`.
3. Adresse und Bus-Typ nach den zitierten Regeln.

### Kollisionsregel

Der libsensors-Name ist **nicht garantiert eindeutig**, und auf BaluNode
kollidiert er: `asus-nb-wmi` und `eeepc-wmi` haben beide keinen numerischen
Suffix (`addr = 0`) und melden beide `name = asus` — beide ergäben
`asus-isa-0000`.

Regel: liefert Schritt 3 die Adresse `0`, lautet die Kennung stattdessen
`<name>@<geräteverzeichnis>`, also `asus@asus-nb-wmi` und `asus@eeepc-wmi`.
Geräteverzeichnisnamen sind innerhalb ihres Busses eindeutig.

Die Regel hängt bewusst **nicht** davon ab, welche anderen Chips vorhanden sind —
sonst bekäme dieselbe Hardware je nach Nachbarn eine andere ID.

### Fallback

Findet Schritt 1 keinen `pci`/`platform`-Elter (rein virtuelle Chips), bleibt die
hwmon-indizierte Kennung stehen und wird als instabil markiert. Kein Erfinden
einer Pseudo-Identität: eine ID, die stabil aussieht und es nicht ist, wäre
schlimmer als der ehrliche Status quo. Auf BaluNode betrifft das keinen Chip;
die Aussage „Fan-IDs sind jetzt stabil" gilt trotzdem nicht unbedingt und ist so
zu dokumentieren.

---

## 2. Datenmodell und Migration

### Warum Zuordnung über den hwmon-Index falsch ist

Die naheliegende Migration — nimm `hwmonN_pwmM`, schau nach, was heute an
`hwmonN` hängt — geht auf den echten Daten schief:

```
2026-07-20   hwmon2_pwm1   <- war damals der nct6798 (Gehäuselüfter)
heute        hwmon2        =  amdgpu (GPU)
```

Blindes Index-Mapping klebte eine Gehäuselüfter-Kurve vom Juli auf den
GPU-Lüfter. Still, plausibel aussehend, Monate später bemerkt.

### Der Schlüssel ist `fan_configs.name`

`name` wird genau einmal bei der Entdeckung gesetzt, als
`f"{hwmon_name_value} PWM{pwm_num}"`, und ist **nicht über die API änderbar** —
`UpdateFanConfigRequest` (`backend/app/schemas/fans.py`) hat kein `name`-Feld.
Jede Altzeile trägt damit den Chip-Namen aus dem Moment ihrer Entstehung. Die
Juli-Zeile heißt `"nct6798 PWM1"`, heute ist `hwmon2` der `amdgpu` — Widerspruch,
also kein Kandidat.

### Zuordnungsregeln

1. Nur Zeilen der Form `^hwmon\d+_` werden angefasst. `dev_*`-Zeilen und bereits
   stabile IDs bleiben unberührt; damit ist der Lauf idempotent.
2. Kandidat ist eine Zeile, wenn der Chip-Name aus `name` heute genau einen Chip
   trifft **und** der Kanal auf diesem Chip existiert. Der Chip-Name ist der
   Teil von `name` vor dem letzten `" PWM"` (Format `"<chip> PWM<n>"`); die
   Kanalnummer stammt aus dem `pwm<M>`-Teil der alten `fan_id`. Trifft der
   Chip-Name heute mehrere Chips (zwei baugleiche Karten), ist die Zeile kein
   Kandidat — Raten wäre hier schlimmer als Nichtstun.
3. Konkurrieren mehrere Zeilen um dieselbe neue ID, gewinnt die mit dem jüngsten
   `updated_at`.
4. Alles Übrige: `is_active=False`. Nichts wird gelöscht.
5. Jede Übernahme als INFO-Zeile `alt → neu`, dazu eine Zusammenfassung.

Ergebnis auf BaluNode: alle Generationen der Gehäuselüfter tragen
`"nct6798 PWM…"` und zielen auf dieselben vier neuen IDs; die Generation vom
2026-08-07 gewinnt und die Kurven überleben. Von den 16 Zeilen bleiben damit
4 aktiv, **9** werden inaktiv, und die 3 `dev_*`-Zeilen bleiben nach Regel 1
unberührt.

### Schema

Eine Alembic-Migration, **nur Struktur**:

```
fan_configs        + legacy_fan_id     String(100) NULL
temp_sensor_labels + legacy_sensor_id  String(120) NULL
```

Keine Spaltenverbreiterung nötig — die längste neue ID
(`hwmon:asus@asus-nb-wmi:temp1`, 28 Zeichen) passt in die bestehenden Breiten.

### Wo die Umschreibung läuft

Beim **Dienststart** in `_load_fan_configs`, nicht in der Migration. Eine
Migration, die sysfs der Zielmaschine liest, verhielte sich in CI, auf einem
Dev-Rechner und bei einem DB-Restore jeweils anders — dort existiert die
Hardware nicht. Zur Startzeit ist der hwmon-Scan ohnehin gelaufen.

Bei vier Uvicorn-Workern läuft der Abgleich nur im Primary-Worker (Muster aus
#465).

Mitzuziehen mit derselben Abbildung: `fan_configs.sync_fan_id`,
`fan_schedule_entries.fan_id`.

### Sensor-IDs: die schwächere Stelle

Für Sensoren gibt es kein Gegenstück zu `name`. `fan_configs.temp_sensor_id` ist
ein nackter String; `temp_sensor_labels.sensor_id` ist ein Primärschlüssel mit
einem Nutzer-Label, aber ohne Chip-Herkunft.

Deshalb: Sensor-IDs werden über den **heutigen Index** aufgelöst. Löst der Index
nicht auf, fällt der Lüfter auf den CPU-Sensor-Default zurück. Beide Fälle werden
als WARNING geloggt, nicht still ausgeführt. Der Schaden im Fehlerfall ist „der
Lüfter folgt dem falschen Sensor" — in der UI sichtbar und mit einem Klick
korrigierbar.

`composite_temp_sensors.source_ids_json` wird mit derselben Abbildung
umgeschrieben (auf BaluNode leer). Kollidieren zwei Altzeilen auf denselben neuen
`temp_sensor_labels`-Primärschlüssel, gewinnt die jüngste; die verworfene wird
geloggt.

Eine Chip-Namensspalte für `temp_sensor_labels` wurde erwogen und **verworfen**:
sie hülfe nur künftigen Index-Migrationen, die es nach dieser Umstellung per
Konstruktion nicht mehr gibt.

---

## 3. Auflösung zur Laufzeit

Der Scan in `_scan_pwm_fans` bildet die neue Form direkt; `_fan_cache` ist damit
auf stabile Schlüssel umgestellt. Als Nebeneffekt überlebt der Write-Backoff aus
#533 ein Renumbering — heute verliert er seinen Eintrag, weil der Schlüssel
wechselt.

**Abwesenheit darf niemals schreiben.** Beim Dienststart kann ein Treiber noch
nicht geladen sein; ein Lüfter fehlt dann im Scan, ohne dass die Hardware weg
wäre.

- Lüfter im Scan, ohne Config → Config mit Defaults anlegen (heutiges Verhalten).
- Config ohne Lüfter im Scan → nichts tun. Kein `is_active=False`, kein Löschen,
  keine Neuanlage.

Die bestehende Schutzregel in `_scan_pwm_fans` („found 0 fans, keeping cached
fans") bleibt und deckt denselben Gedanken eine Ebene tiefer ab.

Der Abgleich läuft genau einmal pro Start, im Primary-Worker, und fasst
ausschließlich Zeilen der Altform an. Zeilen in neuer Form sind für ihn
unsichtbar — ein zweiter Lauf ist folgenlos, auch wenn der erste abbrach.

**Akzeptanzkriterium:** Ein Reboot, der `nct6798` von `hwmon3` nach `hwmon5`
verschiebt, verändert die Kennung `nct6798-isa-0290:pwm1` nicht. Es entsteht
keine neue Config, die Kurve gilt weiter, es sammelt sich keine Generation an.

Sensor-Auflösung braucht keine neue Kompatibilitätsschicht: `TempSourceRegistry`
akzeptiert unpräfixierte Alt-IDs bereits, und nach dem Abgleich hält keine
aktive Config mehr eine Alt-ID.

---

## 4. API, Frontend, Konsumenten

**Das Frontend braucht keine Änderung.** Nachgeprüft: in `client/src/` gibt es
keine Stelle, die `fan_id`/`fanId` zerlegt (`split`, `slice`, `startsWith`,
`match`), und keine, die eine Lüfter-Auswahl in `localStorage` ablegt. Die ID ist
durchgehend ein undurchsichtiger Handle.

**Pfadparameter tragen die neue Form ohne Kodierungsarbeit.** Sechs Routen nehmen
`{fan_id}` (`/{fan_id}/schedule`, `/{fan_id}/gpu-manual-mode`, …). `:` und `@`
sind laut RFC 3986 gültige `pchar` in einem Pfadsegment; die Sensor-Routen
transportieren mit `hwmon:hwmon4_temp1` heute schon Doppelpunkte im Pfad und
funktionieren in Produktion.

**Mitzuziehen:**

- `backend/app/schemas/fans.py` — zehn Swagger-Beispiele auf `hwmon0_pwm1`.
- Rund 75 fest verdrahtete Vorkommen in neun Backend- und vier
  Frontend-Testdateien; betroffen sind die Stellen, die die gebildete ID
  *behaupten*.

**Kein API-Versionssprung.** Die ID war nie ein dokumentiertes Format, sondern
ein Handle; BaluApp und BaluDesk sprechen die Fan-Endpunkte nicht an. Ein Client
mit zwischengespeicherter Fan-ID bekommt eine 404 und lädt neu — bestehender
Fehlerpfad, kein neuer.

---

## 5. Tests und Verifikation

### Der Test, der das Issue beantwortet

Ein hwmon-Baum unter `tmp_path`, zweimal aufgebaut: derselbe Gerätepfad einmal
als `hwmon3`, einmal als `hwmon5`. Erwartung: identische Kennung, und
`_load_fan_configs` legt beim zweiten Durchlauf keine neue Zeile an.

### Kodierung gegen echte Pfade

Sollwerte sind die von `sensors` auf BaluNode gemeldeten Chip-Namen — also eine
unabhängige Implementierung derselben Regeln auf derselben Hardware:

| Gerätepfad | erwartete Kennung |
|---|---|
| `platform/nct6775.656` | `nct6798-isa-0290` |
| `pci…/0000:03:00.0` | `amdgpu-pci-0300` |
| `pci0000:00/0000:00:18.3` | `k10temp-pci-00c3` |
| `…/0000:0d:00.0/nvme/nvme1` | `nvme-pci-0d00` |
| `…/0000:0a:00.0/nvme/nvme0` | `nvme-pci-0a00` |
| `platform/asus-nb-wmi` | `asus@asus-nb-wmi` |
| `platform/eeepc-wmi` | `asus@eeepc-wmi` |

Die NVMe-Fälle sichern ab, dass der Aufstieg den instabilen `nvmeN` überspringt;
die letzten beiden die Kollisionsregel.

### Reconciliation

- Vier Generationen wie auf BaluNode (16 Zeilen) → jüngste gewinnt: 4 aktiv,
  9 inaktiv, 3 `dev_*` unberührt, null Löschungen.
- Die Falle: Zeile `hwmon2_pwm1` mit `name="nct6798 PWM1"`, während `hwmon2`
  heute der `amdgpu` ist → darf **nicht** zugeordnet werden.
- Zweiter Lauf folgenlos (Idempotenz).
- `dev_*`-Zeilen unberührt.
- Lüfter fehlt im Scan → keine Schreiboperation.
- Chip ohne `pci`/`platform`-Elter → Altform bleibt, als instabil markiert.

### Gates

`pytest -k "fan or power"` steht seit #539 bei 559 passed — das ist die Messlatte
plus die neuen Tests. Dazu `ruff check`, `eslint .`, `npm run build`,
`vitest run`. Die volle Backend-Suite bleibt der CI überlassen (hängt auf
Windows).

### Feldverifikation nach dem Deploy

1. Abgeleitete Kennungen gegen die `sensors`-Überschriften vergleichen — muss
   zeichengleich sein.
2. `modprobe -r nct6775 ; modprobe nct6775` erzwingt ein Renumbering ohne Reboot.
   Danach muss `fan_configs` gleich viele Zeilen haben wie davor.

Zu Schritt 2: beim Entladen verliert BaluHost kurzzeitig die Lüfter, und
`pwm_enable` fällt auf den Board-Default zurück. Bei Leerlauftemperaturen
ungefährlich, aber ein Eingriff — ein regulärer Reboot leistet dasselbe, nur ohne
Kontrolle über den Zeitpunkt.

---

## Risiken

- **Selbstgebaute Kodierung.** Die Adressbildung ist aus dem libsensors-Quelltext
  übernommen, nicht aus Beobachtungen zurückgeschlossen. Der Vergleich gegen die
  `sensors`-Ausgabe ist die Absicherung; für Bus-Typen jenseits `pci`/`platform`
  gibt es keine Testdaten auf dieser Hardware.
- **i2c-Busnummern sind laut lm-sensors selbst nicht reboot-stabil** (daher die
  `bus`-Statements und `sensors --bus-list`). Auf BaluNode ist alles `isa` oder
  `pci`, die Kennung darf sich aber nicht darauf verlassen, dass das so bleibt.
- **Sensor-Zuordnung bleibt heuristisch** (siehe Abschnitt 2). Fehlerbild ist ein
  falscher Sensor am Lüfter, sichtbar und korrigierbar, nicht stumm.
- **Einmaliger Vorgang mit Datenwirkung.** Der Abgleich läuft auf produktiven
  Zeilen. Absicherung: nichts wird gelöscht, `legacy_fan_id` hält die Herkunft
  fest, jede Übernahme wird geloggt.

## Quellen

- [sensors.conf(5)](https://manpages.debian.org/testing/lm-sensors/sensors.conf.5.en.html)
  — Chip-Namensformat `<prefix>-<bus>-<adresse>`
- [lm-sensors `lib/sysfs.c`](https://github.com/lm-sensors/lm-sensors/blob/master/lib/sysfs.c)
  — Adressbildung für PCI und platform/ISA
- [fancontrol(8)](https://www.systutorials.com/docs/linux/man/8-fancontrol/) —
  `DEVPATH`/`DEVNAME`, der Stand der Technik: Drift erkennen statt automatisch
  zuordnen
- [lm-sensors#227](https://github.com/lm-sensors/lm-sensors/issues/227) —
  „fancontrol: use sensors' stable names"
- [Fan speed control — ArchWiki](https://wiki.archlinux.org/title/Fan_speed_control)
