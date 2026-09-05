# Stabile Lüfter- und Sensor-Identität statt hwmon-Index

**Status:** Design freigegeben (2026-09-05), überarbeitet nach kritischer Review
**Issue:** #532
**Branch:** `feat/stable-fan-identity-532` (von `main`)
**Voraussetzung:** #517/#480 (PR #537) und #533 (PR #539) sind gemergt.
**Normative libsensors-Version:** 3.6.2 (`dpkg -l lm-sensors` auf BaluNode:
`1:3.6.2-2`). Die Parsing-Regeln haben sich zwischen 3.6.0, 3.6.1/3.6.2 und
`master` verändert — Aussagen gegen `master` sind für diese Box nicht gültig.

## Kontext

`fan_id` wird heute aus dem hwmon-Index gebildet (`fan_backend_linux.py`:
`fan_id = f"{hwmon_dir.name}_pwm{pwm_num}"`), `temp_sensor_id` analog
(`hwmon<N>_temp<M>`). Der hwmon-Index ist über Reboots, Kernel-Updates und
Änderungen der Modul-Ladereihenfolge nicht stabil. Bei jeder Umnummerierung
erkennt BaluHost dieselben physischen Lüfter als neue, legt einen frischen Satz
`fan_configs` an, und die vorher eingestellte Kurve ist für den Nutzer verloren.

### Gemessener Ist-Zustand auf BaluNode (2026-09-05)

`SELECT fan_id, name, temp_sensor_id, updated_at FROM fan_configs ORDER BY updated_at`
liefert **16 Zeilen: 13 hwmon-indizierte für 5 physische Lüfter, plus 3 `dev_*`**,
alle `is_active=True`:

```
hwmon5_pwm1/2/3/7 | nct6798 PWM1/2/3/7 | hwmon5_temp6 | 2026-01-25
dev_case_fan_1    | Case Fan 1 (Simulated) | dev_package_temp | 2026-01-27
dev_cpu_fan       | CPU Fan (Simulated)    | dev_cpu_temp     | 2026-02-17
dev_case_fan_2    | Case Fan 2 (Simulated) | dev_cpu_temp     | 2026-02-25
hwmon1_pwm1       | amdgpu PWM1        | hwmon3_temp1 | 2026-07-06
hwmon2_pwm1/2/3/7 | nct6798 PWM1/2/3/7 | hwmon3_temp1 | 2026-07-20
hwmon3_pwm1/2/3/7 | nct6798 PWM1/2/3/7 | hwmon4_temp1 | 2026-08-07
```

Alle `temp_sensor_id` liegen **unpräfixiert** vor — es sind durchweg Defaults aus
`_load_fan_configs`, keine vom Nutzer über die UI gesetzten (die kämen
präfixiert als `hwmon:…` an, siehe `routes/fans.py:349`).

### Der Schaden ist nicht nur zukünftig — er ist bereits eingetreten

Heute ist `hwmon2` der `amdgpu`, die GPU-Lüfter-ID lautet also `hwmon2_pwm1`.
Unter genau dieser ID liegt die **Juli-Zeile eines Gehäuselüfters**
(`name = "nct6798 PWM1"`, `temp_sensor_id = hwmon3_temp1`). `_load_fan_configs`
sucht ausschließlich über `fan_id` und findet sie. Der GPU-Lüfter läuft damit
auf der Konfiguration eines Gehäuselüfters.

Folgenlos ist das nur, weil die RDNA3-GPU firmware-verwaltet ist und `set_pwm()`
seit #480 dort ohnehin aussteigt. Die Migration behebt diese Fehlzuordnung als
Nebeneffekt: `hwmon2_pwm1` trägt den Chip-Namen `nct6798` und wird korrekt dem
nct6798 zugeordnet, die GPU erhält über `hwmon1_pwm1` (`amdgpu PWM1`) ihre eigene
Zeile zurück.

Bis #517 war der Verlust folgenlos, weil die Kurve ohnehin nicht wirkte. Seit dem
Deploy von PR #537 regelt sie nachweislich (gemessen 2026-09-05: `pwm` bewegt
sich bei 76–79 statt starr auf 128) — damit ist eine Konfiguration zum ersten Mal
etwas wert.

## Ziele

- Lüfter- und Sensor-Identität so bilden, dass sie ein Renumbering überlebt.
- Bestehende Konfigurationen überführen, ohne eine Kurve dem falschen Lüfter
  zuzuordnen — und die bereits bestehende Fehlzuordnung dabei auflösen.
- Verwaiste **hwmon-Generationen** deaktivieren statt sie unbegrenzt als
  `is_active` liegen zu lassen.

## Nicht-Ziele

