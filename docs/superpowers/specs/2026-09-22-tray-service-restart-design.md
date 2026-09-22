# Dienste-Neustart aus dem Desktop-Tray — Design

**Datum:** 2026-09-22
**Status:** Entwurf, abgestimmt
**Basis:** `main` @ `14f9b650`
**Vorgänger:** `2026-09-21-desktop-tray-design.md` — dieses Dokument hebt dort
das Nicht-Ziel „Service-Steuerung" auf.

## Problem

BaluNode ist Server *und* Arbeitsplatz. Wenn die Anlage klemmt, sitzt der
Admin in aller Regel schon davor — und muss trotzdem einen Browser öffnen, sich
anmelden und die Web-UI durchklicken, um die Dienste neu zu starten. Das Tray
zeigt den Zustand bereits im Panel; der Schritt von „ich sehe, dass etwas nicht
stimmt" zu „ich kann es beheben" fehlt.

Schlimmer ist der Fall, in dem das Backend selbst hängt: dann ist die Web-UI
genau so tot wie die API, und der einzige verbleibende Weg ist eine Konsole mit
`sudo systemctl restart`. Das ist der Moment, für den man einen Knopf im Panel
will.

## Ziel

Ein Menüpunkt **„BaluHost neu starten…"** im Tray, der alle BaluHost-Units neu
startet — und zwar auch dann, wenn das Backend nicht mehr antwortet. Der
Neustart ist in beiden Fällen authentifiziert, mit dem Nachweis, der im
jeweiligen Zustand überhaupt prüfbar ist.

## Nicht-Ziele

- **Einzelne Units im Menü auswählen.** Ein Untermenü mit Zustand je Unit wäre
  ein zweiter Gesundheitsbegriff neben dem Meldungsbestand — genau das, was der
  Tray-Entwurf vermeidet. Alles oder nichts.
- **Stoppen und Starten.** Nur Neustart. Ein Tray, das Dienste dauerhaft
  ausschalten kann, lädt zu einem Zustand ein, den danach niemand mehr sieht.
- **Neustart der Maschine.** Dafür gibt es `scheduled_reboot` und die Web-UI.
- **Ein „Alles neu starten"-Knopf in der Web-UI.** Der neue Endpunkt könnte ihn
  bedienen; ob die Web-UI ihn bekommt, ist eine eigene Entscheidung über eine
  andere Oberfläche.
- **Nachträglicher Audit-Eintrag für den Notweg.** Siehe „Audit".

## Die vier Entscheidungen

| Frage | Entscheidung |
|---|---|
| Was wird neu gestartet? | Alle BaluHost-Units, Backend zuletzt |
| Auch bei totem Backend? | Ja, über einen Notweg am Backend vorbei |
| Womit ist der Notweg abgesichert? | polkit (`auth_admin_keep`), also die Systemanmeldung |
| Womit der Normalweg? | Step-up auf dem gekoppelten Konto: Passwort bzw. frisches TOTP |

Die beiden Wege haben verschiedene Gates, weil sie verschiedene Dinge prüfen
*können*. Solange das Backend lebt, ist „BaluHost-Admin" die richtige Frage und
auch beantwortbar. Ist es tot, kann niemand mehr gegen die Datenbank prüfen —
dann ist „darf diese Person an dieser Maschine Dienste verwalten?" die einzige
Frage, die noch eine ehrliche Antwort hat, und genau die beantwortet polkit.

## Architektur: zwei Wege, ein Menüpunkt

Beim Klick entscheidet das Tray **frisch**, welcher Weg gilt — nicht anhand der
Icon-Farbe. Die sagt nur, ob der WebSocket steht, und das ist nicht dasselbe wie
„API tot": ein abgelaufener ws-token oder eine Netzwerkdelle färben das Icon
grau, während `/api/health` tadellos antwortet. Also eine eigene Probe:
`GET /api/health` mit 2 s Timeout. Länger wäre im Notfall eine spürbare
Verzögerung vor dem Dialog, kürzer verwechselt eine langsame Antwort mit einem
toten Backend.

```
Klick
 ├── /api/health antwortet ──► Dialog (Passwort | 2FA-Code)
 │                              └─► POST /api/system/restart-all
 │                                   └─► Backend startet die Units
 └── antwortet nicht ────────► Bestätigungsdialog
                                └─► systemctl restart <unit> je Unit
                                     └─► KDE zeigt den polkit-Dialog
```

### Warum der Notweg keine neue Rechteregel braucht

Auf BaluNode verifiziert (2026-09-22), nicht angenommen:

- `org.freedesktop.systemd1.manage-units` steht auf `implicit active:
  auth_admin_keep` (`pkaction --verbose`).
