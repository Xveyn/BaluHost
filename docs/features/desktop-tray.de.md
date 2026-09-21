# Desktop-Tray (KDE Plasma)

Das BaluHost-Tray ist ein kleines Symbol im Plasma-Panel. Es zeigt, ob es
ungelesene Meldungen vom NAS gibt, und meldet kritische Ereignisse als
Desktop-Benachrichtigung — ohne dass die Web-UI offen sein muss.

Es ist ein eigenes Konsolenprogramm (`baluhost-tray`) aus dem Python-Extra
`baluhost-backend[tray]` und laeuft als **systemd-User-Unit** in der
Desktop-Sitzung. Kein root, keine Systemdienst-Rechte: das Tray liest nur.

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
baluhost-tray --pair
```

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
> Der Hintergrundprozess liest die Zugangsdaten **nur beim Start** und beendet
> sich, wenn die Kopplung wegfaellt. Ohne Neustart nimmt der laufende Dienst
> die frischen Token nie auf — das Symbol bliebe grau, obwohl das Koppeln
> erfolgreich war. Das ist der haeufigste Stolperstein beim ersten Einrichten.

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
es `baluhost-tray --pair` auf der Konsole.

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

Wer erneut koppeln will, fuehrt `baluhost-tray --pair` aus und startet den
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

Zwei Eigenheiten der Unit sind Absicht:

- **`ConditionPathExists=%h/.baluhost/tray-tokens.json`** — ohne Kopplung
  startet die Unit gar nicht erst. Sonst wuerde sie starten, sich sofort
  beenden und im Zehnsekundentakt wiederbelebt, bis das Startlimit greift.
- **`Restart=on-failure`**, nicht `always` — die Exit-Codes sind
  bedeutungstragend: `0` heisst *dauerhaft erledigt* (nicht gekoppelt, zweite
  Instanz laeuft, Extra fehlt), da hilft kein Neustart. `3` heisst
  *moeglicherweise voruebergehend* (kein Session-Bus, kein Tray-Host in der
  Sitzung), da hilft er wirklich — beim Anmelden kann das Tray schlicht vor
  Plasma dran sein.

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

Fehlschlaege erscheinen als Klartextzeile, nicht als Traceback — ein Traceback
im Journal liest niemand.

---

## Wenn etwas nicht stimmt

| Beobachtung | Ursache | Abhilfe |
|---|---|---|
| Symbol erscheint nicht, Unit „inactive (dead)", Condition nicht erfuellt | Nie gekoppelt | `baluhost-tray --pair`, dann `systemctl --user restart baluhost-tray` |
| Symbol bleibt grau, Tooltip *„nicht gekoppelt"* | Gerade gekoppelt, Dienst nicht neu gestartet | `systemctl --user restart baluhost-tray` |
| Symbol bleibt grau, Tooltip *„nicht erreichbar"* | Backend aus oder Netz weg | Warten; das Tray verbindet sich selbst wieder |
| Beim Start beendet mit Code 3 | Tray war vor Plasma dran | Nichts tun — `Restart=on-failure` versucht es erneut |
| *„PyQt6 fehlt"* | Extra nicht installiert | `pip install 'baluhost-backend[tray]'` |
| *„BaluHost Tray laeuft bereits in dieser Sitzung."* | Zweite Instanz | Nichts tun; die erste macht bereits das Richtige |

Nach einer Verbindungsunterbrechung meldet sich das Tray nur, wenn sie
**laenger als zwei Minuten** gedauert hat — kurzes Flattern des Backends soll
keinen Popup-Regen ausloesen. Ein geschlummerter („gesnoozter") Eintrag faerbt
das Symbol nach Ablauf der Frist wieder ein, spaetestens beim Abgleich alle
zehn Minuten.