- Kein Löschen von Zeilen. Deaktivieren genügt.
- Keine Aufräumarbeit an den `dev_*`-Zeilen. Sie fallen nicht unter Regel 1 und
  bleiben unberührt und aktiv — bewusst, weil ein Eingriff dort den Dev-Betrieb
  auf derselben Datenbank beschädigen könnte und der Nutzen kosmetisch ist.
  Das Ziel „verwaiste Generationen deaktivieren" bezieht sich auf
  hwmon-Generationen.
- Keine Erhaltung der Lüfter-Historie (`fan_sample`). **Wirkung explizit:**
  `get_history` filtert nach `fan_id` (`fan_control.py:854-877`) — der
  Verlaufsgraph ist nach der Umstellung für **alle** Lüfter schlagartig leer,
  nicht „beginnt neu". Alte Samples laufen über die bestehende Retention aus.
- Keine Änderung an Kurvenauswertung, Zeitplänen, Profilen oder Presets.

---

## 1. Identität und ihre Ableitung

### Gewählter Anker: der libsensors-Chipname

`sensors.conf(5)` definiert Chip-Namen als `<prefix>-<bus>-<adresse>`. Das ist
eine dokumentierte, außerhalb von BaluHost gültige Konvention, und sie ist auf
der Zielhardware bereits sichtbar — es sind exakt die Überschriften von `sensors`.

```
Lüfter:  nct6798-isa-0290:pwm1
Sensor:  hwmon:k10temp-pci-00c3:temp1
```

Der `hwmon:`-Präfix bei Sensoren bleibt, weil `fan_sources.py` die Namensräume
`hwmon:` / `gpu:` / `disk:` / `mix:` bereits so führt.

**Warum nicht der Gerätepfad (fancontrol-Stil).** `fancontrol` speichert
`DEVPATH`/`DEVNAME` aus `readlink -f /sys/class/hwmon/hwmonN/device`. Einfacher
zu bilden, aber bei PCI steckt die Bridge-Kette drin, und für NVMe enthält der
Pfad den Instanzindex `nvmeN` — selbst instabil, auf BaluNode sogar gekreuzt
(`hwmon0 → nvme1`, `hwmon1 → nvme0`).

**Warum keine Indirektionstabelle.** Eine `fan_identity`-Tabelle würde die
Datenmigration sparen, aber zwei Wahrheiten schaffen und das Aufräumproblem nur
verschieben.

### Ableitungsregeln

libsensors steigt **nicht** lexikalisch über `..` auf, sondern folgt dem
`device`-Symlink und klassifiziert auf jeder Ebene (`lib/sysfs.c`,
`find_bus_type` / `classify_device`). Es kennt neun Bustypen: `i2c`, `spi`,
`pci`, `platform`, `of_platform`, `acpi`, `hid`, `mdio_bus`, `scsi`, `sdio` — und
bricht beim **ersten klassifizierbaren** Elter ab, nicht beim ersten
pci-/platform-Elter.

Ableitung:

1. Startpunkt ist `realpath(/sys/class/hwmon/hwmonN/device)`. **Kein lexikalischer
   `Path.parent`/`dirname`** — `/sys/class/hwmon/hwmonN` ist ein Symlink, ein
   lexikalischer Aufstieg landet bei `/sys/class` und findet nie ein
   `subsystem`. Das Repo dokumentiert die Falle bereits in
   `fan_gpu_manual.py:101-127`.
2. Auf jeder Ebene das `subsystem`-Symlink auflösen und klassifizieren, dann
   aufwärts über den aufgelösten Pfad.
3. Unterstützt werden `pci` und `platform`/`of_platform`. Wird ein **anderer**
   bekannter Bustyp getroffen (`i2c`, `spi`, `scsi`, `hid`, `acpi`, `mdio_bus`,
   `sdio`), wird **sofort** in den instabilen Fallback gefallen — nicht
   weitergeklettert. Fehlt der `device`-Link ganz, ist der Chip virtuell,
   ebenfalls Fallback.
4. Präfix = Inhalt von `hwmon<N>/name`. Fehlt oder ist unlesbar (`"Unknown"`,
   `fan_backend_linux.py:390`), greift ebenfalls der Fallback.

**Warum Schritt 3 so scharf ist:** `drivetemp` (SATA-Plattentemperaturen, für ein
NAS hochrelevant) hängt am `scsi`-Bus. Ein Weiterklettern landete auf dem
AHCI-Controller und gäbe **allen Platten desselben Controllers dieselbe
Kennung**; `:tempN` unterscheidet sie nicht, jede hat `temp1`. Dasselbe gilt für
USB/HID-Lüftersteuerungen (`corsair-cpro`, `nzxt-*`, `aquacomputer_d5next`).
Weitere Bustypen zu unterstützen ist möglich, aber eigene Arbeit mit eigenen
Testdaten — nicht in diesem Scope.

