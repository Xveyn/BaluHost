# Desktop-Tray (KDE Plasma)

Das BaluHost-Tray ist ein kleines Symbol im Plasma-Panel. Es zeigt, ob es
ungelesene Meldungen vom NAS gibt, und meldet kritische Ereignisse als
Desktop-Benachrichtigung — ohne dass die Web-UI offen sein muss.

Es ist ein eigenes Konsolenprogramm aus dem Python-Extra
`baluhost-backend[tray]` und laeuft als **systemd-User-Unit** in der
Desktop-Sitzung. Kein root, keine Systemdienst-Rechte: das Tray liest nur.
Auf einer normalen Installation liegt es unter
`/opt/baluhost/backend/.venv/bin/baluhost-tray`.

---

## Das Symbol

Die BaluHost-Katze mit einem kleinen Punkt unten rechts. Vier Zustaende:

| Zustand | Aussehen | Bedeutung |
|---|---|---|
| `ok` | **gruener Punkt** | Verbunden, nichts Ungelesenes |
| `warning` | gelber Punkt | Mindestens eine ungelesene Warnung |
| `critical` | roter Punkt | Mindestens eine ungelesene kritische Meldung |
| `offline` | entsaettigt, **ohne** Punkt | Keine Verbindung — oder nicht gekoppelt |

Auch der ruhige Zustand traegt einen Punkt, und zwar einen gruenen. Ohne
Badge liesse sich „alles in Ordnung" nicht von „Symbol nicht geladen" oder
„Zustand unbekannt" unterscheiden. Nur bei `offline` fehlt der Punkt: dort
traegt die Entsaettigung die Aussage, und ein Punkt waere irrefuehrend — wir
wissen in diesem Moment ja gerade nichts.

### Gruen ist keine Gesundheitsaussage

**Gruen heisst „nichts Ungelesenes", nicht „dem NAS geht es gut."** Wer eine
Meldung liest — im Web, auf dem Handy, egal wo —, faerbt das Symbol gruen,
waehrend das RAID weiterhin degradiert ist. Das Symbol zaehlt ungelesene
Meldungen; es misst nicht den Zustand der Maschine. Fuer den Zustand ist das
Dashboard zustaendig.

Grau hat zwei Ursachen, die verschiedene Reaktionen verlangen. Welche es ist,
sagt der Tooltip beim Darueberfahren:

- *„BaluHost — nicht erreichbar"* → warten, das Tray verbindet sich selbst
  wieder.
- *„BaluHost — nicht gekoppelt: baluhost-tray --pair"* → handeln, siehe unten.

---

## Kopplung

```bash
/opt/baluhost/backend/.venv/bin/baluhost-tray --pair
```

Das Programm liegt im venv der Installation und ist damit **nicht im PATH** —
der nackte Name `baluhost-tray` funktioniert auf dem Zielrechner nicht von
selbst. Wer sich die Tipparbeit sparen will, legt einen Symlink an:

```bash
sudo ln -s /opt/baluhost/backend/.venv/bin/baluhost-tray /usr/local/bin/baluhost-tray
```

Ein Alias in `~/.bashrc` tut es genauso. Beides ist ein Angebot, keine
Voraussetzung; in dieser Doku steht deshalb durchgehend der volle Pfad. Die
Meldungen des Programms selbst — etwa der Tooltip *„nicht gekoppelt:
baluhost-tray --pair"* — nennen weiterhin den kurzen Namen.

Das Programm zeigt einen **sechsstelligen Code** und die Adresse zur Freigabe.
Den Code in der Web-UI unter **Geraete** bestaetigen — fertig, die Zugangsdaten
landen auf der Platte.

Das funktioniert **auch waehrend der Dienst laeuft**: die Kopplung nimmt ein
eigenes Schloss, es muss also nichts gestoppt werden.

> **Wichtig: nach dem Koppeln den Dienst neu starten.**
>
> ```bash
> systemctl --user restart baluhost-tray
> ```
>
> Der Hintergrundprozess liest die Zugangsdaten **nur beim Start**. Ohne
> Neustart nimmt der laufende Dienst die frischen Token nie auf — das Symbol
> bliebe grau, obwohl das Koppeln erfolgreich war. Das ist der haeufigste
> Stolperstein beim ersten Einrichten.

Beim allerersten Mal ist der Neustart ohnehin noetig: die Unit startet ohne
vorhandene Zugangsdaten gar nicht erst (siehe *Autostart*).

