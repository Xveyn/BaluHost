# Installer: optionale Schritte dürfen die Installation nicht kippen

Issue: #683 (Restfrage aus dem Nachtrag). Folgefunde, bewusst **nicht** Teil dieser
Arbeit: #780 (Monitoring wird nicht gestartet), #781 (`cryptography` im
System-Python), #782 (umask beim Schreiben von Secret-Dateien).

## Problem

`deploy/install/install.sh` führt die Module 02–14 in einer Schleife aus und
beendet sie mit `break`, sobald ein Modul nicht mit 0 endet. Es gibt keinen
Unterschied zwischen Kern- und optionalen Schritten. Ein fehlgeschlagener
optionaler Schritt lässt deshalb `11-nginx`, `12-start-services`, die
Verifikation und das Abschluss-Banner ausfallen, die Box steht ohne Reverse-Proxy
und ohne gestartete Dienste da.

Der Tray-Teil (`install_tray_user_unit`, Modul 10) ist bereits behoben. Das
Muster steckt aber auch anderswo (Audit zu #683):

- **Modul 10:** polkit-Regel, udev-Regel, Gruppenmitgliedschaften, Update-/
  Deploy-/Hardware-/Plugin-Sudoers und der Plugin-Wrapper laufen **vor**
  `daemon-reload` und der `systemctl enable`-Schleife. `process_template`
  legt kein Zielverzeichnis an und liefert bei Schreibfehlern 1; fehlt
  `/etc/polkit-1/rules.d/` (polkit wird von Modul 02 nicht installiert), reißt
  `errexit` das Modul ab, bevor die Kerndienste aktiviert sind. Mehrere
  Sudoers-Zweige enden bei einem Validierungsfehler mit `exit 1`.
- **Modul 12:** `systemctl start` für Scheduler und WebDAV ist ungeschützt; ein
  Portkonflikt bei WebDAV überspringt Health-Check, 13 und 14.
- **Modul 13:** gesamtes Modul ist optional (logind-Idle-Helper), hat aber keinen
  einzigen Guard.
- **Modul 14:** ist fehlertolerant gebaut, endet aber bei jedem fehlgeschlagenen
  Feature mit `exit 1` und wird als „Installation stopped" gemeldet.
- **`lib/features.sh`:** `run_feature` wird in Modul 14 als `if`-Bedingung
  aufgerufen, `errexit` ist im ganzen Rumpf aus (die Falle aus #683). Ein
  fehlgeschlagenes `_apt_install` wird verschluckt, ein fehlgeschlagenes
  `_run_script` in `install_hardware_sudoers_once` ebenfalls — und das
  „fertig"-Flag wird trotzdem gesetzt.

## Ziel und Erfolgskriterien

- Ein Fehler in einem **optionalen** Schritt lässt die Installation durchlaufen;
  Verifikation und Banner laufen, die Warnung steht im Banner und im Log.
- Ein Fehler in einem **Kern**modul bricht wie bisher ab (Resume-Hinweis,
  Exit 1, spätere Module laufen nicht).
- Ein Fehler in einem optionalen Block von Modul 10 verhindert nie das
  Aktivieren der Kerndienste.
- Ein fehlgeschlagenes Paket-/Setup-Kommando in `features.sh` gilt nicht mehr
  als Erfolg.

Nicht-Ziel: Fehler grundsätzlich tolerieren. Kernmodule (Postgres, nginx,
Backend-Start) müssen hart scheitern.

## Entwurf

### 1. `install.sh`: Registry der optionalen Module

Neben `MODULES` kommt `readonly -a OPTIONAL_MODULES=("13-power-helpers"
"14-optional-features")`. In der Schleife (Zeile ~263):

- Scheitert ein Modul aus `OPTIONAL_MODULES`: `log_warn` statt `log_error`/
  `break`, Name in ein Array `warned_modules`, Schleife läuft weiter,
  `load_config` wie gewohnt.
- Scheitert ein anderes Modul: unverändert.
- Nach der Schleife (wenn `failed=0`) laufen Verifikation und Banner. Ist
  `warned_modules` nicht leer, lautet die Überschrift
  „Installation Complete (with warnings)", gefolgt von einer Liste der Module
  und dem Nachhol-Befehl `sudo $0 --module <name>`.
- **Exit-Code bei Warnungen: 0.** Der Server steht; Automatisierung soll das nicht
  als Fehlschlag werten. `failed` bleibt ausschließlich für Kernmodule.
- Einzelmodul-Modus (`--module`) bleibt unverändert und gibt den Exit-Code des
  Moduls durch — dort will der Betreiber den echten Status.
- Ein Hilfsprädikat `is_optional_module()` kapselt den Lookup; `--list-modules`
  markiert optionale Module mit `(optional)`.

Das Banner nennt weiterhin nur die drei Kerndienste; die Monitoring-Zeile gehört
zu #780.

### 2. Modul 10: Kern zuerst, optionale Blöcke danach, jeder isoliert

Reihenfolge neu: Unit-Dateien rendern → `daemon-reload` → `systemctl enable`-
Schleife (Kern) → danach die optionalen Blöcke. Verschoben werden: Update-,
Deploy-, Hardware-Sudoers, Plugin-Wrapper + Sudoers, polkit, udev, Gruppen
(`video`, `bluetooth`) und der Tray-Aufruf. Kein zweiter `daemon-reload`: kein
optionaler Block verändert System-Units.

Muster für jeden optionalen Block: **kein** `block || warn` über mehrere Kommandos
(Falle aus #683), sondern Guard pro Kommando:

```bash
[[ -d /etc/polkit-1/rules.d ]] || { log_warn "polkit nicht installiert — Regel übersprungen."; skip=1; }
process_template ... || { log_warn "..."; skip=1; }
```

Konkret je Block: Zielverzeichnis prüfen (`/etc/polkit-1/rules.d`,
`/etc/udev/rules.d`, `/usr/local/sbin`), `process_template`/`chmod`/`chown`
einzeln mit `|| { log_warn …; return/continue }`, `usermod -aG` mit
`|| log_warn`. Die Sudoers-Blöcke behalten das Löschen einer durchgefallenen
Datei (`visudo -cf` || `rm -f`), ersetzen aber `exit 1` durch Warnung und
Überspringen. Die wiederkehrende Sudoers-Form (rendern, `chmod 0440`, `visudo -cf`, bei
Fehler löschen) wird zu einer Funktion `install_sudoers_file <template> <dest>`.
Sie schützt **jedes** Kommando im Rumpf einzeln mit `|| return 1`, weil sie vom
Aufrufer in einer `if`-Bedingung (`if install_sudoers_file …; then …; else
log_warn …; fi`) aufgerufen wird und `errexit` dort aus ist.

Der Plugin-Wrapper bleibt „fail closed": Fehlt er, sind externe Plugins
unbenutzbar (bestehender Zweig bei Zeile ~155); das ist kein Installationsfehler.

### 3. Modul 12: nur das Backend ist Kern

`baluhost-backend`: Start und Health-Check unverändert hart (`exit 1`).
`baluhost-scheduler` und `baluhost-webdav`: `systemctl start/restart … ||
{ log_warn "$service konnte nicht gestartet werden"; ALL_OK=false; }`. Das
Backend wird zuerst gestartet; die bestehende Statusausgabe zeigt die
Warnung bereits an. Health-Timeout bleibt bei 10 s (kein Teil dieser Arbeit).

### 4. Modul 13: Guards, ehrlicher Exit

Kein Guard-Gewirr im Modul: jeder Schritt (`mkdir`, `cp`, `process_template`,
`chmod`/`chown`, `visudo`) bekommt `|| { log_error "…"; exit 1; }` mit klarer
Meldung. Ein Fehler endet das Modul weiter mit `exit 1` — ob das die Installation
kippt, entscheidet jetzt der Orchestrator (Punkt 1), nicht das Modul. Eine
kaputte Sudoers-Datei wird wie bisher gelöscht.

### 5. Modul 14: Exit-Code bleibt ehrlich

`exit 1` bei fehlgeschlagenen Features bleibt; der Orchestrator zeigt es nun als
Warnung statt als Abbruch. Die Meldung „Der Kern-NAS bleibt unberührt" bleibt
zutreffend.

### 6. `lib/features.sh`

- `run_feature`: `_apt_install $pkgs || return 1` und
  `feature_setup "$key" || return 1`, explizit statt auf `errexit` zu bauen
  (der Aufrufer nutzt `if run_feature`, `errexit` ist dort aus).
- `install_hardware_sudoers_once`: `_run_script … || return 1`; `_HW_SUDOERS_DONE=true`
  erst nach Erfolg, damit ein zweites Feature (SMART nach RAID) es erneut
  versucht.
- `feature_precheck "$key" || true` bleibt (reiner Hinweis).

## Tests

`deploy/install/tests/test-install-orchestration.sh` (läuft die echte `install.sh`
gegen Stub-Module; unprivilegiert):

1. Stub `13-power-helpers` und/oder `14-optional-features` mit `exit 1`: Lauf endet
   mit Exit 0, alle übrigen Module laufen, Verifikation läuft, Banner enthält
   „with warnings" und nennt das Modul.
2. Beide optionalen Module scheitern: weiterhin Exit 0, beide in der Liste.
3. Stub `11-nginx` scheitert (Kernmodul): Exit ≠ 0, „Installation stopped",
   `12`–`14` laufen nicht (bestehender Test 3 bleibt gültig).
4. `--module 13-power-helpers` mit Exit 1 propagiert den Code (Einzelmodus).
5. `--list-modules` markiert optionale Module.

Neu: `deploy/install/tests/test-features-errexit.sh` — lädt `lib/features.sh` mit
gestubbtem `_apt_install` und `_run_script`, ruft `run_feature` in einer
`if`-Bedingung auf und prüft: Fehler aus `_apt_install` ⇒ Rückgabe ≠ 0; Fehler aus
`install_hardware_sudoers_once` ⇒ Rückgabe ≠ 0 **und** `_HW_SUDOERS_DONE` bleibt
`false`.

Modul 10 und 12 lassen sich ohne Root-Umgebung nur eingeschränkt testen: Für Modul
10 ein Test mit `process_template`-Stub und fehlendem Zielverzeichnis in einer
Sandbox (`require_root` überschrieben wie im Orchestrierungstest) — erwartet:
Exit 0, `enable`-Schleife erreicht (Stub-`systemctl` protokolliert die Aufrufe
und prüft, dass `enable` **vor** den optionalen Blöcken steht). Ist das nicht
sauber stubbar, wird die Reihenfolge stattdessen durch einen statischen Test
abgesichert (Zeile der `enable`-Schleife < Zeile des ersten optionalen Blocks)
und im Plan ausdrücklich so benannt.

## Dokumentation

`deploy/install/` hat kein eigenes CLAUDE.md; falls `docs/` den Installer-Ablauf
beschreibt, wird der Absatz „Installation stoppt bei Modulfehler" um die
Unterscheidung Kern/optional ergänzt (im Plan prüfen, ob eine Stelle existiert).

## Nicht Teil dieser Arbeit

#780, #781, #782; weiche Git-Fehler in Modul 04 (`checkout`/`fetch`/`pull` nur
Warnung); kosmetische Versionsausgaben unter `set -e` in 05/06; das
`|| true` mit anschließendem Erfolgs-Log in `03:65`; Health-Timeout in Modul 12.
Auf Wunsch jeweils eigene Issues.