### Adressbildung

Aus `lm-sensors 3.6.2`, `lib/sysfs.c`:

```c
/* PCI */
addr = (domain << 16) + (bus << 8) + (slot << 3) + fn;
/* platform / of_platform -> ISA */
if (sscanf(dev_name, "%*[a-zA-Z0-9_]%*1[.:]%d", &addr) == 1);
else if (sscanf(dev_name, "%x.%*s", &addr) == 1);
else addr = 0;
```

Zwei Details, die man sonst falsch rät: die PCI-Domain geht mit `<<16` **in** die
Adresse ein, und der Platform-Suffix wird **dezimal** gelesen (`nct6775.656` →
656 → als Hex ausgegeben `0290`).

**Formatierung** (`lib/data.c:sensors_snprintf_chip_name`): `"%s-isa-%04x"`,
`"%s-pci-%04x"`. `%04x` ist eine **Mindest**breite — bei PCI-Domain ≠ 0 sind es
fünf Hexziffern (`nvme-pci-10d00`). Wer auf vier Stellen abschneidet, baut eine
stille Kollision zwischen Domain 0 und Domain 1.

**Bewusste Abweichung beim Hex-Fallback.** libsensors' zweiter `sscanf` gibt
bereits `1` zurück, wenn `%x` etwas konsumiert hat, auch wenn der Literal-Punkt
danach nie matcht. Daraus werden `asus-nb-wmi` → `0x0a` und `eeepc-wmi` →
`0xeee` — stabil, aber bedeutungslos. Wir bilden stattdessen:

```
Regel A:  ^[A-Za-z0-9_-]+[.:](\d+)$   ->  addr = int(gruppe, 10)     # nct6775.656 -> 0290
Regel B:  ^([0-9a-f]+)\.               ->  addr = int(gruppe, 16)     # f0000000.hwmon (Device-Tree)
sonst:    Kennung = "<präfix>@<gerätename>"                           # asus@asus-nb-wmi
```

Regel B verlangt den Punkt tatsächlich und reproduziert damit den *gemeinten*
Device-Tree-Fall (relevant für die ARM-Box mit Rock Pi), nicht den Parser-Unfall.
Die Abweichung betrifft ausschließlich Chips, die `sensors` auf BaluNode
**überhaupt nicht listet** — die asus-WMI-Knoten erscheinen in der Ausgabe nicht,
haben keine PWM-Kanäle und sind für die Lüftersteuerung ohne Belang. Die
Verifikation „zeichengleich mit `sensors`" gilt entsprechend nur für Chips, die
`sensors` auch ausgibt.

### Eindeutigkeit

Der Chipname ist **nicht garantiert eindeutig**. Zwei Fälle:

- Zwei Geräte ohne numerischen Suffix → durch die `@`-Regel getrennt
  (Gerätenamen sind innerhalb ihres Busses eindeutig).
- **Zwei hwmon-Knoten am selben Gerät** (kernelseitig zulässig) → erzeugen
  dieselbe Kennung, und `_scan_pwm_fans` baut `new_cache` als Dict über `fan_id`
  (`fan_backend_linux.py:410`, `:441`): der zweite überschriebe den ersten
  **still**, ein Lüfter verschwände. Der `:pwmN`-Suffix hilft nicht, weil beide
  Knoten bei 1 zu zählen anfangen.

Deshalb: der Scan erkennt Duplikate der abgeleiteten Kennung und lässt **alle
betroffenen** Knoten in den instabilen Fallback fallen, mit WARNING. Lieber
ehrlich instabil als scheinstabil.

### Fallback

Betroffen sind: unbekannter/nicht unterstützter Bustyp, fehlender `device`-Link,
fehlender `name`, doppelte abgeleitete Kennung. In allen Fällen bleibt die
hwmon-indizierte Kennung stehen und wird als instabil markiert (Feld im
Fan-Cache, WARNING beim Scan). Kein Erfinden einer Pseudo-Identität.

Auf BaluNode betrifft das keinen für die Lüftersteuerung relevanten Chip; die
Aussage „Fan-IDs sind jetzt stabil" gilt trotzdem nicht unbedingt und ist so zu
dokumentieren.

---

## 2. Die Rückabbildung (fehlte in der ersten Fassung vollständig)

Der Scan muss eine Map **stabile Kennung → aktuelles hwmon-Verzeichnis**
mitführen. Ohne sie kann nach der Umstellung weder eine Temperatur gelesen noch
ein PWM geschrieben werden. Betroffene Stellen:

| Fundort | Problem |
|---|---|
| `fan_backend_linux.py:253-270` `get_temperature()` | `sensor_id.split("_")`, `if len(parts) != 2: return None`. `k10temp-pci-00c3:temp1` hat keinen Unterstrich → ein Element → `None`. **Jede** hwmon-Temperatur wäre `None` |
| `fan_backend_linux.py:272-309` `_find_cpu_temp_sensor()` | bildet Sensor-IDs aus dem hwmon-Verzeichnisnamen |
| `fan_control.py:336-342` `_make_hwmon_reader()` | legt jede `HwmonTempSource` genau auf `get_temperature` |
| `fan_control.py:676` `get_status()` | liest die Temperatur am Registry **vorbei** über `_backend.get_temperature`; scheitert das, fällt die Anzeige stumm auf den Scan-Sensor zurück und die UI zeigt für jeden Lüfter mit abweichendem Sensor die falsche Temperatur |
| `fan_sources.py:101-106` `_normalize_id()` | `if ":" in sensor_id: return sensor_id` — die neue nackte Form enthält selbst einen Doppelpunkt, wird nicht zu `hwmon:…` normalisiert, Registry-Miss |

Umsetzung: `_scan_pwm_fans` und `get_available_temp_sensors` legen die
aufgelösten Pfade in einen Cache; `get_temperature` löst darüber auf statt per
String-Zerlegung. `_normalize_id` bekommt eine echte Namespace-Whitelist
(`hwmon:`, `gpu:`, `disk:`, `mix:`) statt der `":" in`-Heuristik.

**Speicherform von `temp_sensor_id`: künftig präfixiert** (`hwmon:<chip>:<kanal>`).
Das ist die Form, die die API ohnehin ausgibt (`routes/fans.py:349`) und unter
der die Registry registriert (`fan_sources.py:43`). Der Default in
`_load_fan_configs` (`fan_control.py:279`, heute unpräfixiert) wird entsprechend
mitgezogen. Die Migration akzeptiert beide Altformen und streift ein optionales
`hwmon:` vor der Abbildung ab.

---

## 3. Datenmodell und Migration

### Warum Zuordnung über den hwmon-Index falsch ist

```
2026-07-20   hwmon2_pwm1   <- war damals der nct6798 (Gehäuselüfter)
heute        hwmon2        =  amdgpu (GPU)
```

Blindes Index-Mapping klebte eine Gehäuselüfter-Kurve auf den GPU-Lüfter — und
genau das ist über die `fan_id`-Gleichheit heute schon passiert (siehe Kontext).

### Der Schlüssel ist `fan_configs.name`

`name` wird genau einmal bei der Entdeckung gesetzt, als
`f"{hwmon_name_value} PWM{pwm_num}"`, und ist **nicht über die API änderbar**.
Beide Reviewer haben das unabhängig erschöpfend verifiziert: einziger
Schreibpfad ist die Neuanlage (`fan_control.py:271-282`);
`UpdateFanConfigRequest` hat kein `name`-Feld; `apply_preset`,
`update_fan_curve`, `set_fan_mode`, `set_fan_pwm` fassen es nicht an; keiner der
`setattr()`-Aufrufe im Backend zielt auf `FanConfig`.

Chip-Name = Teil von `name` vor dem letzten `" PWM"`. Enthält `name` kein
`" PWM"` (Dev-Backend erzeugt `"CPU Fan (Simulated)"` u. ä.), ist die Zeile kein
Kandidat — ein naives `rsplit(" PWM", 1)` gäbe sonst den ganzen Namen als
Chip-Namen zurück. Kanalnummer = `pwm<M>`-Teil der alten `fan_id`.

### Vorbedingungen — ohne die läuft der Abgleich nicht

Beide sind hart, weil ihr Fehlen einen Totalverlust bedeutet:

1. `self._use_linux_backend` ist wahr. `is_available()` gibt `False` zurück,
   sobald der Scan **0 PWM-Lüfter** findet, und `_initialize_backend` schaltet
   dann **auch in Produktion** auf `DevFanControlBackend`
   (`fan_backend_linux.py:51-65`, `fan_control.py:220-238`). Der Abgleich liefe
   dann gegen eine Chip-Menge ohne einen einzigen hwmon-Chip. Genau so sind die
   drei `dev_*`-Zeilen auf BaluNode entstanden.
2. Der Scan hat mindestens einen Chip geliefert.

### Zuordnungsregeln

1. Nur Zeilen der Form `^hwmon\d+_` werden angefasst. `dev_*`-Zeilen und bereits
   stabile IDs bleiben unberührt.