---

## Menue und Klick

Rechtsklick auf das Symbol:

| Eintrag | Wirkung |
|---|---|
| **BaluHost oeffnen** | Oeffnet die Web-UI im Standardbrowser |
| **Eine Stunde stumm** | Haelt Popups eine Stunde zurueck (umschaltbar) |
| **Geraete in der Web-UI** | Oeffnet die Geraeteseite — dort wird gekoppelt und widerrufen |
| **Beenden** | Beendet das Tray fuer diese Sitzung |

Ein einfacher Linksklick auf das Symbol oeffnet ebenfalls die Web-UI.

Der Menuepunkt heisst bewusst *„Geraete in der Web-UI"* und nicht *„Neu
koppeln"*: er kann die Kopplung nicht selbst wiederherstellen, dafuer braucht
es `/opt/baluhost/backend/.venv/bin/baluhost-tray --pair` auf der Konsole.

---

## Verhalten beim Spielen

Laeuft ein Spiel, werden Popups **zurueckgehalten, nicht verworfen**. Das
Symbol faerbt sich trotzdem — wer waehrend des Spielens hinsieht, sieht Rot.

Nach der Spielsitzung wird das Zurueckgehaltene zugestellt, in der Regel
innerhalb von 30 Sekunden (so oft fragt das Tray nach). Ab **vier** Meldungen
kommt statt eines Popup-Schwalls eine gesammelte Zeile: *„N neue kritische
Meldungen"*.

Zusaetzlich greift Plasmas eigenes **„Nicht stoeren"**. Das Tray meldet ueber
die Standardschnittstelle `org.freedesktop.Notifications`, also gelten alle
Regeln, die Plasma ohnehin durchsetzt — das Tray muss dafuer nichts selbst
erkennen.

---

## Stummschaltung

**Eine Stunde stumm** im Menue haelt alle Popups zurueck. Danach — oder wenn
der Haken vorher wieder entfernt wird — kommt das Zurueckgehaltene, nach
derselben Regel wie beim Spielen (ab vier Meldungen gesammelt).

Zurueckgehaltenes geht nie verloren. Eine Meldung spaet zu sehen ist besser,
als sie gar nicht zu sehen.

---

## Wo die Zugangsdaten liegen

```
~/.baluhost/tray-tokens.json     (Datei 0600, Verzeichnis 0700)
```

Darin stehen ein Access- und ein Refresh-Token.

> **Das ist ein vollwertiges Nutzer-Token.** Wer die Datei lesen kann, kann
> die API mit den Rechten dieses Kontos benutzen — nicht nur Meldungen
> abrufen. Deshalb gehoert sie niemandem ausser dem Benutzer selbst, und
> deshalb wird sie mit `0600` schon beim Anlegen geschrieben und nicht erst
> nachtraeglich.

Auf Maschinen mit mehreren Anmeldungen ist das der Grund, das Tray nur im
eigenen Konto zu koppeln.

---

## Kopplung widerrufen

In der Web-UI unter **Geraete** das Geraet entfernen. Das Tray merkt es beim
naechsten Zugriff, geht in den Zustand *„nicht gekoppelt"* (graues Symbol),
meldet sich **einmal** mit *„Kopplung aufgehoben — bitte neu koppeln"* und
loescht die Zugangsdaten von der Platte. Danach ist Ruhe: es entsteht kein
Sturm von Anfragen im Log.

Beendet wird dabei nur der Hintergrund-Arbeiter — der Prozess selbst laeuft
mit grauem Symbol weiter, damit der Tooltip die Erklaerung behalten kann.

Wer erneut koppeln will, fuehrt
`/opt/baluhost/backend/.venv/bin/baluhost-tray --pair` aus und startet den
Dienst neu (siehe oben).

---

## Autostart und Installation

Der Installer legt eine **User-Unit** an:

```
~/.config/systemd/user/baluhost-tray.service
```

Sie haengt an `graphical-session.target` — das Tray gehoert zur
Desktop-Sitzung, nicht zum Systemstart.

Der Ziel-Benutzer wird beim Installieren getrennt bestimmt und **nicht** aus
dem BaluHost-Dienstkonto abgeleitet: eine User-Unit im Home des Dienstkontos
startet in keiner Desktop-Sitzung. Vorgabe ist `SUDO_USER`, ausdruecklich
setzen laesst er sich so:

```bash
sudo TRAY_DESKTOP_USER=sven TRAY_WEB_URL=https://baluhost.local ./install.sh
```

Steht kein Desktop-Benutzer fest, meldet der Installer das und ueberspringt
den Schritt, statt die Unit in ein falsches Home zu schreiben.

> **Der Autostart kann fehlen, obwohl die Unit da ist.** Aktivieren laesst
> sich eine User-Unit nur aus einer laufenden Sitzung des Zielbenutzers
> heraus. Bei einer Erstinstallation per SSH als root gibt es die nicht —
> das ist der Normalfall, nicht die Ausnahme. Die Unit liegt dann zwar in
> `~/.config/systemd/user/`, aber `systemctl --user enable` ist nie gelaufen,
> es gibt keinen Symlink in `graphical-session.target.wants/`, und
> `WantedBy=` bleibt wirkungslos. Der Installer sagt das als **Warnung**.
> Einmal nachholen, angemeldet als der Zielbenutzer:
>
> ```bash
> systemctl --user enable baluhost-tray.service
> ```
>
> Ob es noetig ist, beantwortet `systemctl --user status baluhost-tray` —
> Punkt 15 der Abnahme unten prueft genau das.

### Einmalig: das Extra `[tray]` nachinstallieren

Das venv der Installation enthaelt das Extra **nicht**. Das ist Absicht: Qt
gehoert nicht auf eine kopflose Serverinstallation, und das Tray ist ein
Opt-in fuer die eine Maschine, die auch Desktop ist. Genau einmal:

```bash
sudo /opt/baluhost/backend/.venv/bin/pip install -e '/opt/baluhost/backend[tray]'
```

Ohne diesen Schritt ist die Unit zwar angelegt **und aktiviert**, das Tray
beendet sich beim Start aber sofort mit *„PyQt6 fehlt"*. Der Installer weist
beim Anlegen der Unit mit genau diesem Befehl darauf hin.

Der volle Pfad ins venv ist noetig, nicht Bequemlichkeit: ein nacktes
`pip install` liefe gegen das System-Python, und das ist auf Debian 13
„externally managed" (PEP 668) und weist die Installation ab.

### Drei Eigenheiten der Unit sind Absicht

- **`ConditionPathExists=%h/.baluhost/tray-tokens.json`** — ohne Kopplung
  startet die Unit gar nicht erst. Das verhindert *keinen* Neustart-Sturm:
  der ungekoppelte Fall endet mit Exit 0, und `Restart=on-failure` startet
  bei 0 ohnehin nicht neu. Der Gewinn ist die Lesbarkeit des Zustands —
  `systemctl --user status` zeigt `condition failed`, und das heisst fuer
  einen Menschen „noch nicht eingerichtet". Ein Start, der sich sofort sauber
  beendet, saehe dort dagegen wie ein Fehlstart aus.
- **`Restart=on-failure`**, nicht `always` — die Exit-Codes sind
  bedeutungstragend: `0` heisst *dauerhaft erledigt* (nicht gekoppelt, zweite
  Instanz laeuft, Extra fehlt), da hilft kein Neustart. `3` heisst
  *moeglicherweise voruebergehend*: kein Session-Bus oder kein Tray-Host in
  der Sitzung — beim Anmelden kann das Tray schlicht vor Plasma dran sein —,
  **oder** ein durchgereichter Fehler des Hintergrundprozesses, dessen
  Ursache niemand kennt. Da hilft ein Neustart wirklich.
- **`StartLimitIntervalSec=300` mit `StartLimitBurst=5`** — die Unit setzt ihr
  Startlimit selbst. Die systemd-Vorgabe ist ein Fenster von zehn Sekunden
  bei fuenf Versuchen; bei `RestartSec=10s` faellt hoechstens ein Start in
  jedes Fenster, die fuenf werden nie erreicht, und ein dauerhafter Exit 3
  liefe **endlos** alle zehn Sekunden weiter. Fuenf Minuten fassen die fuenf
  Versuche, danach ist Schluss.

---

## Dienst und Logs

```bash
systemctl --user status baluhost-tray      # Laeuft es?
systemctl --user restart baluhost-tray     # Nach --pair noetig
systemctl --user enable  baluhost-tray     # Autostart einschalten
journalctl --user -u baluhost-tray -f      # Mitlesen
```

