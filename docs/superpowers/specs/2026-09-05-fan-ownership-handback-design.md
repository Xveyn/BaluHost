# Regelung an die Board-Automatik zurückgeben

**Status:** Design freigegeben (2026-09-05)
**Issue:** #534
**Branch:** `feat/fan-ownership-handback-534` (von `main`)
**Voraussetzung:** #517/#480 (PR #537), #533 (PR #539) und #532 (PR #550) sind gemergt.

## Kontext

BaluHost nimmt die Kontrolle über jeden schreibbaren Lüfter und gibt sie nie
zurück. Es gibt dadurch Zustände, in denen *niemand* regelt: BaluHost regelt
nicht mehr (oder falsch), und die Board-Automatik ist abgeschaltet.

### Was der Ist-Zustand tatsächlich ist

Der Issue-Text nimmt an, `pwm_enable` werde einmal beim Start auf `1` gesetzt.
Das stimmt nicht: **`set_pwm` schreibt `pwm_enable=1` bei jedem einzelnen
PWM-Write** (`fan_backend_linux.py:183`). BaluHost übernimmt die Kontrolle also
alle fünf Sekunden neu.

Der Ursprungswert wird nirgends gesichert. Der Scan legt `pwm_enable_path` ab,
liest den Wert aber nicht. Ein Muster für Sicherung und Rückgabe existiert im
Repo — `AmdManualState` in `fan_gpu_manual.py:23-52` — allerdings nur für den
AMD-Pfad.

Ein Aufhängepunkt für den Shutdown ist vorhanden: `_shutdown()`
(`lifespan.py:757`) ruft `fan_control.stop_fan_control()` bereits
primary-gegated auf. `stop()` bricht dort heute nur die Monitoring-Task ab.

### Die Prämisse ist gemessen, nicht angenommen

Auf BaluNode (2026-09-05), Kanal 1 des nct6798, Dienst gestoppt:

| | `pwm1_enable` | `pwm1` | RPM |
|---|---|---|---|
| BaluHost regelt | 1 | 76 | — |
| nach `echo 5` | 5 | **87** | 508 |
| nach Dienststart | 1 | 87 | — |

`pwm1` wanderte ohne fremden Schreibzugriff von 76 auf 87 — der Chip hat die
Regelung übernommen. Smart Fan IV greift also wirklich. Der letzte Schritt
zeigt zugleich, dass BaluHost sich den Kanal binnen Sekunden von selbst
zurückholt, weil `set_pwm` `pwm_enable=1` mitschreibt.

### Was der frühere Aufhänger des Issues war