2. Kandidat ist eine Zeile, wenn der Chip-Name aus `name` heute **genau einen**
   Chip trifft und der Kanal auf diesem Chip existiert. Mehrere Treffer (zwei
   baugleiche Karten) → kein Kandidat; Raten wäre schlimmer als Nichtstun.
   `"Unknown …"`-Zeilen sind nie Kandidat.
3. Konkurrieren mehrere Zeilen um dieselbe neue ID, gewinnt die mit dem jüngsten
   `updated_at`. Die Konkurrenzmenge schließt eine **bereits in Neuform
   vorliegende** Zeile ein — sonst läuft ein nach einem Abbruch wiederholter Lauf
   in den Unique-Index. Die Rangfolge wird als Snapshot **vor** dem ersten
   Schreibzugriff festgehalten, weil `FanConfig.updated_at` ein
   `onupdate=func.now()` trägt (`models/fans.py:104-109`).
4. Deaktiviert wird **nur**, wessen Chip heute präsent ist und der entweder den
   Vergleich aus Regel 3 verloren hat oder dessen Kanal auf dem Chip fehlt.
   Zeilen, deren Chip heute **nicht** auftaucht, bleiben unangetastet und aktiv.
   Fallback-Zeilen (neue ID = alte ID) sind ein No-op, nie eine Deaktivierung.
5. Jede Übernahme als INFO-Zeile `alt → neu`, dazu eine Zusammenfassung und ein
   Audit-Eintrag über `get_audit_logger_db()` — der Lauf verändert
   Nutzerkonfiguration und gehört in die Revisionsspur.

**Regel 4 ist die Korrektur des schwersten Fehlers der ersten Fassung.** Dort
hieß es „alles Übrige `is_active=False`". Ist `nct6775` beim Dienststart noch
nicht geladen, wären alle vier Gehäuselüfter-Zeilen keine Kandidaten gewesen und
deaktiviert worden — `fan_control.py:478` (`if not config or not
config.is_active: continue`) schaltet die Regelung für sie ab, und beim
Nachladen legt `_load_fan_configs` Default-Configs an. Die Nutzerkurven wären
still weg gewesen: exakt der Schaden, den dieses Issue verhindern soll.

### Erwartetes Ergebnis auf BaluNode

| Neue ID | Quelle | |
|---|---|---|
| `nct6798-isa-0290:pwm1/2/3/7` | `hwmon3_pwm*` (2026-08-07) | aktiv |
| `amdgpu-pci-0300:pwm1` | `hwmon1_pwm1` (2026-07-06, `amdgpu PWM1`) | aktiv |

**5 aktiv, 8 inaktiv** (4× Januar `hwmon5_*`, 4× Juli `hwmon2_*`), 3 `dev_*`
unberührt, 0 Löschungen. Nebeneffekt: die heutige Fehlzuordnung des GPU-Lüfters
auf eine Gehäuselüfter-Config ist danach aufgelöst.

### Schema

Eine Alembic-Migration, **nur Struktur**, Elternrevision `c4b18e9a2f37`
(aktueller einziger Head; die Kette lautet
`dcabe4cc2ebc → 16ea14ef13bb → a7d3c9f18e42 → c4b18e9a2f37`). Explizit genannt,
weil das Projekt einen Multi-Head-Deployfehler in seiner Geschichte hat.

```
fan_configs        + legacy_fan_id     String(100) NULL
temp_sensor_labels + legacy_sensor_id  String(120) NULL
```

Keine Spaltenverbreiterung nötig — verifiziert: `fan_configs.fan_id`/`name`/
`temp_sensor_id` `String(100)`, `fan_schedule_entries.fan_id` `String(100)`,
`temp_sensor_labels.sensor_id` `String(120)`; längste neue ID 28 Zeichen.

### Ausführungsort, Reihenfolge, Nebenläufigkeit

Der Abgleich läuft **beim Dienststart in `_load_fan_configs`, vor der
Anlage-Schleife, in derselben Transaktion**. Eine Migration, die sysfs der
Zielmaschine liest, verhielte sich in CI, auf einem Dev-Rechner und bei einem
DB-Restore jeweils anders.

Nebenläufigkeit ist der zweite schwere Fehler der ersten Fassung. Tatsächlicher
Ist-Zustand:

- `start()` ruft `_load_fan_configs()` **vor** dem `if monitoring:`-Gate auf
  (`fan_control.py:199`) — also in **allen vier Workern**. Der `monitoring`-
  Schalter steuert nur die Loop.
