# KDE-Session entsperren beim Displays-Einschalten — Design

**Datum:** 2026-07-24
**Status:** entworfen, abgenommen

## Ziel

Wer die Displays über die Web-App einschaltet, hat sich dort bereits mit Passwort
(und je nach Konto mit 2FA) authentifiziert. Trotzdem steht danach der
KDE-Sperrbildschirm im Weg und verlangt dieselbe Person ein zweites Mal nach
einem Passwort. Dieses Design lässt `POST /system/sleep/desktop/enable` die
grafische Session mit entsperren — unter zwei Bedingungen, die beide erfüllt
sein müssen.

## Ausgangslage (gemessen, nicht angenommen)

### Was heute passiert

`desktop_enable` (`api/routes/desktop.py`) ruft `kscreen-doctor --dpms on` als
User `sven` auf. Das ist **reine Display-Ansteuerung**. Der KDE-Sessionlock ist
eine davon unabhängige Schicht, die BaluHost nirgends berührt: eine Suche über
`backend/app` nach `loginctl`, `kscreenlocker`, `ScreenSaver`, `unlock-session`
oder `lock-session` liefert keinen einzigen funktionalen Treffer.

### Warum überhaupt gesperrt wird

Auf BaluNode existiert **keine** `~/.config/kscreenlockerrc`
(`cat` → „Datei oder Verzeichnis nicht gefunden“; `kreadconfig6` und
`kreadconfig5` sind beide unter `/usr/bin` vorhanden, das leere Ergebnis kam
also nicht von einem fehlenden Binary). Damit greifen die KDE-Vorgaben:
Auto-Lock **an**, Timeout **5 Minuten**, Sperren nach dem Aufwachen **an**. Das
sind die beiden Auslöser.

### Der Mechanismus funktioniert ohne root

Auf der Box gemessen, Session 2 ist die grafische (`seat0`, `tty2`, Klasse
`user`; Session 27 war die SSH-Verbindung, 3 der User-Manager, 1 der CI-Runner):

```
$ loginctl lock-session 2
$ loginctl show-session 2 -p LockedHint
LockedHint=yes
$ loginctl unlock-session 2
$ loginctl show-session 2 -p LockedHint
LockedHint=no
```

**Ohne `sudo`, ohne polkit-Rückfrage.** Der Grund: `systemd-logind` sendet ein
`Unlock`-Signal an die Session, und kscreenlocker befolgt es — derselbe Weg, über
den Fingerabdrucksensoren und Smartcards entsperren. Und das Backend läuft
bereits als genau der User, dem die Session gehört (`sven`, UID 1000 — in
Teilprojekt 1 des Steam-Tracks nachgemessen, dort steht auch, dass es keinen
`baluhost`-User auf der Box gibt).

Daraus folgt: **keine sudoers-Regel, kein Wrapper, kein Privilegienzuwachs auf
Systemebene.** Das ist der Grund, warum dieses Feature überhaupt vertretbar ist.

**Grenze dieser Messung, ehrlich benannt:** Sie lief aus einer SSH-Verbindung —
die ist selbst eine logind-Session. Das Backend ist dagegen ein **session-loser
Systemdienst** unter `system.slice`. Sehr wahrscheinlich greift loginds
Owner-Regel (Caller-UID == Session-Owner-UID, per D-Bus-Credentials), die vom
Session-Status des Callers unabhängig ist — aber das ist eine Annahme über
logind-Interna, kein Messwert. Der Dienst-Kontext wird deshalb vor der
Implementierung separat gemessen (siehe Offene Punkte); fällt die Messung
negativ aus, braucht das Design einen sudoers-Eintrag im Muster von
`sudoers-baluhost-power` und ist neu abzuwägen.

### Bestehendes Rechtemodell

`UserPowerPermission` (`models/power_permissions.py`) hat eine Boolean-Spalte je
Aktion (`can_soft_sleep`, `can_wake`, `can_suspend`, `can_wol`,
`can_toggle_desktop`). `_make_power_dependency(action)` in `api/deps.py` lässt
**Admins per Rolle durch** und prüft für alle anderen
`check_permission(db, user.id, action)`.