- `polkitd` und `polkit-kde-auth` laufen in der Sitzung.
- `/usr/share/polkit-1/rules.d/50-default.rules` setzt `unix-group:sudo` als
  AdminIdentity; `sven` ist in dieser Gruppe.
- `pkcheck --action-id org.freedesktop.systemd1.manage-units --process $$`
  antwortet „Authorization requires authentication" mit
  `retains_authorization_after_challenge=1`.

Daraus folgt dreierlei. Erstens: **kein eigener polkit-Policy-File und keine
sudoers-Zeile für den Desktop-Nutzer** — systemd bringt die Aktion mit, und sie
ist bereits richtig eingestellt. Zweitens: `NoNewPrivileges=yes` in
`baluhost-tray.service` **bleibt**. `systemctl` eskaliert nichts im eigenen
Prozess; es spricht über D-Bus mit systemd, und systemd fragt polkit nach dem
Aufrufer. Drittens: Wegen `auth_admin_keep` erscheint der Passwortdialog
**einmal** und deckt alle vier Neustarts ab.

Ist der Desktop-Nutzer *nicht* in der Gruppe `sudo`, fragt polkit nach dem
Passwort eines anderen Admins. Das ist kein Fehler, sondern die richtige
Antwort — gehört aber in die Installationsdoku, sonst liest sich der Dialog wie
eine Störung.

### Sichtbarkeit des Menüpunkts

Sichtbar, wenn das gekoppelte Konto Admin ist (`GET /api/auth/me` beim Start und
nach jedem erfolgreichen Reconnect) **oder** die API gerade nicht erreichbar ist.

Die zweite Bedingung ist der Punkt: Ohne sie fehlte der Knopf ausgerechnet im
Notfall — Backend seit der Anmeldung tot, Rolle deshalb nie erfahren. Sie
schwächt nichts, weil auf diesem Weg ohnehin polkit entscheidet und nicht die
Sichtbarkeit eines Menüeintrags.

## Backend: `POST /api/system/restart-all`

Neuer Endpunkt neben dem bestehenden `/api/system/restart`, das unverändert
bleibt (`localApi.ts:313` und die Companion-App benutzen es).

**Auth:** `Depends(deps.get_current_admin)` **plus** Step-up nach dem Muster von
`/api/auth/recovery-codes` (`auth.py:570`): frisches TOTP prüfen, wenn
`totp_enabled` gesetzt ist, sonst `current_password` gegen
`authenticate_user()`. Fehlschlag → 401 und `log_security_event`.

**Der 401-Body ist Teil des Vertrags.** Ein fehlgeschlagener Step-up antwortet
strukturiert:

```json
{"detail": {"error": "step_up_failed", "message": "..."}}
```

Ohne diese Unterscheidung kann das Tray „falsches Passwort" nicht von
„Access-Token abgelaufen" trennen — beides ist 401, beides braucht eine andere
Reaktion. Muster dafür gibt es bereits (`local_channel_required`,
`deps.py:188`).

**Schemata** (nach `schemas/`-Konvention, kein rohes `dict`):

```python
class SystemRestartAllRequest(BaseModel):
    current_password: str | None = None   # wenn 2FA aus
    code: str | None = None               # frisches TOTP, wenn 2FA an

class UnitRestartResult(BaseModel):
    name: str
    success: bool
    message: str | None = None

class SystemRestartAllResponse(BaseModel):
    units: list[UnitRestartResult]        # die drei synchron gestarteten
    backend_restart_scheduled: bool
    eta_seconds: int
    initiated_by: str
```

`baluhost-backend` taucht **nicht** in `units` auf: sein Ergebnis ist zum
Antwortzeitpunkt noch nicht bekannt, und ein Feld, das immer „geplant"
bedeutet, gehört nicht in dieselbe Liste wie echte Ergebnisse.

**Rate-Limit:** eigener Schlüssel `system_restart` mit `5/minute`.
`admin_operations` wäre für einen Endpunkt, der ein Passwort entgegennimmt, zu
locker; der Wert entspricht `auth_password_change`.

**Reihenfolge und Ausführung:**

1. `baluhost-scheduler`, `baluhost-monitoring`, `baluhost-webdav` **synchron**,
   je `sudo systemctl restart <unit>` in `asyncio.to_thread` mit Timeout. Das
   Ergebnis jeder Unit steht in der Antwort — nur so erfährt der Nutzer von
   einem Fehlschlag.