Mehr Details im Journal:

```bash
systemctl --user set-environment BALUHOST_TRAY_LOG_LEVEL=DEBUG
systemctl --user restart baluhost-tray
```

Zu jedem Fehlschlag steht eine Klartextzeile im Journal, die sagt, was zu tun
ist. Im unerwarteten Fall steht der Traceback **zusaetzlich** dort
(`logger.exception` in `tray.py`): die Zeile ist fuer den Menschen davor, der
Traceback fuer die Ursachensuche.

---

## Wenn etwas nicht stimmt

| Beobachtung | Ursache | Abhilfe |
|---|---|---|
| Symbol erscheint nicht, Unit „inactive (dead)", Condition nicht erfuellt | Nie gekoppelt | `/opt/baluhost/backend/.venv/bin/baluhost-tray --pair`, dann `systemctl --user restart baluhost-tray` |
| Symbol bleibt grau, Tooltip *„nicht gekoppelt"* | Gerade gekoppelt, Dienst nicht neu gestartet | `systemctl --user restart baluhost-tray` |
| Symbol bleibt grau, Tooltip *„nicht erreichbar"* | Backend aus oder Netz weg | Warten; das Tray verbindet sich selbst wieder |
| Beim Start beendet mit Code 3 | Tray war vor Plasma dran — **oder** der Hintergrundprozess ist unerwartet gescheitert | Beim Anmelden: nichts tun, `Restart=on-failure` versucht es erneut. Sonst ins Journal sehen (`journalctl --user -u baluhost-tray`): steht dort *„Tray-Hintergrund beendet"* oder ein Traceback, ist es ein echter Absturz und kein Startreihenfolge-Problem |
| *„PyQt6 fehlt"* | Extra nicht installiert | `sudo /opt/baluhost/backend/.venv/bin/pip install -e '/opt/baluhost/backend[tray]'` |
| *„BaluHost Tray laeuft bereits in dieser Sitzung."* | Zweite Instanz | Nichts tun; die erste macht bereits das Richtige |

Nach einer Verbindungsunterbrechung meldet sich das Tray nur, wenn sie
**laenger als zwei Minuten** gedauert hat — kurzes Flattern des Backends soll
keinen Popup-Regen ausloesen. Ein geschlummerter („gesnoozter") Eintrag faerbt
das Symbol nach Ablauf der Frist wieder ein, spaetestens beim Abgleich alle
zehn Minuten.

---

## Abnahme auf dem Zielrechner

Kein CI-Ersatz. PyQt6 ist auf dem Entwicklungsrechner nicht installiert, das
Tray laesst sich dort nicht starten — diese Liste ist fuer einen Menschen an
der echten Maschine geschrieben.

### Voraussetzungen

- [ ] **0a.** Extra einmalig nachinstallieren:
      `sudo /opt/baluhost/backend/.venv/bin/pip install -e '/opt/baluhost/backend[tray]'`
- [ ] **0b.** `test -f ~/.config/systemd/user/baluhost-tray.service` → die
      Datei muss da sein. Fehlt sie, ist Modul 10 in den Zweig *„Kein
      Desktop-Benutzer bekannt"* gelaufen (oder in *„Kein Home fuer …"*).
      Abhilfe: Installation erneut mit `TRAY_DESKTOP_USER=<name>`.
- [ ] **0c.** `/opt/baluhost/backend/.venv/bin/baluhost-tray --pair` →
      sechsstelliger Code erscheint; in der Web-UI unter **Geraete**
      freigeben; Ausgabe `Gekoppelt.`
- [ ] **0d.** **`systemctl --user restart baluhost-tray`** — zwingend. Der
      Arbeiter liest die Zugangsdaten **nur beim Start**; ohne Neustart nimmt
      ein laufender Dienst die frischen Token nie auf und das Symbol bleibt
      grau, obwohl das Koppeln geklappt hat. Vor dem ersten Koppeln startet
      die Unit wegen `ConditionPathExists` ohnehin nicht
      (`systemctl --user status` zeigt `condition failed`) — das ist Absicht,
      kein Fehler.

### Die zwoelf Punkte

- [ ] **1.** `systemctl --user start baluhost-tray` → Symbol erscheint im Panel.
- [ ] **2.** Backend stoppen → Symbol wird grau, **eine** Meldung, danach Ruhe.
- [ ] **3.** Backend starten → Symbol wird gruen; Rueckmeldung nur bei
      Unterbrechung ueber zwei Minuten.