`run_plugin_menu_action` (`api/routes/plugins.py`) hängt an `get_current_admin` —
Plugin-Menüaktionen sind ohnehin admin-only.

## Entscheidungen (im Brainstorming getroffen)

- **Auslöser: der bestehende Enable-Knopf entsperrt mit**, nicht ein zweiter
  Knopf. Dafür bekommt das Entsperren aber ein **eigenes, separat vergebenes
  Recht** — `can_toggle_desktop` bleibt eine reine Strom-Berechtigung und wächst
  nicht heimlich zum Desktop-Schlüssel.
- **Exposition: nur LAN und VPN.** Über `baluhost.duckdns.org` aus dem offenen
  Netz wird nicht entsperrt.
- **Der Gaming-Modus (Teilprojekt 2) entsperrt nach denselben Regeln.** Er
  schaltet dieselben Displays ein und liefe sonst genauso gegen den
  Sperrbildschirm — mit dem Unterschied, dass niemand erklären könnte, warum der
  eine Knopf funktioniert und der andere nicht.
- **Admins dürfen automatisch**, wie bei allen anderen Power-Rechten. Das neue
  Recht steuert ausschließlich delegierte Nutzer.

## Nicht-Ziele

- **Keine erneute Passwort- oder 2FA-Abfrage** vor dem Entsperren. Der
  Ausgangspunkt war „ich habe mich doch schon angemeldet"; eine Step-up-Abfrage
  würde genau das aufheben. Preis, ausgesprochen: ein gestohlenes Token aus dem
  `localStorage` reicht innerhalb seiner 15 Minuten, sofern der Dieb im LAN oder
  VPN ist.
- **Kein Abschalten des KDE-Locks.** Die codefreie Alternative (Auto-Lock und
  `LockOnResume` per `kwriteconfig6` aus) wurde erwogen und verworfen: sie
  entfernt den Schutz gegen physischen Zugriff vollständig.
- **Kein Sperren aus der Web-App.** Nur Entsperren. Ein „Session sperren"-Knopf
  wäre trivial nachzurüsten, wird aber nicht gebraucht.
- **Keine eigene Notification.** Das Entsperren begleitet immer ein „Displays
  an", das bereits eine auslöst.

## Architektur

```
backend/app/services/power/session_lock.py          NEU  ~130 Z.
backend/app/models/power_permissions.py             ÄND  + can_unlock_session
backend/alembic/versions/<rev>_…                    NEU  Spalte, server_default "0"
backend/app/services/power_permissions.py           ÄND  _ACTION_FIELD_MAP-Eintrag
backend/app/schemas/power_permissions.py            ÄND  Feld in Response + Update
backend/app/api/routes/desktop.py                   ÄND  enable() versucht Unlock
backend/app/plugins/base.py                         ÄND  run_menu_action-Kontext
backend/app/api/routes/plugins.py                   ÄND  reicht user + client_host durch
backend/app/plugins/installed/steam_gaming/__init__.py  ÄND  Gaming-Modus entsperrt
client/src/… (Power-Permissions-UI)                 ÄND  Checkbox für das neue Recht
```

### Trennung von Mechanismus und Policy

`session_lock.py` enthält beides, aber sauber getrennt:

- **Mechanismus** — `SessionLockBackend` (Protocol) mit `DevSessionLockBackend`
  (In-Memory, für Windows/Dev) und `LinuxSessionLockBackend` (`loginctl`).
  Spiegelt exakt das Muster von `desktop_backend.py`.
- **Policy** — die Modulfunktion `unlock_if_permitted(user, client_host, db)`.
  Sie ist die **einzige** Stelle, an der die beiden Gates ausgewertet werden.

Route und Plugin rufen dieselbe Funktion. Es gibt keine zweite Stelle, an der
jemand die Regeln nachbaut oder eine davon vergisst.

### Die zwei Gates

| Gate | Prüfung |
|---|---|
| Recht | `user.role == "admin"` **oder** `check_permission(db, user.id, "unlock_session")` |
| Ort | `is_private_or_local_ip(request.client.host)` (`core/network_utils.py`) |