- `_load_fan_configs` legt für jeden gescannten Lüfter ohne Config eine
  Default-Zeile an (`fan_control.py:265-284`). Ein Sekundär-Worker, der zuerst
  durchläuft, belegt damit die neuen Ziel-IDs; der Primary läuft beim
  `UPDATE fan_id` in den UNIQUE-Index (`models/fans.py:76`). Die `IntegrityError`
  fliegt aus `start()` und wird in `lifespan.py:531-532` nur als Warning
  geschluckt — Fan-Control startet auf dem Primary gar nicht.
- `start_fan_control` ist zusätzlich über `service_registry.py:208` aus
  `restart_service` (`services/service_status.py:233-292`, Route
  `routes/service_status.py:91-118`) und über `switch_backend()`
  (`fan_control.py:879-904`) erreichbar — beides aus einem HTTP-Request in einem
  **beliebigen** Worker.

Daraus folgt:

- Der Primary-Gate liegt **im Abgleich selbst**, nicht im Startpfad — sonst
  umgehen ihn `restart_service` und `switch_backend`.
- Gelesen wird `lifespan.IS_PRIMARY_WORKER` als Attributzugriff. Ein
  `from app.core.lifespan import IS_PRIMARY_WORKER` friert den Importwert `False`
  ein und der Abgleich liefe **nie**. Einziges funktionierendes Muster im Repo:
  `plugin_enablement.py:191`.
- Die Neuanlage wird ebenfalls serialisiert (Primary-only oder
  `ON CONFLICT DO NOTHING` mit Re-Select). Regel 1 allein genügt **nicht** als
  Schutz: die konkurrierende Zeile entsteht in *Neuform* und ist für Regel 1
  unsichtbar.
- Ist die Ziel-ID trotz allem belegt, wird der Verlierer deaktiviert statt in die
  `IntegrityError` zu laufen.

Mitzuziehen mit derselben Abbildung: `fan_configs.sync_fan_id`,
`fan_schedule_entries.fan_id`.

### Sensor-IDs: die schwächere Stelle

Für Sensoren gibt es kein Gegenstück zu `name`. Sensor-IDs werden über den
**heutigen Index** aufgelöst; löst er nicht auf, fällt der Lüfter auf den
CPU-Sensor-Default zurück. Beide Fälle als WARNING, nicht still. Fehlerbild:
„der Lüfter folgt dem falschen Sensor" — sichtbar und mit einem Klick
korrigierbar.

`composite_temp_sensors.source_ids_json` wird mit derselben Abbildung
umgeschrieben (auf BaluNode leer).

`temp_sensor_labels.sensor_id` ist Primärschlüssel ohne `is_active`-Spalte.
Kollidieren zwei Altzeilen auf denselben neuen Schlüssel, gewinnt die jüngste;
die verworfene **bleibt unter ihrem alten Schlüssel liegen** und wird ignoriert.
Kein Löschen (Nicht-Ziel), keine neue Spalte.

Eine Chip-Namensspalte für `temp_sensor_labels` wurde erwogen und verworfen: sie
hülfe nur künftigen Index-Migrationen, die es nach dieser Umstellung per
Konstruktion nicht mehr gibt.

---

## 4. Auflösung zur Laufzeit

Der Scan in `_scan_pwm_fans` bildet die neue Form direkt; `_fan_cache` ist auf
stabile Schlüssel umgestellt. Nebeneffekt: der Write-Backoff aus #533 überlebt
ein Renumbering — heute verliert er seinen Eintrag, weil der Schlüssel wechselt
(`fan_backend_linux.py:458`).

**Abwesenheit darf niemals schreiben.**

- Lüfter im Scan, ohne Config → Config mit Defaults anlegen (heutiges Verhalten).
- Config ohne Lüfter im Scan → nichts tun. Kein `is_active=False`, kein Löschen,
  keine Neuanlage. Deckungsgleich mit Regel 4 aus Abschnitt 3.

Der `„found 0 fans, keeping cached fans"`-Schutz in `_scan_pwm_fans`
(`fan_backend_linux.py:454-464`) greift **nur bei null** gefundenen Lüftern und
deckt den Teilfall (amdgpu da, nct6775 noch nicht) *nicht* ab — die Aussage der
ersten Fassung, er decke „denselben Gedanken eine Ebene tiefer" ab, war falsch.
Der Schutz liegt allein in Regel 4.

**Es gibt keinen periodischen Rescan.** `_scan_pwm_fans` läuft nur über
`is_available()` beim Start und in `switch_backend`. Ein später geladener Treiber
bleibt bis zum Neustart unsichtbar — das bestimmt die Halbwertszeit des Zustands
„Lüfter fehlt" und ist ein bestehender Zustand, den diese Arbeit nicht ändert.