2. `baluhost-backend` **zuletzt**, per Timer-Thread nach 1 s, wie es
   `/api/system/restart` heute schon tut (`system.py:272`). Die Antwort muss
   raus sein, bevor der Prozess stirbt. Dass er wiederkommt, sieht man am
   Tray-Icon.

`baluhost-backend-local` bleibt außen vor: socket-aktiviert, die Socket-Unit
startet sie bei Bedarf selbst.

**Keine sudoers-Erweiterung.** Alle vier Zeilen stehen bereits in
`deploy/install/templates/baluhost-deploy-sudoers`; `/etc/sudoers.d/baluhost-deploy`
auf BaluNode ist aktuell (2026-09-22 14:22, Größe passend zum Template).

**Dev-Mode:** kein `systemctl` — SIGINT auf den eigenen Prozess wie bisher. Die
übrigen Units existieren dort nicht.

## Tray

**Neues Modul `backend/baluhost_tray/restart.py`, ohne Qt** — wie `loop.py` und
`state.py`. Dort liegt alles Entscheidbare:

| Funktion | Aufgabe |
|---|---|
| `probe_api(client)` | `GET /api/health`, kurzer Timeout, liefert erreichbar ja/nein |
| `restart_via_api(client, secret)` | der POST samt Abbildung von 401/403/429/5xx/Netzwerkfehler auf Klartext |
| `restart_via_systemctl(runner, units)` | `systemctl restart` je Unit; `runner` injiziert, Vorgabe `subprocess.run` |

`UNITS = ("baluhost-scheduler", "baluhost-monitoring", "baluhost-webdav",
"baluhost-backend")` — dieselbe Reihenfolge wie im Backend. Auf dem Notweg wäre
sie technisch gleichgültig, aber ein Ablauf im Kopf ist besser als zwei.

Diese Liste steht damit zweimal im Repo. Das Tray kann sie nicht vom Backend
holen — auf dem Notweg ist es ja tot. Ein Test in `backend/tests/` importiert
beide und prüft auf Gleichheit; läuft die Liste auseinander, fällt es beim
nächsten Lauf auf.

**Eigener `BackendClient` für den Neustart**, nicht der aus der Schleife: der
Worker-Thread mutiert dessen Token beim Refresh, und zwei Threads auf demselben
Objekt sind eine Verabredung zum Rennen.

**`tray.py` bleibt dünn.** Menüpunkt, `QInputDialog` mit `EchoMode.Password`,
`QMessageBox` für Bestätigung und Ergebnis. Der Ablauf geht über zwei neue
Signale des vorhandenen `_Bridge`, weil Dialoge auf den GUI-Thread gehören und
Netzwerk nicht:

1. Klick → Aktion wird deaktiviert (kein Doppelstart) → Arbeitsthread probt die
   API.
2. `restart_prompt(str)` → GUI zeigt den passenden Dialog (Passwort, 2FA-Code
   oder Notweg-Bestätigung) und reicht die Eingabe zurück.
3. `restart_finished(str)` → GUI zeigt das Ergebnis, Aktion wieder aktiv.

Das Label des Eingabefelds kommt aus `GET /api/auth/2fa/status` (`auth.py:438`).
Sonst stünde „Passwort" über einem Feld, das einen TOTP-Code erwartet.

## Fehlerfälle

Jeder Fall bekommt eine eigene Meldung. Der Grund steht in den ersten beiden
Zeilen: „falsches Passwort" und „Kopplung abgelaufen" sind beide 401 und
bedeuten Verschiedenes.

| Fall | Erkennung | Verhalten |
|---|---|---|
| Step-up falsch | 401 mit `error: step_up_failed` | „Passwort falsch", ein erneuter Versuch; nach 3 Schluss (Limit 5/min) |
| Token abgelaufen | einfaches 401 aus `get_current_user` | einmal `refresh_access()`, dann Wiederholung; scheitert auch das → „Kopplung abgelaufen, `baluhost-tray --pair`" |
| Kein Admin | 403 | Meldung; sollte nicht auftreten, da der Eintrag verborgen ist |
| Zu viele Versuche | 429 | „In einer Minute erneut" |
| Eine Unit scheitert | Status je Unit in der Antwort | Dialog benennt die betroffene Unit |
| polkit abgebrochen oder verweigert | `systemctl` exit ≠ 0 | „Abgebrochen bzw. keine Berechtigung" |
| Kein polkit-Agent, keine Sitzung | Fehlerausgabe von `systemctl` | ausdrücklich benennen statt stumm scheitern |
| API stirbt zwischen Probe und Aufruf | Netzwerkfehler nach erfolgreicher Probe | anbieten, auf den Notweg zu wechseln |

## Audit

