# Rückweg für Lüfterkennungen: stabil → hwmon-indiziert (#585)

Entwurf vom 2026-09-08. Spiegelt den Hinweg aus #532, der bisher nur in eine Richtung läuft.

## Ausgangslage

#532 überführt hwmon-indizierte `fan_configs` auf stabile Kennungen (`nct6798-isa-0290:pwm1`). Bei einer Kollision gewinnt die jüngste Zeile, die Verliererinnen werden auf `is_active = False` gesetzt und bleiben liegen — Löschen ist dort ausdrückliches Nicht-Ziel.

Der umgekehrte Fall hat keinen Weg. `build_fan_id()` fällt auf `hwmon<N>_pwm<M>` zurück, sobald `derive_chip_identity()` keine stabile Kennung bilden kann: `hwmon/name` unlesbar, kein `device`-Symlink, nicht bildbarer Bustyp (`i2c`, `scsi`, …), kein pci/platform-Elter, oder zwei hwmon-Knoten mit derselben Kennung (`derive_all` markiert beide als instabil).

Feldstand BaluNode am 2026-09-07 — drei Generationen für dieselben vier Kanäle:

```
nct6798-isa-0290:pwm1..7  is_active=t   legacy_fan_id=hwmon3_pwm*
hwmon2_pwm1..7            is_active=f   legacy_fan_id=(leer)
hwmon5_pwm1..7            is_active=f   legacy_fan_id=(leer)
```

## Was heute passierte, wenn der Rückfall greift

Der Scan liefert `hwmon2_pwm1`. Dann:

1. Die Anlage-Schleife findet die Zeile vor (`fan_control.py:857-860`, `if not existing`) und legt keine neue an.
2. Die vorgefundene Zeile trägt `is_active = False`. `is_active = True` wird im ganzen Dienst nur beim Anlegen gesetzt (`fan_control.py:875`); `routes/fans.py` kennt das Feld nicht — es gibt keinen Weg zurück.
3. Der Regelkreis steigt bei `not config.is_active` aus (`fan_control.py:1160`).
4. `get_status` filtert inaktive Lüfter nicht (`fan_control.py:1544`), und kein Frontend-Bauteil liest das Feld. Die Karte sieht normal aus, mit Modusknöpfen und Kurveneditor — und nichts davon wirkt.

Ein Lüfter, um den sich niemand kümmert, ohne eine einzige Logzeile. Landete der Index auf einer Nummer ohne Altzeile, entstünde stattdessen eine frische Zeile mit Standardkurve: geregelt, aber die getunte Konfiguration wäre still verwaist.

## Die Verschärfung durch #580

Seit #534 Punkt 2 gibt BaluHost einen Kanal an die Board-Automatik ab, wenn seine Temperaturquelle 300 s keinen Messwert liefert. `build_sensor_id()` fällt gemeinsam mit `build_fan_id()` zurück — die Zeile zeigt danach auf `hwmon:nct6798-isa-0290:temp6`, während der Scan nur noch `hwmon:hwmon2_temp6` kennt. `get_temp()` liefert `None`.

Der Rückweg muss die Sensoren also mitnehmen. Täte er es nicht, wäre das Ergebnis nicht bloß eine falsche Kennung, sondern ein Lüfter, den BaluHost fünf Minuten später an das Board abgibt.

## Der Anker

Eine instabile `ChipIdentity` trägt weiterhin ihren `prefix` — den Inhalt von `hwmon/name`, also `nct6798`. Und jede stabile Kennung beginnt mit genau diesem Präfix: `format_chip_name()` bildet `<prefix>-<bus>-<addr>`, der adresslose Zweig `<prefix>@<devname>`.

Damit ist die Zuordnung: **ein instabiler Kanal (`prefix`, `pwm_num`) gehört zu der Zeile, deren `fan_id` die Form `<prefix>[-@]…:pwm<pwm_num>` hat.** Für Sensoren dasselbe mit `:temp<K>`.

Der Name der Zeile (`"nct6798 PWM1"`, den der Hinweg über `_chip_from_name()` auswertet) wird hier nicht gebraucht: die stabile `fan_id` enthält den Chipnamen selbst und ist der festere Anker.