**Akzeptanzkriterium:** Ein Reboot, der `nct6798` von `hwmon3` nach `hwmon5`
verschiebt, verändert `nct6798-isa-0290:pwm1` nicht. Keine neue Config, die Kurve
gilt weiter, keine neue Generation.

---

## 5. API, Frontend, Konsumenten

**Das Frontend braucht keine funktionale Änderung.** Unabhängig von beiden
Reviewern verifiziert: keine Stelle in `client/src/` zerlegt `fan_id`/`fanId`,
keine legt eine Lüfterauswahl in `localStorage` ab, keine Router-/URL-Parameter,
React-Query-Keys ohne fan_id (`hooks/useFanControl.ts:37`), E2E-Fixture
`MOCK_FAN_STATUS = { fans: [] }`.

Eine Ausnahme: `client/src/components/fan-control/FanCard.tsx:9` baut
`` `hwmon:${sensorId}` `` und setzt damit eine Formatannahme über Sensor-IDs
voraus. Funktioniert nach der Umstellung weiter, gehört aber auf die
Mitzuziehen-Liste.

**Pfadparameter** tragen die neue Form ohne Arbeit: der Client kodiert mit
`encodeURIComponent` (`api/fan-control.ts`, neun Stellen), uvicorn entquotet vor
dem Routing, und die Sensor-Label-Routen transportieren `hwmon:…` bereits
produktiv. Weder `fan_id` noch `sensor_id` noch `sync_fan_id` haben ein
`pattern=` in den Pydantic-Schemas.

**Keine weitere Spalte speichert eine Fan- oder Sensor-ID.** Repo-weit
verifiziert: Notifications tragen nur `action_url="/fans"`, die Status-Bar liest
nur `fan["name"]`, Monitoring speichert nur `fan_rpm`, Scheduler/Presets/
Profile/Audit-Logs führen keine fan_id. Die TUI (`backend/baluhost_tui/`) hat
null Treffer für „fan" oder „hwmon" und ist kein Konsument.

**Mitzuziehen:** zehn Swagger-Beispiele in `backend/app/schemas/fans.py`
(Z. 88, 122, 132, 172, 194, 233, 346, 392, 394, 413).

**Kein API-Versionssprung.** Die ID war nie ein dokumentiertes Format. Ein Client
mit zwischengespeicherter Fan-ID bekommt eine 404 und lädt neu.

**Restore:** `fan_configs` steckt im DB-Backup
(`services/backup/service.py:30`). Das Zurückspielen eines
Vor-Umstellungs-Backups bringt Altzeilen zurück; der Abgleich läuft nur beim
Dienststart — **nach einem Restore ist ein Neustart erforderlich.**

---

## 6. Tests und Verifikation

### Der Test, der das Issue beantwortet

Ein hwmon-Baum unter `tmp_path`, zweimal aufgebaut: derselbe Gerätepfad einmal
als `hwmon3`, einmal als `hwmon5`. Erwartung: identische Kennung, und
`_load_fan_configs` legt beim zweiten Durchlauf keine neue Zeile an.

**Der Testbaum muss echte `device`- und `subsystem`-Symlinks enthalten.** Sonst
läuft er in den Fallback und prüft die neue Ableitung gerade nicht. Das betrifft
auch drei bestehende Dateien, die synthetische Bäume ohne Elternstruktur bauen —
`test_fan_pwm_control_probe.py` (35 hwmon-Vorkommen),
`test_fan_gpu_manual_mode.py` (17), `test_fan_einval_diagnostic.py` (15): sie
würden nach der Umstellung stillschweigend den Fallback testen und grün bleiben,
ohne die Umstellung abzudecken.

### Kodierung gegen echte Pfade

Sollwerte sind die von `sensors` auf BaluNode gemeldeten Chip-Namen — eine
unabhängige Implementierung derselben Regeln auf derselben Hardware:

| Gerätepfad | erwartete Kennung |
|---|---|
| `platform/nct6775.656` | `nct6798-isa-0290` |
| `pci…/0000:03:00.0` | `amdgpu-pci-0300` |
| `pci0000:00/0000:00:18.3` | `k10temp-pci-00c3` |
| `…/0000:0d:00.0/nvme/nvme1` | `nvme-pci-0d00` |
| `…/0000:0a:00.0/nvme/nvme0` | `nvme-pci-0a00` |

Ergänzend, ohne `sensors`-Sollwert (die Chips erscheinen dort nicht):
`platform/asus-nb-wmi` → `asus@asus-nb-wmi`, `platform/eeepc-wmi` →
`asus@eeepc-wmi`. Dazu je ein Fall für PCI-Domain ≠ 0 (fünf Hexziffern), einen
`scsi`-Elter (→ Fallback), einen fehlenden `device`-Link (→ Fallback) und zwei
hwmon-Knoten am selben Gerät (→ beide Fallback, WARNING).