**Achtung, stille Falle:** `check_permission()` schlägt die Aktion in
`_ACTION_FIELD_MAP` nach und gibt für einen unbekannten Schlüssel schlicht
`False` zurück (`services/power_permissions.py`). Wer nur die DB-Spalte und das
Schema ergänzt, aber den Map-Eintrag `"unlock_session" → "can_unlock_session"`
vergisst, bekommt kein Fehlerbild, sondern ein Feature, das für delegierte
Nutzer dauerhaft und begründungslos nicht funktioniert — fail-closed, aber
unsichtbar. Der Map-Eintrag gehört zum Pflichtumfang und braucht einen eigenen
Test.

Beide müssen zutreffen. Der Ortsfilter nutzt bewusst die **Client-IP**, nicht
`request.state.channel`: der Channel ist in Produktion hartverdrahtet `remote`
(er markiert den UDS-Pfad der Tauri-App) und würde jeden Browser aussperren —
eine Falle, die im Repo bereits einmal zugeschlagen hat. WireGuard-Clients haben
private Adressen und gelten damit als erlaubt; das ist beabsichtigt, denn wer im
VPN ist, hat sich bereits mit einem Schlüssel ausgewiesen.

**Tragende Annahme, benannt:** `request.client.host` ist hinter Nginx nur
deshalb die echte Client-IP, weil Uvicorn mit dem bestehenden
Proxy-Headers-Pin läuft (X-Forwarded-For, nur vom lokalen Nginx akzeptiert).
Ohne diesen Pin sähe jeder Request wie 127.0.0.1 aus und das Ortsgate wäre
dauerhaft offen. Der Pin existiert und trägt bereits die anderen LAN-Gates —
aber wer ihn je entfernt, entfernt damit auch diesen Riegel. Ein Test prüft
deshalb, dass eine öffentliche IP abgelehnt wird (nicht nur, dass eine private
durchkommt).

### Session-Ermittlung

Die Session-ID ist nicht stabil (die gemessene `2` gilt bis zum nächsten
Neustart), sie wird also zur Laufzeit ermittelt:

1. **Primär:** `loginctl show-user <uid> -p Display --value` — liefert die
   grafische Session des Nutzers.
2. **Fallback:** `loginctl list-sessions` und die erste Session dieses Nutzers
   mit Seat und Klasse `user`.

Beide Wege werden bei der Umsetzung gegen die Box gemessen. Dass
`unlock-session` funktioniert, ist belegt; **wie man die ID zuverlässig findet,
ist es noch nicht** — das ist die einzige offene Messfrage dieses Designs.

### Der Extension-Point

```python
async def run_menu_action(
    self, action_id: str, db: Session, *,
    user: Optional[UserPublic] = None,
    client_host: Optional[str] = None,
) -> Optional[MenuActionResult]:
```

Keyword-only mit Defaults, damit kein Implementierer bricht; `steam_gaming` ist
der einzige im Repo. Es werden **beide** Werte durchgereicht, nicht nur der Ort:
so ruft das Plugin dieselbe `unlock_if_permitted()` wie die Route, statt sich auf
den impliziten Vertrag „der Core hat Admin schon geprüft" zu verlassen. Solche
Verträge reißen beim nächsten Umbau, und zwar lautlos.

**Reihenfolge im Gaming-Modus:** Displays an → **Unlock** → Big Picture. Der
Unlock sitzt zwischen den beiden bestehenden Schritten — Big Picture auf einen
Sperrbildschirm zu öffnen ist genau das Szenario, das dieses Feature beseitigen
soll. Ein fehlgeschlagener Unlock bricht die Aktion nicht ab (Big Picture
startet trotzdem; es wird eben erst nach manuellem Entsperren sichtbar). Das
Zeitbudget bleibt eingehalten: Enable + Unlock-Polling (max. 3 s) + Spawn
liegen deutlich unter dem 20-s-Timeout der Menüaktionen.

### Kein neues Route-Gate