## Wachen

Jede einzelne blockiert die Zuordnung — im Zweifel geschieht nichts, denn ein falsch zugeordneter Lüfter ist schlimmer als ein unzugeordneter:

| Wache | Grund |
|---|---|
| `prefix` fehlt oder ist `"Unknown"` | `hwmon/name` war unlesbar; „Unknown" wäre über Chips hinweg mehrdeutig |
| mehr als eine Kandidatenzeile | zwei Chips desselben Präfix — dieselbe Regel, mit der `derive_all` Duplikate für instabil erklärt |
| mehr als ein instabiler Chip mit demselben Präfix im Scan | die Indizes zweier gleicher Chips können über Boots tauschen |

## Wirkung

Bei genau einem Kandidaten gilt dieselbe Mechanik wie auf dem Hinweg, unverändert übernommen:

1. Gewinnerin ist die jüngste Zeile (`updated_at`) aus Kandidat und einer etwaigen Zeile, die die aktuelle Kennung schon trägt — auf BaluNode also die stabile Zeile gegen die 2026-09-05 deaktivierte.
2. Eine Inkumbentin auf der Zielkennung wird zuerst freigemacht (`fan_id = f"{ziel}#legacy{row.id}"`), dann `db.flush()`, dann die Umbenennung — die Reihenfolge-Falle I-2 aus #532 gilt hier genauso.
3. `legacy_fan_id` nimmt die alte Kennung auf, `_rewrite_references()` zieht `sync_fan_id` und Zeitplaneinträge mit.
4. Verliererinnen werden deaktiviert.
5. `temp_sensor_id` der Gewinnerin wird über die Präfix-Abbildung auf die aktuelle Sensorkennung umgeschrieben.

Nutzer-Labels und Composite-Quellen ziehen mit derselben Abbildung mit. Bei Labels ist das Kosmetik, bei Composites nicht: eine Quelle, die niemand mehr auflöst, endet in derselben Abgabe nach 300 s wie ein direkt zugewiesener Sensor. Kollisionen werden wie auf dem Hinweg behandelt — die vorhandene Zeile bleibt stehen, die umzuschlüsselnde wird ignoriert, gelöscht wird nichts.

Erholt sich die Ableitung später wieder, greift der Hinweg aus #532 und führt die Zeile zurück auf die stabile Kennung. Die beiden Wege sind zueinander invers; `legacy_fan_id` trägt jeweils die zuletzt verlassene Form.

## Die Vorbedingung muss sich ändern

`_should_reconcile()` verlangt heute `chip_count > 0`, und `_collect_chip_facts()` überspringt instabile Chips. Fällt die Ableitung für **alle** Chips zurück, ist die Faktenmenge leer und es läuft gar kein Abgleich — ausgerechnet im Vollfall. Die Vorbedingung zählt künftig stabile Chips **und** instabile Kanäle; „kein Linux-Backend" und „leerer Scan" bleiben harte Ausschlüsse.

## Der Rest, der keine Zuordnung findet

Findet sich kein Kandidat und die vorgefundene Zeile ist inaktiv, bleibt der Lüfter ungeregelt — daran ändert dieser Entwurf nichts. Aber er wird **hörbar**: eine WARNING mit Kennung und Grund. Das ist die Variante A aus #585, hier als Restfall enthalten statt als Alternative.

## Nicht-Ziele

- **Zeilen löschen.** Nicht-Ziel schon in #532; hier unverändert.
- **Reaktivieren ohne Identitätsnachweis.** Eine inaktive Zeile, zu der kein Kandidat passt, bleibt inaktiv. Sie wurde einmal bewusst zugunsten einer anderen deaktiviert, und ohne Zuordnung gibt es keinen Grund anzunehmen, dass sich das geändert hat.
- **Ein Bedienelement für `is_active`.** Dass es keines gibt, ist die Voraussetzung dafür, dass dieser Entwurf keine Nutzerentscheidung überschreibt. Käme eines dazu, müsste die Reaktivierung neu bewertet werden — als Kommentar im Code festgehalten.