Die ursprüngliche Messung im Issue („alle vier Lüfter fest auf `pwm=128`, keine
Temperaturregelung im Gehäuse") ist überholt. Ursache war #517; seit dessen
Deploy regelt die Kurve nachweislich. Übrig bleibt die Regelungslücke beim
Dienst-Ende und bei ausgefallener oder unmöglicher Regelung.

## Ziele

- Beim Dienst-Ende die Kontrolle an die Board-Automatik zurückgeben.
- Einen Lüfter, dessen Schreibversuche strukturell scheitern, an die Automatik
  zurückgeben statt ihn weiter erfolglos zu beschreiben.
- Einen Lüfter, für den kein Zielwert mehr gebildet werden kann, an die
  Automatik zurückgeben statt den letzten Wert einzufrieren.

## Nicht-Ziele

- Keine Bedienoberfläche für den Rückgabewert. Er stammt aus der Sicherung oder
  dem Treiber-Fallback.
- Keine Rückgabe auf Hardware, für die kein Rückgabewert bekannt ist.
- Keine Änderung am Notfallpfad, an der Kurvenauswertung oder am Backoff aus
  #533 — der Backoff wird nur als Auslöser gelesen.

### Die Grenze, die keine Lösung beseitigt

Bei `SIGKILL` gibt es keine Rückgabe. `systemctl stop` und der Deploy-Neustart
senden `SIGTERM`, dort greift der Shutdown-Pfad. Ein hartes Kill oder ein
Stromausfall hinterlässt die Lüfter auf dem letzten Wert — das ist der heutige
Zustand und im Prozess selbst nicht behebbar.

---

## 1. Das Besitz-Modell

Ein Lüfter ist entweder in BaluHosts Hand oder freigegeben. Der Regelkreis
fragt einmal pro Zyklus; ein freigegebener Lüfter wird übersprungen, `set_pwm`
läuft für ihn also gar nicht erst und schreibt folglich kein `pwm_enable=1`.
Die Rückgabe braucht damit **keinen Sonderfall im Schreibpfad**.

### Besitz entsteht mit dem erfolgreichen `pwm_enable=1`

Nicht durch den Scan, und **nicht** durch den erfolgreichen PWM-Wert-Write.
`set_pwm` schreibt erst `pwm_enable=1`, dann den Wert (`fan_backend_linux.py:182-190`).
Genau der erste Schritt *ist* die Übernahme — er schaltet die Board-Automatik ab.

Der Unterschied ist nicht akademisch. Gelingt `pwm_enable=1` und scheitert der
Wert-Write (etwa `EINVAL` auf einem Knoten, der den Modus annimmt aber keinen
Wert), hat BaluHost die Automatik abgeschaltet, ohne selbst regeln zu können —
der schlimmste erreichbare Zustand. Genau dieser Lüfter muss zurückgegeben
werden können, und mit „Besitz = erfolgreicher Wert-Write" wäre er davon
ausgenommen gewesen.

Scheitert schon `pwm_enable=1`, wurde nie übernommen: dann wird bei der
Freigabe **kein** Rückgabe-Write versucht, der Lüfter aber trotzdem als
freigegeben markiert, damit der Regelkreis aufhört, ihn zu beschreiben.

Sekundär-Worker laufen mit `monitoring=False` und rufen `set_pwm` nie auf. Ihr
Besitz-Zustand bleibt leer, und wenn uvicorn einen Sekundär-Worker neu startet,
gibt dessen `stop()` nichts zurück. Andernfalls übergäbe er den Lüfter ans
Board, während der Primary noch regelt.

### Drei Freigabegründe

| Grund | Auslöser | Rückweg |
|---|---|---|
| `shutdown` | Dienst-Ende | kein Laufzeitzustand — der Prozess endet |
| `not_controllable` | Backoff aus #533 hat den 15-Minuten-Deckel erreicht | **klebrig** — bis Neustart oder Nutzer-Klick |
| `no_target` | 12 Zyklen ohne gültigen Temperaturwert | **selbstheilend** — sobald wieder ein Wert kommt |

Der Nutzer-Klick braucht keinen neuen Mechanismus: `set_fan_pwm()` geht seit
#533 über `force=True`, und Besitz entsteht durch einen erfolgreichen
`set_pwm` — wer klickt, nimmt den Lüfter damit zurück.

### Der GPU-Fall bleibt draußen

`set_pwm` steigt bei `FIRMWARE_MANAGED` als Erstes aus (#480), bevor
`pwm_enable` angefasst wird; auf BaluNode steht `hwmon2/pwm1_enable` deshalb
unverändert auf `2`. Der Mechanismus zielt auf den generischen hwmon-Pfad.

### Wo der Zustand liegt

Neues Modul `backend/app/services/power/fan_ownership.py`, prozesslokal,
`fan_id → Freigabe(grund, zeitpunkt)`. Kein DB-Feld: die Regelung läuft ohnehin
nur im Primary-Worker, und ein persistierter „freigegeben"-Zustand arbeitete
gegen die gewünschte Selbstheilung nach einem Neustart. Der Preis ist eine
Backoff-Periode pro Neustart, und die ist nach #533 gedeckelt.

Die Rückgabe wird **einmal** geschrieben, nicht wiederholt — es schreibt
danach niemand mehr dagegen.

---

## 2. Der Rückgabewert

Gesichert wird **beim Scan**, in `_scan_pwm_fans`, bevor irgendein `set_pwm`
gelaufen ist. Das ist der einzige Moment, in dem der Wert echt sein kann: nach
einem Kaltstart steht dort, was das BIOS gesetzt hat.

**Eine `1` ist nie ein gültiges Ziel.** Sie bedeutet Handsteuerung, und die
kann kein Board von sich aus wollen — sie ist der Beweis, dass schon jemand
übernommen hat.

### Persistenz

Neue Spalte `fan_configs.pwm_enable_restore` (Integer, nullable). Nötig, weil
die Sicherung nur nach einem Kaltstart stimmt: nach einem `SIGKILL` hinterlässt
die Vorgängerinstanz eine `1`, und ohne gespeicherten Wert wäre der echte
Ursprungswert dauerhaft verloren. Dass die Spalte an einer stabilen `fan_id`
hängt, ist das Ergebnis von #532.

Die Spalte braucht eine Alembic-Migration. **Die Elternrevision ist zum
Zeitpunkt der Umsetzung frisch über `alembic heads` zu prüfen**, nicht aus
diesem Dokument zu übernehmen — das Projekt hatte einen Deploy-Fehler durch
mehrere Heads.

### Die Auflösungsregel

```
gelesener Wert != 1   ->  als Ziel benutzen UND persistieren
gelesener Wert == 1   ->  gespeicherten Wert benutzen, falls vorhanden
                          sonst Treiber-Fallback benutzen, NICHT speichern
kein Fallback bekannt ->  nicht zurueckgeben, WARNING mit Treibernamen
```

**Der Fallback wird benutzt, aber nie gespeichert.** Ohne diese Einschränkung
wäre eine falsch geratene Annahme selbsterhaltend: wir schrieben `5`, läsen
beim nächsten Start `5`, speicherten `5` — und der echte Board-Wert käme nie
mehr zum Zug. So bleibt der Platz für eine echte Beobachtung dauerhaft offen.

### Der Fallback, als Annahme dokumentiert

| Treiber | Wert | Belegt durch |
|---|---|---|
| `nct6775` (deckt nct6798 ab) | `5` — Smart Fan IV | Messung oben: `pwm1` 76 → 87, 508 RPM |
| `amdgpu` | `2` — Auto | Ist-Zustand auf BaluNode; derselbe Wert, den `disable_amd_manual` zurückschreibt |
| alles andere | keiner | keine Rückgabe, WARNING |

Dass für unbekannte Treiber **nichts** passiert, ist Absicht: ein geratener
Modus auf fremder Hardware ist schlechter als der heutige Zustand, und der
heutige Zustand ist bekannt.

Fehlt `pwm_enable_path`, gibt es weder Übernahme noch Rückgabe.

---

## 3. Die drei Auslöser

### Dienst-Ende

In `stop()`, **nachdem** die Monitoring-Task abgebrochen ist — erst die
Schleife stilllegen, damit sie nicht gegen die Rückgabe schreibt, dann alle
besessenen Lüfter zurückgeben. `_shutdown()` ruft `stop_fan_control()` bereits
primary-gegated auf; der leere Besitz-Zustand auf Sekundär-Workern sichert das
doppelt ab.

### Nicht steuerbar

Aufhänger ist der Backoff aus #533. Die Bedingung ist **„das Fenster liegt
erstmals am Deckel"**, nicht eine feste Fehlerzahl — mit den heutigen Konstanten
(`PWM_BACKOFF_BASE_SECONDS = 10`, Verdopplung, `PWM_BACKOFF_MAX_SECONDS = 900`)
ist das der achte aufeinanderfolgende Fehlschlag (10, 20, 40, 80, 160, 320, 640,
dann gedeckelt). Die Bedingung wird gegen den Deckel formuliert, damit eine
spätere Änderung der Konstanten sie nicht still verschiebt.

An diesem Punkt sind die Schreibversuche strukturell gescheitert und nicht bloß
kurz gestört. Dann Rückgabe, `not_controllable`, **eine** ERROR-Zeile — die
Log-Hygiene aus #533 gilt hier genauso.

**Scheitern PWM-Writes, scheitert das Zurückschreiben von `pwm_enable` sehr
wahrscheinlich auch** — derselbe Knoten, dieselben Rechte, derselbe Treiber.
Die Rückgabe wird versucht und ihr Ergebnis geloggt, aber der Lüfter gilt
danach **in jedem Fall** als freigegeben. Wir geben unseren Anspruch auf, auch
wenn wir den Board-Modus nicht wiederherstellen können; weiter alle fünf
Sekunden erfolglos zu schreiben ist eindeutig schlechter.

### Regelung ausgefallen

Liefert die Sensorauflösung über **zwölf** aufeinanderfolgende Zyklen keinen
Wert — bei 5-Sekunden-Takt eine Minute —, wird zurückgegeben mit `no_target`.
Ein oder zwei ausgefallene Messungen sind Rauschen; eine Minute ohne
verwertbare Temperatur heißt, dass die Quelle weg ist.

Kommt wieder ein Wert, übernimmt BaluHost beim nächsten Zyklus von selbst: der
Regelkreis hört auf zu überspringen, und der nächste `set_pwm` schreibt
`pwm_enable=1` mit. Das ersetzt das heutige Einfrieren des letzten Werts.

### Der Notfallpfad bleibt unangetastet

Er greift bei `Temperatur >= emergency_temp_celsius` und schreibt mit
`force=True` volle Leistung. Beide Freigabegründe machen ihn gegenstandslos,
statt ihn zu behindern:

- Bei `no_target` gibt es keine Temperatur, also keinen Notfall — und das Board
  regelt inzwischen selbst. Auf dem nct6798 rampt Smart Fan IV bei 60 °C auf 255.
- Bei `not_controllable` scheitern Schreibversuche ohnehin; ein erzwungener
  Notfall-Write scheiterte genauso.

Ein freigegebener Lüfter wird **nicht** durch den Notfall zurückgeholt. Das
kehrt die Abwägung aus #533 bewusst um: dort war der Emergency-Bypass richtig,
weil BaluHost die Kontrolle hatte. Hier hat sie das Board, und das Board ist
für genau diesen Fall gebaut.

---

## 4. Integration

### Regelkreis

Eine Abfrage pro Lüfter, direkt nachdem die Config geladen ist: ist der Lüfter
freigegeben, werden Zielwert-Berechnung und Write übersprungen. **Die
Messwert-Aufzeichnung läuft weiter** — Drehzahl und Temperatur gehören auch
dann in die Historie, wenn das Board regelt; sonst reißt der Verlaufsgraph
genau dort ab, wo man am ehesten nachsieht.

### Nutzer-Klick

Kein eigener Pfad nötig (siehe Abschnitt 1). Bei einem
`not_controllable`-Lüfter scheitert der Klick weiterhin, und der Nutzer bekommt
die echte Fehlermeldung statt eines stillen `False` — die Absicht des
`force`-Pfades aus #533. Läuft der Backoff danach erneut in den Deckel, wird
wieder freigegeben.

### API

`FanInfo` bekommt `released_reason: Optional[str]`.

### Frontend

#480 hat `pwm_control` eingeführt, #537 hat `editingLocked` durch Profile,
Save/Discard, `canEdit` und das Zeitplan-Panel gezogen, um firmware-verwaltete
Lüfter zu sperren. Ein freigegebener Lüfter ist aus Nutzersicht derselbe Fall —
die Regler sind wirkungslos, weil jemand anderes regelt. Also dieselbe Sperre
mit eigenem Hinweistext:

| Grund | Hinweis |
|---|---|
| `not_controllable` | „Nicht steuerbar — das Board regelt diesen Lüfter." |
| `no_target` | „Kein Temperaturwert — das Board regelt, bis der Sensor zurückkommt." |

Kein neues Sperr-Konzept, kein zweiter Zustandsbaum. i18n-Schlüssel in `de` und
`en`.

---

## 5. Tests und Verifikation

### Reine Einheiten

Besitz-Modul und Auflösung des Rückgabewerts fassen weder sysfs noch Datenbank
an. Die Auflösung ist als Tabelle prüfbar:

| gelesen | gespeichert | Ergebnis | persistiert? |
|---|---|---|---|
| `5` | — | `5` | ja |
| `1` | `5` | `5` | nein (unverändert) |
| `1` | — | Treiber-Fallback | **nein** |
| `1` | — , Treiber unbekannt | keine Rückgabe + WARNING | nein |

Die dritte Zeile ist die wichtigste: bliebe der Fallback hängen, wäre eine
falsche Annahme selbsterhaltend.

### Scan

`tmp_path`-Baum mit `pwm1_enable = 5`, Scan laufen lassen, gesicherten Wert
prüfen. Platform-förmig und doppelpunktfrei, damit der Test auch unter Windows
läuft (NTFS verbietet Doppelpunkte in Verzeichnisnamen, Lehre aus #532).

### Die drei Auslöser

- **Shutdown:** besessener Lüfter → nach `stop()` steht der Rückgabewert in der
  Datei. Nicht besessener Lüfter → Datei unverändert. **Sekundär-Worker → gar
  kein Write**, weil der Besitz-Zustand leer ist. Der dritte Fall ist der
  wichtigste der drei.
- **`not_controllable`:** Backoff am Deckel → Freigabe, genau eine ERROR-Zeile.
  Scheitert auch das Zurückschreiben → Lüfter gilt trotzdem als freigegeben.
- **`no_target`:** elf Zyklen ohne Wert → weiterhin besessen. Zwölfter →
  freigegeben. Wert kommt zurück → wieder übernommen. Die Grenze wird von
  beiden Seiten festgenagelt.

### Notfallpfad

Eigener Test, dass ein freigegebener Lüfter **nicht** zurückgeholt wird — es
ist eine bewusste Umkehr gegenüber #533 und sähe ohne Test wie ein Versehen aus.

### Gates

`pytest -k "fan or power"` (Messlatte 621 passed, 2 skipped), `ruff check`,
`eslint .`, `npm run build`, `vitest run`. Volle Backend-Suite in der CI.

### Feldverifikation

1. **Shutdown — der Kern.** `systemctl stop baluhost-backend`, dann
   `cat /sys/class/hwmon/hwmon3/pwm{1,2,3,7}_enable`. Erwartung: viermal `5`
   statt viermal `1`. Heute steht dort `1`; das ist die Lücke.
2. **Der Kreis schließt sich.** Dienst starten, dann
   `SELECT fan_id, pwm_enable_restore FROM fan_configs WHERE is_active`. Der
   Scan sollte `5` gesichert haben, weil der Shutdown sie hinterlassen hat.
   Damit ist die Selbstheilung belegt und der Treiber-Fallback arbeitslos.
3. **`no_target` erzwingen, reversibel.** Einem Lüfter über die API eine nicht
   existierende Sensor-ID zuweisen, eine Minute warten, `pwm_enable` lesen —
   muss auf `5` stehen. Sensor zurücksetzen, prüfen dass BaluHost binnen eines
   Zyklus wieder übernimmt.
4. **`not_controllable`** bleibt den Einheitentests überlassen. Es im Feld zu
   erzwingen hieße, Rechte oder Treiber zu manipulieren — mehr Risiko als
   Erkenntnis.

---

## Risiken

- **Der Treiber-Fallback ist eine Annahme**, für `nct6775` durch Messung
  gedeckt, für `amdgpu` durch den Ist-Zustand. Für alles andere wird bewusst
  nichts getan.
- **Die Rückgabe kann scheitern**, gerade im `not_controllable`-Fall. Der
  Lüfter gilt dann trotzdem als freigegeben; das Ergebnis wird geloggt.
- **Ob das Board nach der Rückgabe tatsächlich regelt**, ist auf BaluNode
  gemessen und für andere Hardware nicht garantiert. Da nur bei bekanntem
  Treiber zurückgegeben wird, ist das Risiko auf die zwei Fälle in der Tabelle
  begrenzt.
- **`SIGKILL` bleibt ungedeckt** (siehe Nicht-Ziele).