### Reconciliation

Fixture ist die echte Datenlage (16 Zeilen, oben vollständig abgedruckt).

- Erwartung: **5 aktiv, 8 inaktiv, 3 `dev_*` unberührt, 0 Löschungen.**
- Die Falle: `hwmon2_pwm1` mit `name="nct6798 PWM1"` darf **nicht** dem heutigen
  `hwmon2` (amdgpu) zugeordnet werden, sondern muss gegen die August-Generation
  des nct6798 verlieren.
- `hwmon1_pwm1` mit `name="amdgpu PWM1"` gewinnt `amdgpu-pci-0300:pwm1`.
- Chip nicht präsent (Treiber nicht geladen) → **keine** Deaktivierung.
- Dev-Backend aktiv → Abgleich läuft gar nicht.
- Zweiter Lauf folgenlos, auch nach Abbruch zwischen Umbenennung und
  Deaktivierung.
- `"Unknown PWM1"` → weder Kandidat noch Deaktivierung.
- Zwei Sekundär-Worker parallel → keine `IntegrityError`.

### Gates

`pytest -k "fan or power"` steht seit #539 bei 559 passed — Messlatte plus die
neuen Tests. Dazu `ruff check`, `eslint .`, `npm run build`, `vitest run`. Die
volle Backend-Suite bleibt der CI überlassen (hängt auf Windows).

Mitzuziehen: 74 hwmon-ID-Literale in 8 Backend-Testdateien und 4
Frontend-Testdateien.

### Feldverifikation nach dem Deploy

1. Abgeleitete Kennungen gegen die `sensors`-Überschriften vergleichen — für die
   fünf dort gelisteten Chips zeichengleich.
2. `SELECT count(*) FROM fan_configs WHERE is_active` vor und nach dem ersten
   Start: 16 → 8 (5 neue + 3 `dev_*`).
3. `modprobe -r nct6775 ; modprobe nct6775` erzwingt ein Renumbering ohne Reboot.
   Danach muss `fan_configs` gleich viele Zeilen haben wie davor.

Zu Schritt 3: beim Entladen verliert BaluHost kurzzeitig die Lüfter, und
`pwm_enable` fällt auf den Board-Default zurück. Bei Leerlauftemperaturen
ungefährlich, aber ein Eingriff — ein regulärer Reboot leistet dasselbe.

---

## Risiken

- **Selbstgebaute Kodierung.** Aus dem libsensors-Quelltext übernommen, nicht aus
  Beobachtungen zurückgeschlossen — mit einer dokumentierten bewussten Abweichung
  beim Hex-Fallback. Für Bustypen jenseits `pci`/`platform` gibt es auf dieser
  Hardware keine Testdaten; sie fallen deshalb in den ehrlichen Fallback.
- **i2c-Busnummern sind laut lm-sensors selbst nicht reboot-stabil.** Auf
  BaluNode ist alles `isa` oder `pci`; die Kennung darf sich nicht darauf
  verlassen, dass das so bleibt — deshalb Fallback statt Rateversuch.
- **Sensor-Zuordnung bleibt heuristisch.** Fehlerbild ist ein falscher Sensor am
  Lüfter, sichtbar und korrigierbar, nicht stumm.
- **`is_active=False` ist keine Buchhaltung, sondern eine Funktionsabschaltung**
  (`fan_control.py:478` überspringt inaktive Configs in der Regelschleife). Das
  bestimmt die Kosten eines Fehlurteils in Regel 4 und ist der Grund für die
  beiden harten Vorbedingungen.
- **Einmaliger Vorgang mit Datenwirkung** auf produktiven Zeilen. Absicherung:
  nichts wird gelöscht, `legacy_fan_id` hält die Herkunft fest, jede Übernahme
  wird geloggt und auditiert.

## Quellen

- [sensors.conf(5)](https://manpages.debian.org/testing/lm-sensors/sensors.conf.5.en.html)
- [lm-sensors `lib/sysfs.c`](https://github.com/lm-sensors/lm-sensors/blob/master/lib/sysfs.c)
  — `find_bus_type`, `classify_device`, Adressbildung
- [fancontrol(8)](https://www.systutorials.com/docs/linux/man/8-fancontrol/) —
  `DEVPATH`/`DEVNAME`: Drift erkennen statt automatisch zuordnen
- [lm-sensors#227](https://github.com/lm-sensors/lm-sensors/issues/227)
- [Fan speed control — ArchWiki](https://wiki.archlinux.org/title/Fan_speed_control)