**Normalweg:** `log_system_event(action="restart_all_initiated", …)` mit den
Unit-Ergebnissen; fehlgeschlagener Step-up als `log_security_event`.

**Notweg: kein App-Audit.** Das Backend ist tot, es kann nichts schreiben. Die
Spur liegt im Journal — polkitd protokolliert die Autorisierung, systemd den
Neustart.

Ein Nachtrag-Endpunkt, der den Eintrag nachreicht, sobald die API wieder
antwortet, wird **bewusst nicht** gebaut: ein vom Client behaupteter
Audit-Eintrag ist schwächeres Beweismaterial als die Zeile, die systemd selbst
geschrieben hat, und er verlängert die Kette um einen Endpunkt, der fremde
Behauptungen über die Vergangenheit annimmt. Die Lücke gehört stattdessen
ausdrücklich in die „Known Gaps" von `security-agent.md`.

## Sicherheitsbetrachtung

**Was neu hinzukommt:** Das Tray erhält seinen ersten ausgehenden,
zustandsändernden Pfad. Der Tray-Entwurf sagte „es zeigt und meldet, es bedient
nicht" — das gilt ab hier nicht mehr, und die Zusage „fasst nichts
Privilegiertes an" wird auf dem Notweg eingelöst durch polkit statt durch
Verzicht.

**Bedrohungsmodell.** Der Angreifer, der hier zählt, ist jemand an einer
unbeaufsichtigt entsperrten Desktop-Sitzung, oder Code, der als Desktop-Nutzer
läuft. Für beide gilt:

- Der Normalweg verlangt das BaluHost-Passwort bzw. ein frisches TOTP. Das
  gekoppelte Token allein reicht **nicht**, obwohl es technisch ein
  Admin-Token ist — genau das ist der Zweck des Step-ups.
- Der Notweg verlangt die polkit-Authentifizierung. Eine NOPASSWD-Zeile hätte
  den Dialog im Tray zur Dekoration gemacht: das eigentliche Gate ist die
  Rechteregel, nicht die Abfrage im unprivilegierten Prozess.

**Blast radius:** Neustart, kein Datenzugriff. Der Schaden ist eine
Unterbrechung von Sekunden, kein Verlust und keine Offenlegung. Das rechtfertigt
die Abwägung, ein Passwortfeld in einem Tray zu haben — nicht mehr.

**Was ausdrücklich nicht passiert:** kein neues Recht für den `baluhost`-Nutzer,
keine neue sudoers-Zeile, kein neuer polkit-Policy-File, keine Änderung an
`NoNewPrivileges=yes`.

## Tests

Nach der Vorgehensweise des Repos: Test zuerst.

**Backend**
- Step-up richtig, falsch, und die 2FA-Variante (frisches TOTP statt Passwort).
- Nicht-Admin → 403; ohne Token → 401.
- Reihenfolge mit gefaktem `subprocess`: `baluhost-backend` kommt zuletzt.
- Eine scheiternde Unit erscheint als Fehlschlag in der Antwort, ohne die
  übrigen zu verhindern.
- Dev-Mode-Zweig ruft kein `systemctl`.
- Audit-Einträge für Erfolg und für den fehlgeschlagenen Step-up.
- Rate-Limit-Schlüssel ist gesetzt.

**Tray**
- `restart.py` vollständig ohne Qt: Pfadwahl bei erreichbarer und bei toter API,
  401-Refresh-Retry, jede Zeile der Fehlertabelle, `systemctl`-Aufrufe über den
  injizierten Runner in der richtigen Reihenfolge, Abbruch durch polkit.
- Sichtbarkeitsregel des Menüpunkts (Admin oder API unerreichbar) als reine
  Funktion.

**Übergreifend**
- Gleichheit der Unit-Listen in Tray und Backend.

Kein Qt-Test für den Dialog: die Codebasis testet Qt nirgends, und ein Dialog,
der nur Eingaben weiterreicht, trägt keine Logik.

## Doku und Regeln

Teil der Arbeit, nicht Anhängsel:

- Im Tray-Entwurf vom 2026-09-21 das Nicht-Ziel „Service-Steuerung" als überholt
  markieren, mit Verweis hierher — nicht löschen.
- `.claude/rules/security-agent.md`: Step-up-Pflicht auf `/api/system/restart-all`
  sowie der Notweg samt Audit-Lücke unter „Known Gaps & Accepted Risks".
- `.claude/rules/architecture.md`: API-Liste um den neuen Endpunkt ergänzen.
- Installationsdoku des Trays: Der Desktop-Nutzer muss in der Gruppe `sudo`
  sein, sonst fragt polkit nach dem Passwort eines anderen Admins.
