# Deploy rollt systemd-Units aus — Design

**Datum:** 2026-09-27
**Status:** Entwurf
**Basis:** `main` @ `45ff8f71`
**Issue:** [#689](https://github.com/Xveyn/BaluHost/issues/689) — „LAN-Gates
wirkungslos: laufende Unit ohne --proxy-headers, Unit-Templates erreichen die Box
nie ueber den Deploy"
**Umfang:** Nur „Option 1" aus #689. Sofortmaßnahme (Drop-in) und „Option 2"
(Drift-Check `app.services.unit_drift`, #718) sind erledigt und auf BaluNode
verifiziert (Kommentare vom 2026-09-22 und 2026-09-24).

## Problem

`deploy/scripts/ci-deploy.sh` schreibt keine Unit-Dateien. Das tut ausschließlich
`deploy/install/modules/10-systemd-services.sh`, und das läuft nur bei einem
manuellen Installer-Lauf. Eine Änderung an einem Unit-Template landet im Repo und
unter `/opt/baluhost/deploy/`, erreicht aber `/etc/systemd/system/` nicht.

So lief `baluhost-backend` monatelang ohne `--proxy-headers`, obwohl das Template
die Flags trug, und alle LAN-Gates waren wirkungslos (#689). Der Drift-Check aus
#718 macht eine solche Abweichung heute sichtbar. Beheben muss sie aber weiterhin
ein Mensch von Hand.

**Ziel:** Für Unit-Dateien gilt dasselbe wie für Code. Eine Änderung an einem der
verwalteten Unit-Templates ist nach dem nächsten Deploy ohne weiteren Handgriff in
Kraft, der Drift-Check bleibt auf PASS, und ein Rollback stellt auch die alten
Units wieder her.

## Die Entscheidungen

1. **Bei jedem Deploy, nicht hinter `SYNC_PERMISSIONS`.** Der Abgleich ist
   idempotent und schreibt nur bei Abweichung, im Normalfall ist er ein No-op. Ein
   Opt-in-Schalter ließe genau die Lücke halb offen, die #689 beschreibt: Jemand
   muss an ihn denken.
2. **Ein Fehlschlag des Abgleichs bricht den Deploy ab und rollt zurück.** Ein
   Unit-Template, das nicht rendert oder das `systemd-analyze verify` ablehnt, ist
   ein kaputter Release. Neuer Code mit alten Units wäre die stille Divergenz aus
   #689. Einzige Ausnahme: Fehlt die sudoers-Erlaubnis, wird nur gewarnt (siehe
   Ablauf).
3. **Eigenes Root-Skript statt feingranularer sudo-Befehle oder Modul 10.**
   `deploy/scripts/install-systemd-units.sh` folgt dem Muster von
   `install-power-sudoers.sh` und wird über einen festen Pfad per `sudo -n bash`
   aufgerufen.
   - *Verworfen: unprivilegiert rendern, sudo nur für `install` und
     `daemon-reload`.* Das Staging-Verzeichnis gehört dem Deploy-User, er bestimmt
     den Inhalt also ohnehin. Das ist dieselbe Vertrauensgrenze, dafür kämen etwa
     zehn exakte sudoers-Strings, die mit jeder Unit wachsen, und die Prüflogik
     läge verstreut in `ci-deploy.sh`.
   - *Verworfen: Modul 10 per sudo.* Es schreibt zusätzlich vier sudoers-Dateien,
     polkit- und udev-Regeln, führt `usermod` aus und installiert Spawn-Wrapper und
     Tray. Viel zu breit für jeden Deploy und ein Rückschritt gegenüber dem
     Opt-in `SYNC_PERMISSIONS`.
4. **Ein Paritätstest statt einer gemeinsamen Unit-Liste.** Die Liste der
   verwalteten Units steht dann an vier Stellen: Modul 10 (`SERVICES`),
   `ci-deploy.sh` (`SERVICES`), `unit_drift.py` (`MANAGED_UNITS`) und das neue
   Skript. Bash und Python teilen sich schlecht eine Quelle, ein Test nagelt die
   vier auf Gleichheit fest.
5. **`systemd-analyze verify` als Vorab-Prüfung, auf BaluNode gemessen
   (2026-09-27):**
   - die vier installierten Units: `exit=0`, keine Ausgabe;
   - eine Kopie von `baluhost-backend.service` in `mktemp -d`: `exit=0`;
   - dieselbe Kopie mit relativem `ExecStart`: `exit=1` mit „Neither a valid
     executable name nor an absolute path … Unit configuration has fatal error".

   Die Prüfung liefert auf dem korrekten Stand also keinen Fehlalarm, der jeden
   Deploy zurückrollen würde, und sie lehnt eine kaputte Unit tatsächlich ab.

**Nicht im Umfang:**
- `baluhost-backend-local` (Service und Socket): erst nach #717, dort fehlen
  Installer-Pfad und ein korrektes Template. Der Drift-Check nimmt sie aus
  demselben Grund aus.
- Die Tray-User-Unit (`baluhost-tray.service`): Das ist eine User-Unit im Home
  des Desktop-Benutzers, keine System-Unit.
- `enable`/`reenable` bei Änderungen an `[Install]`, Aktivieren neu
  hinzugekommener Units, Aufräumen von Drop-ins. Das bleibt beim Installer bzw.
  wird nur vom Drift-Check gemeldet.

## Ablauf im Deploy

Neuer Schritt **6b „Systemd Units"** in `ci-deploy.sh`, nach dem Frontend-Build
und direkt vor `restart_services`:

```
… 5 Migration → 6 Frontend Build → 6b Units abgleichen → 7 Restart → 8 Health-Check
```

Warum dort: Alles davor ist gebaut und migriert. Scheitert 6b, kann `rollback()`
wie bei jedem späten Fehler Code und DB zurücksetzen. Das Skript führt selbst
`daemon-reload` aus, und `restart_services` startet ohnehin alle vier Units neu.
Geänderte Units greifen also ohne eigene Restart-Logik.

| Ergebnis | Erkennung | Reaktion |
|---|---|---|
| OK, nichts geändert oder N Units ersetzt | Exit 0 | `log_info` mit der Ausgabe des Skripts, weiter |
| sudoers-Erlaubnis fehlt | stderr beginnt mit `sudo: a password is required` | `log_warn` mit dem einmaligen Reparaturbefehl, weiter mit den installierten Units |
| Skript scheitert | jeder andere Exit ≠ 0 | `log_error`, `deploy_log_write`-Status über `rollback()`, **Rollback** |

**Umbau von `run_permission_script`.** Der Kern (Aufruf mit `LC_ALL=C sudo -n
bash "$script"`, stderr einfangen, `a password is required` erkennen) wandert in
eine Funktion, die einen Status zurückgibt: 0 = OK, 1 = Skript gescheitert, 2 =
nicht erlaubt. `run_permission_script` benutzt sie und bleibt im Verhalten
unverändert: Die drei Permission-Syncs warnen weiterhin nur. Schritt 6b benutzt
denselben Kern und entscheidet anhand des Status selbst. Der Aufruf `sudo -n bash
"$script"` steht danach weiterhin genau einmal in der Datei (Vertrag aus
`test_ci_deploy_permission_sync.py`).

**Rollback** (automatisch nach gescheitertem Health-Check oder 6b, und
`--rollback`). Die Wiederherstellung alter Units gilt für den automatischen
Rollback. `ci-deploy.sh --rollback` setzt heute auf `current_commit` zurück,
also nach einem erfolgreichen Deploy auf den aktuellen Stand; der Abgleich ist
dort ein No-op. Das ist ein vorbestehendes Verhalten des manuellen Rollbacks,
nicht Teil dieses Designs. Nach `git reset --hard "$PREV_COMMIT"` und vor `restart_services`
läuft das Skript noch einmal, **aus dem zurückgesetzten Baum**, also mit den
alten Templates:

- Hier gibt es nur Warnungen. Ein Rollback im Rollback gibt es nicht, und der
  Rollback soll so weit wie möglich kommen.
- Existiert das Skript im alten Commit noch nicht (erster Rollback nach dem
  Einführungs-Deploy), wird der Schritt mit `log_info` übersprungen.
- Ist 6b an `verify` gescheitert, hat das Skript nichts geschrieben. Der
  Re-Render im Rollback ist dann ein No-op.
- Scheitert eine korrekt geschriebene neue Unit erst beim Start, fängt das der
  Health-Check. Der Rollback schreibt die alten Units zurück, bevor er neu
  startet.

Der Rückweg nach einer gescheiterten Migration (Schritt 5, eigener `git
checkout`) braucht nichts: 6b ist dann noch nicht gelaufen.

## `deploy/scripts/install-systemd-units.sh`

Das Skript läuft als root in sechs Schritten.

1. **Kontext.**
   - `INSTALL_DIR` ergibt sich aus dem eigenen Ort (`SCRIPT_DIR/../..`, wie seit
     #581 üblich). `VENV_BIN="$INSTALL_DIR/backend/.venv/bin"`, derselbe Default
     wie in Modul 10 und `unit_drift.py`.
   - Der Dienstbenutzer kommt aus `systemctl show -p User --value
     baluhost-backend.service`. Eine Umgebungsvariable `BALUHOST_USER` hat für
     den manuellen Aufruf Vorrang, im selben Muster wie die anderen
     Permission-Skripte (`BALUHOST_USER="${BALUHOST_USER:-${SERVICE_USER:-}}"`,
     festgenagelt in `test_deploy_service_user_resolution.py`). Über den Deploy ist sie nicht setzbar: Die
     sudoers-Zeile pinnt die Kommandozeile ohne `SETENV`, und `env_reset` verwirft
     die Umgebung.
   - Ist der Benutzer leer oder kennt `id -u` ihn nicht: Exit 1.
   - `UNITS=(baluhost-backend baluhost-scheduler baluhost-webdav
     baluhost-monitoring)`.
2. **Rendern.**
   - `source "$INSTALL_DIR/deploy/install/lib/common.sh"`, dann dessen
     `process_template` mit `BALUHOST_USER`, `INSTALL_DIR` und `VENV_BIN`, also
     genau den Werten aus Modul 10. Eine eigene Render-Implementierung würde von
     Modul 10 wegdriften.
   - Gerendert wird in ein `mktemp -d`, unter den echten Dateinamen. `trap`
     räumt das Verzeichnis beim Beenden auf.
   - Steht danach noch irgendwo `@@[A-Z_]+@@`: Exit 1.
3. **Prüfen, alles oder nichts.** `systemd-analyze verify` über alle vier
   gerenderten Dateien in einem Aufruf. Bei Exit ≠ 0 geht die Ausgabe auf stderr,
   und das Skript endet mit Exit 1, **bevor irgendeine Datei in `SYSTEMD_DIR`
   angefasst ist**. Nicht-fatale Hinweise von `verify` gehen im Erfolgsfall
   ebenfalls auf stderr und landen so im Deploy-Log.
4. **Vergleichen und ersetzen**, pro Unit:
   - `cmp -s` gegen `$SYSTEMD_DIR/<unit>.service`. Bei Gleichheit weiter mit der
     nächsten Unit.
   - Existiert die Datei, geht ein Backup nach
     `$UNIT_BACKUP_DIR/<unit>.service.<YYYYmmdd-HHMMSS-Nanosekunden>` (fest
     breit, damit die Glob-Sortierung chronologisch ist). `UNIT_BACKUP_DIR`
     ist per Default `/var/backups/baluhost/units`, bewusst nicht
     `/etc/systemd/system`. Pro Unit bleiben die neuesten 10.
   - `install -m 0644 -o root -g root` in eine Temp-Datei **in** `SYSTEMD_DIR`,
     dann `mv -f` auf den Zielnamen. Der Rename auf demselben Dateisystem ist
     atomar, systemd sieht nie eine halbe Datei.
   - Ausgabe `CHANGED: <unit>`.
5. **Neu laden.** `systemctl daemon-reload`, wenn mindestens eine Unit ersetzt
   wurde **oder** eine verwaltete Unit `NeedDaemonReload=yes` meldet. Der zweite
   Fall ist der Zustand nach einem gescheiterten Reload: Die Dateien stimmen
   schon, systemd fährt aber die alte Fassung. Ein erneuter Aufruf, den der
   Drift-Check als Reparatur empfiehlt, muss ihn beheben. Scheitert der Reload:
   Exit 1.
6. **Abschluss.** `OK: <n> unit(s) replaced`, `OK: all 4 units up to date` oder
   `OK: all 4 units up to date, stale systemd state fixed by daemon-reload`,
   Exit 0.

Ein Fehler beim Schreiben mittendrin (etwa ein voller Datenträger) endet mit
Exit 1, und der Deploy rollt zurück. Der Re-Render im Rollback schreibt die alten
Templates und stellt den Zustand damit wieder her. Die Backups sind nur das
Netz für Handarbeit.

**Test-Nähte.** `SYSTEMD_DIR` (Default `/etc/systemd/system`),
`UNIT_BACKUP_DIR` und `BALUHOST_UNITS_ALLOW_NONROOT=1` (überspringt den
Root-Check) sind über die Umgebung überschreibbar, damit die Tests ohne root
gegen ein Wegwerf-Verzeichnis laufen. Über den Deploy ist keine davon erreichbar
(`env_reset`, kein `SETENV`), das steht als Kommentar im Skript. Wer die
Umgebung eines root-Aufrufs kontrolliert, braucht diese Nähte ohnehin nicht.

## sudoers und Provisionierung

`deploy/install/templates/baluhost-deploy-sudoers` bekommt im Block
„Idempotent … scripts" zwei Zeilen:

```
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /bin/bash @@INSTALL_DIR@@/deploy/scripts/install-systemd-units.sh
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/bash @@INSTALL_DIR@@/deploy/scripts/install-systemd-units.sh
```

Der Pfad ist exakt, es gibt keine Argumente, keine Wildcards und kein `SETENV`.
Beide bash-Pfade braucht es, weil sudo den aufgelösten Pfad vergleicht.

**Einmalig auf BaluNode**, nach dem Merge:

```bash
sudo env BALUHOST_USER=sven bash /opt/baluhost/deploy/scripts/install-deploy-sudoers.sh
```

Bis dahin meldet Schritt 6b bei jedem Deploy die Warnung mit genau diesem Befehl
(Benutzername per `$(id -un)` eingesetzt, wie bei `run_permission_script`). Das
Verhalten ist fail-closed auf dem heutigen Stand. Der erste Deploy danach meldet
voraussichtlich `OK: all 4 units up to date`, weil der Drift-Check seit
2026-09-24 PASS meldet. Ein einmaliges `CHANGED:` wäre harmlos: Der Drift-Check
ignoriert Leerzeichen am Zeilenende und Leerzeilen am Dateiende, `cmp` nicht.

## Vertrauensgrenze

Das Skript schreibt Units mit frei wählbarem `User=` und `ExecStart=` und läuft
als root aus einer Datei unter `$INSTALL_DIR`. Die eigentliche Grenze lautet
deshalb: **Wer als Deploy-Benutzer unter `$INSTALL_DIR` schreiben kann, hat
root.** Der Deploy-Benutzer ist zugleich der Dienstbenutzer, gehört ihm
`/opt/baluhost` (`deploy/update/run-update.sh` macht `chown -R`), und das Backend
läuft ohne `NoNewPrivileges`. Zwei Wege führen dorthin:

- ein Commit auf `main`;
- Codeausführung im Backend-Prozess, die dieses Skript (oder heute schon
  `install-power-sudoers.sh`) umschreibt und per `sudo -n bash` startet.

**Beides ist nicht neu:** Die drei `install-*-sudoers.sh` haben seit jeher
dieselbe Form. Neu ist nur, dass die Grenze benannt wird. Gegen den `main`-Weg
kompensieren Layer 3 (`github.actor == 'Xveyn'`) und Layer 4
(`production`-Environment mit Reviewer). Gegen den Backend-RCE-Weg gibt es keine
eigene Kompensation; das engere Muster wäre der Spawn-Wrapper aus Known Gap 10
(root-eigen, außerhalb von `/opt/baluhost`). `systemd-analyze verify` und der
Rollback sind **Integritäts**prüfungen, keine Sicherheitskontrollen: Eine
absichtlich bösartige Unit besteht beide.

Festgehalten wird das in `.claude/rules/ci-cd-security.md`:
- ein neuer Eintrag 12 unter „Known Gaps & Accepted Risks";
- im Reviewer-Checklist-Punkt „Sudoers / systemd" der Hinweis, dass Änderungen
  an Unit-Templates jetzt beim nächsten Deploy als root wirksam werden.

## Weitere Änderungen

- `ci-deploy.sh`, Kommentar zu Schritt 8c: Er sagt heute „This script never
  renders unit files". Neu: 6b rendert, 8c ist die unabhängige zweite Messung
  danach.
- `backend/app/services/unit_drift.py`: Docstring entsprechend. Die
  Reparaturzeile (`WARN: fix: …`) zeigt auf
  `sudo bash <install-dir>/deploy/scripts/install-systemd-units.sh` statt auf den
  ganzen Modul-10-Lauf.
- `backend/app/services/CLAUDE.md`: Die Zeile zu `unit_drift.py` sagt heute
  „Exists because the deploy never renders units" und wird entsprechend
  angepasst.
- `backend/tests/test_deploy_service_user_resolution.py`: Das neue Skript kommt
  in die Listen der geprüften Permission-Skripte, damit sein Muster der
  Benutzerauflösung nicht später zerfällt.
- `deploy/install/modules/10-systemd-services.sh` bleibt unverändert. Es rendert
  weiterhin selbst, mit demselben `process_template`.

## Tests

**Verhaltenstests für das Skript** — `backend/tests/test_deploy_install_systemd_units.py`.
Das Skript läuft wirklich unter bash, gegen `tmp_path` als `SYSTEMD_DIR` und
`UNIT_BACKUP_DIR`. `systemctl`, `systemd-analyze` und `id` sind Stub-Skripte vorn
im `PATH`, die ihre Aufrufe in eine Datei protokollieren. Ist `bash` nicht
verfügbar (Windows), werden die Tests übersprungen, die CI unter Linux führt sie
aus.

- Alles gleich: keine Datei geändert (mtime/Inhalt), **kein** `daemon-reload`,
  Exit 0, Ausgabe `OK: all 4 units up to date`.
- Eine Unit abweichend: genau diese ersetzt, Backup vorhanden, genau **ein**
  `daemon-reload`, Ausgabe `CHANGED: <unit>`.
- `verify` scheitert (Stub mit Exit 1): **keine** Datei in `SYSTEMD_DIR`
  angefasst, kein `daemon-reload`, Exit 1.
- Übriger Platzhalter (Template mit `@@UNBEKANNT@@`): Exit 1, nichts geschrieben.
- Dienstbenutzer leer bzw. von `id` unbekannt: Exit 1.
- `daemon-reload` scheitert: Exit 1.
- Backup-Rotation: Nach 12 ändernden Läufen liegen für die Unit 10 Backups.
- Ohne `BALUHOST_UNITS_ALLOW_NONROOT` und nicht als root: Exit 1.
- Rendering-Parität: Die ersetzte Datei entspricht Byte für Byte dem, was
  `process_template` aus `common.sh` mit denselben Werten erzeugt.

**`ci-deploy.sh`** — textlich, im Stil der bestehenden Deploy-Tests. Die
Reihenfolge lässt sich nur so prüfen, weil das Skript beim Laden sofort
`.env.production` braucht:

- Schritt 6b steht nach `npm run build` und vor dem Hauptfluss-Aufruf von
  `restart_services`.
- In 6b führt der Status „Skript gescheitert" zu `rollback`, der Status „nicht
  erlaubt" nicht.
- `rollback()` ruft das Skript nach `git reset --hard` und vor
  `restart_services`, und dieser Aufruf kann den Rollback nicht abbrechen.
- Verhalten des neuen Kerns, analog zu den bestehenden Tests mit
  nachgebautem sudo: Status 0, 1 und 2 für die Modi `ok`, `scriptfail`,
  `password`.
- `test_ci_deploy_permission_sync.py`: Der Extraktor für die Helferfunktion
  muss den ausgelagerten Kern mitnehmen. Die bestehenden Zusicherungen
  (genau ein `sudo -n bash "$script"`, nur warnend, Reparaturbefehl mit
  `$(id -un)`) bleiben unverändert und müssen weiter grün sein.

**Parität und sudoers**

- Die vier Unit-Listen (Modul 10, `ci-deploy.sh`, `unit_drift.MANAGED_UNITS`,
  das neue Skript) sind als Mengen gleich.
- Die Vorlage erlaubt das Skript mit genau den zwei bash-Pfaden, NOPASSWD, ohne
  Argumente und ohne Wildcard (Muster: `test_die_vorlage_erlaubt_den_power_aufruf_ueberhaupt`).
- `test_deploy_sudoers_units.py` bleibt grün: Die neuen Zeilen sind keine
  `systemctl restart`-Einträge.
- `test_unit_drift.py`: Die Reparaturzeile nennt `install-systemd-units.sh`.

## Abnahme auf BaluNode

Maßstab ist die beobachtete Wirkung, kein Exit-Code:

1. **Nach Merge und Deploy, ohne Provisionierung:** Das Deploy-Log zeigt in
   Schritt 6b die Warnung „NOT PERMITTED" mit dem Reparaturbefehl, der Deploy
   bleibt grün, der Drift-Check meldet PASS.
2. **Provisionierung ausführen, dann einen Deploy per `workflow_dispatch`:** Im
   Log steht `OK: all 4 units up to date`, der Drift-Check meldet PASS.
3. **Gegenprobe von Hand:** `sudo bash
   /opt/baluhost/deploy/scripts/install-systemd-units.sh` liefert kein
   `CHANGED`, und `systemctl show baluhost-backend -p NeedDaemonReload` bleibt
   `no`.

Dass eine Template-Änderung tatsächlich ankommt, zeigt die nächste echte
Unit-Änderung, zuerst voraussichtlich #717. Einen künstlichen Test-Commit auf
`main` gibt es dafür nicht.