- [ ] **4.** Kritische Testmeldung erzeugen → rotes Symbol plus Popup.
      `POST /api/notifications` ist **admin-only** (`get_current_admin`) und
      nimmt einen `NotificationCreate`-Body. Damit das Tray ueberhaupt
      reagiert, muss `notification_type` **`critical`** sein — `warning`
      faerbt das Symbol nur und loest kein Popup aus — **und** `user_id` das
      gekoppelte Konto treffen (`null` ist ein Rundruf und erreicht nur
      Admin-Konten). `category` muss aus der festen Liste stammen: `raid`,
      `smart`, `backup`, `scheduler`, `system`, `security`, `sync`, `vpn`,
      `lifecycle`.

      ```bash
      # Admin-Token holen (bei aktivem 2FA liefert der Login stattdessen einen
      # pending_token — dann den Token aus der angemeldeten Web-UI nehmen)
      TOKEN=$(curl -s -X POST https://baluhost.local/api/auth/login \
        -H 'Content-Type: application/json' \
        -d '{"username":"admin","password":"<passwort>"}' \
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

      # user_id ist die id des gekoppelten Kontos, nicht die des Admins
      curl -X POST https://baluhost.local/api/notifications \
        -H "Authorization: Bearer $TOKEN" \
        -H 'Content-Type: application/json' \
        -d '{
              "user_id": 1,
              "notification_type": "critical",
              "category": "system",
              "title": "Abnahme Schritt 4",
              "message": "Testmeldung fuer das Desktop-Tray",
              "priority": 3
            }'
      ```

      Einen spontan degradierenden RAID gibt es nicht zu simulieren:
      `emit_raid_degraded_sync` wird nur aus `degrade()` gerufen, also wenn
      BaluHost selbst ein Device ausfallen laesst. Alternative ohne HTTP:
      `simulate_failure` im Dev-Backend.
- [ ] **5.** Dieselbe Meldung **auf dem Handy** wegwischen → Symbol wird ohne
      Zutun gruen.
- [ ] **6.** Meldung snoozen, Frist kurz waehlen → Symbol gruen, und nach
      spaetestens zehn Minuten (Neuabgleich) wieder rot.
- [ ] **7.** Spiel im Vollbild starten — **direkt aus Steam, nicht ueber
      BaluHost** —, Testmeldung erzeugen → kein Popup, Symbol rot.
- [ ] **8.** Spiel beenden → innerhalb von 30 Sekunden wird die
      zurueckgehaltene Meldung zugestellt.
- [ ] **9.** „Eine Stunde stumm" waehlen, Meldung erzeugen → kein Popup;
      Menuepunkt erneut waehlen oder abwarten → Zustellung.
- [ ] **10.** Zweites `/opt/baluhost/backend/.venv/bin/baluhost-tray` starten →
      beendet sich mit Hinweis („BaluHost Tray laeuft bereits in dieser
      Sitzung.", Exit-Code 0).
- [ ] **11.** `/opt/baluhost/backend/.venv/bin/baluhost-tray --pair` bei
      laufendem Dienst → zeigt einen Code, statt sich zu beenden.
- [ ] **12.** Kopplung in der Web-UI widerrufen → Symbol grau, eine Meldung,
      kein Sturm von Anfragen im Log.

### Nach Punkt 12

- [ ] **13.** Nach dem Widerruf erneut koppeln:
      `/opt/baluhost/backend/.venv/bin/baluhost-tray --pair`, freigeben,
      **dann `systemctl --user restart baluhost-tray`** → Symbol wird wieder
      gruen. Ohne den Neustart bleibt es grau — dieselbe Falle wie bei 0d, und
      derselbe Grund. Genau hier wird sie ein zweites Mal gestellt, weil Punkt
      11 zeigt, dass Koppeln bei laufendem Dienst geht: es geht, aber der
      Dienst *uebernimmt* die neuen Token erst nach einem Neustart.

### Autostart pruefen

- [ ] **14.** Abmelden und neu anmelden → das Symbol ist ohne Zutun da
      (`WantedBy=graphical-session.target`).
- [ ] **15.** `systemctl --user status baluhost-tray` zeigt `enabled`;
      `journalctl --user -u baluhost-tray` enthaelt keine Tracebacks.