Das Recht wird **innerhalb** der Enable-Route geprüft, nicht als `Depends`. Ein
fehlendes Recht darf den Aufruf nicht mit 403 abweisen: Displays einschalten
muss weiterhin für jeden funktionieren, der es heute darf. Deshalb entsteht auch
keine `require_power_unlock_session`-Dependency.

### Antwortformat

```json
{
  "success": true,
  "message": "ok",
  "session_unlocked": false,
  "unlock_message": "not permitted from this network"
}
```

Präzise Semantik von `session_unlocked`, damit sie nicht zweideutig wird:

- **`true`** — beide Gates passiert, und die Session ist danach nachweislich
  entsperrt (`LockedHint=no`). Eine ohnehin unversperrte Session meldet `true`.
- **`false`** — alles andere: Gate verweigert (dann wurde `loginctl` nie
  gerufen und der tatsächliche Sperrzustand ist unbekannt), keine Session
  gefunden, Kommando fehlgeschlagen oder `LockedHint` blieb `yes`.
  `unlock_message` nennt den Grund.

Das Feld behauptet also nie mehr, als geprüft wurde — bei verweigerten Gates
sagt es nichts über den Sperrzustand aus, sondern nur, dass nicht entsperrt
wurde.

**Frontend-Verhalten:** `unlock_message` ist ein serverseitig englischer
Debug-String und wird **nicht** wörtlich gerendert — das wäre der nächste
Eintrag in #406. Die UI zeigt bei `session_unlocked=false` einen übersetzten,
generischen Hinweis (i18n-Key, de/en) und loggt `unlock_message` höchstens in
die Konsole.

## Fehlerbehandlung

**Grundregel: das Entsperren darf den Enable-Aufruf nie kippen.**

| Fall | Verhalten |
|---|---|
| Keine grafische Session gefunden | `session_unlocked=false` mit Begründung, Displays trotzdem an |
| Session war nicht gesperrt | `true` (Zustand danach) |
| Recht fehlt oder falsches Netz | `false` mit Begründung, kein 403, kein Audit-Eintrag |
| `loginctl` fehlt / Timeout | `false`, Warnung ins Log |
| kscreenlocker befolgt das Signal nicht | wird erkannt, siehe unten |

**Nachlesen statt vertrauen:** `loginctl unlock-session` liefert Exit 0, sobald
das Signal *abgesetzt* ist — ob der Locker es befolgt hat, steht auf einem
anderen Blatt. Deshalb wird nach dem Unlock `LockedHint` zurückgelesen und nur
bei `no` ein Erfolg gemeldet. Ohne diesen Schritt würde die API „entsperrt"
behaupten, während der Bildschirm gesperrt bleibt — eine Lüge, die man erst
bemerkt, wenn man vor dem Rechner steht.

**Das Nachlesen braucht ein Zeitfenster, kein Einzelread.** kscreenlocker
verarbeitet das Signal asynchron; die Messung auf der Box hatte zwischen Signal
und Nachlesen bewusst zwei Sekunden Pause. Ein sofortiger Read liefert
sporadisch noch `yes` und würde fälschlich „nicht entsperrt" melden — ein
flackernder Fehlbericht, der schwerer zu debuggen ist als ein ehrlicher.
Vorgabe: **Polling auf `LockedHint`, 200-ms-Schritte, Abbruch bei `no`,
Obergrenze 3 s.** Erst nach Ablauf der Obergrenze gilt der Unlock als
fehlgeschlagen.

## Sicherheit

- Kein sudo, keine sudoers-Änderung, kein neuer Rootpfad. Das Backend nutzt
  ausschließlich, was sein eigener User ohnehin darf.
- `loginctl` wird mit Argumentliste aufgerufen, nie als Zeichenkette. Die
  Session-ID stammt aus `loginctl` selbst und nie aus einer Benutzereingabe.
- **`unlock_if_permitted()` schreibt den Audit-Eintrag selbst**, nicht der
  Aufrufer. Damit kann kein Pfad protokolllos entsperren — auch der Gaming-Modus
  nicht. Erfolgreiche Unlocks werden als POWER-Event `desktop_unlock_session`
  geloggt, für delegierte Nutzer zusätzlich als `delegated_power_action`, analog
  zu den bestehenden Power-Routen. (#455 — dass der Gaming-Modus für den
  Display-Toggle generell kein POWER-Event schreibt — bleibt davon unberührt und
  offen.)

**Ausgesprochene Konsequenz:** Weil Admins die Power-Rechte per Rolle
durchlaufen, ist das Feature ab dem Deploy sofort scharf; es gibt keinen
Schalter, der erst umgelegt wird. Der Ortsfilter ist damit der einzige Riegel,
der ein übernommenes Admin-Konto aufhält. Aus dem offenen Netz geht nichts, aus
dem LAN und aus dem VPN schon.

## Tests

**`session_lock`** gegen einen injizierten Kommando-Runner (kein echtes
`loginctl`):

- Session-Ermittlung über den primären Weg;
- Fallback greift, wenn `Display` leer ist;
- keine Session vorhanden → sauberes `false` statt Absturz;
- Unlock erfolgreich (`LockedHint=no` danach);
- Unlock mit Exit ≠ 0;
- **`LockedHint` bleibt `yes` → es wird `false` gemeldet** (der Test, der die
  Nachlese-Regel festnagelt);
- Dev-Backend meldet Erfolg ohne `loginctl`.

**Policy-Matrix** für `unlock_if_permitted()`: Admin × LAN → entsperrt; Admin ×
extern → nein; delegiert mit Recht × LAN → ja; delegiert ohne Recht × LAN →
nein; Audit-Eintrag genau im Erfolgsfall.

**Route:** ein fehlgeschlagener Unlock lässt `enable` weiterhin `success=true`
liefern — der Test, der die Grundregel festnagelt. Dazu die beiden neuen
Antwortfelder, und ein Test, der eine **öffentliche** IP explizit ablehnt
(nicht nur eine private akzeptiert — sonst bliebe ein kaputtes Ortsgate
unsichtbar grün).

**Nachlese-Polling:** `LockedHint` wird erst nach mehreren Reads `no` →
Erfolg; bleibt es über die Obergrenze `yes` → `false`. Uhr und Runner
injiziert, kein echtes Warten im Test.

**Gaming-Modus:** reicht `user` und `client_host` durch und entsperrt unter
denselben Regeln.

**Migration:** `upgrade`/`downgrade` isoliert gegen SQLite **und** PostgreSQL
prüfen. Die Kette läuft nicht von null durch (#471), also wird das Schema
gestampt und nur das Delta gefahren — wie bei der `steam_sessions`-Migration.

## Offene Punkte

Drei Messungen stehen aus; die erste ist tragend und läuft als Aufgabe 1 des
Implementierungsplans, **bevor** Code entsteht:

1. **Funktioniert der Unlock aus einem session-losen Dienst-Kontext?** Die
   bisherige Messung lief aus einer SSH-Session; das Backend hat keine. Die
   ehrliche Simulation (transiente Unit unter `system.slice`, UID 1000, keine
   logind-Session):

   ```bash
   loginctl list-sessions   # grafische ID: seat0, Klasse user
   sudo systemd-run --uid=1000 --pipe --wait loginctl lock-session <ID>
   loginctl show-session <ID> -p LockedHint     # erwartet: yes
   sudo systemd-run --uid=1000 --pipe --wait loginctl unlock-session <ID>
   loginctl show-session <ID> -p LockedHint     # erwartet: no
   ```

   Fällt sie negativ aus, ist das Design neu abzuwägen (sudoers-Weg).
2. **Session-Ermittlung:** liefert `loginctl show-user 1000 -p Display --value`
   auf der Box die grafische Session? Sonst greift der Fallback über
   `list-sessions`.
3. **Visuelle Bestätigung**, dass der Sperrbildschirm wirklich verschwindet.
   `LockedHint` sprang auf `no`, und diesen Hint pflegt die Session-Software
   selbst — aber gesehen hat es noch niemand.
