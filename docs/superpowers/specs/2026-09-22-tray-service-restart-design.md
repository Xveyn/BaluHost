# Dienste-Neustart aus dem Desktop-Tray — Design

**Datum:** 2026-09-22
**Status:** Entwurf, überarbeitet nach kritischem Review (zwei Subagenten, 2026-09-22)
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
- **Den Step-up auf `/api/system/restart` nachziehen.** Die Nachbarroute startet
  `baluhost-backend` weiterhin ohne zweiten Nachweis; sie zu ändern bricht
  Companion-App und Web-UI. Issue #699 — und bis dahin steht die Einschränkung
  ausdrücklich in `security-agent.md`, statt dass der Step-up mehr verspricht,
  als die Route-Familie einlöst.
- **Nachträglicher Audit-Eintrag für den Notweg.** Siehe „Audit".

## Die vier Entscheidungen

| Frage | Entscheidung |
|---|---|
| Was wird neu gestartet? | Alle fünf BaluHost-Units, Backend zuletzt |
| Auch bei totem Backend? | Ja, über einen Notweg am Backend vorbei |
| Womit ist der Notweg abgesichert? | polkit (`auth_admin_keep`), also die Systemanmeldung |
| Womit der Normalweg? | Step-up auf dem gekoppelten Konto: Passwort bzw. TOTP |

Die beiden Wege haben verschiedene Gates, weil sie verschiedene Dinge prüfen
*können*. Solange das Backend lebt, ist „BaluHost-Admin" die richtige Frage und
auch beantwortbar. Ist es tot, kann niemand mehr gegen die Datenbank prüfen —
dann ist „darf diese Person an dieser Maschine Dienste verwalten?" die einzige
Frage, die noch eine ehrliche Antwort hat, und genau die beantwortet polkit.

## Die Units

```
baluhost-scheduler        \
baluhost-monitoring        |  synchron, Ergebnis je Unit in der Antwort
baluhost-webdav            |
baluhost-backend-local    /
baluhost-backend             zuletzt, per Timer nach der Antwort
```

`baluhost-backend` steht zuletzt, weil sein Neustart auf dem API-Weg den
Prozess beendet, der die Sequenz ausführt.

`baluhost-backend-local` ist **dabei**, obwohl sie socket-aktiviert ist. Der
erste Entwurf ließ sie mit der Begründung weg, die Socket-Unit starte sie bei
Bedarf selbst — das ist falsch: die Unit ist `Type=simple` mit
`Restart=on-failure`, sie läuft nach dem ersten Verbindungsaufbau dauerhaft
(auf BaluNode am 2026-09-22 als `ActiveState=active`, `MainPID=398735`,
`TriggeredBy=baluhost-backend-local.socket` nachgesehen). Ohne sie liefe der
Companion-Kanal nach „BaluHost neu starten" mit altem Code weiter, und der
Menüpunkt verspräche etwas, das er nicht hält.

**Das kostet eine sudoers-Zeile.** `deploy/install/templates/baluhost-deploy-sudoers`
kennt heute vier Units, nicht fünf. Die fünfte Zeile hat dieselbe Form wie die
vorhandenen — ein fester Pfad, ein Verb, genau eine Unit, keine Platzhalter —
und erweitert den Radius um dieselbe Klasse von Befehl, die der Nutzer dort
schon hat. Die Zusage des ersten Entwurfs („keine sudoers-Erweiterung") gilt
damit nicht mehr; sie galt ohnehin nur für den Notweg, der weiterhin ohne
auskommt.

Ein Test hält beides zusammen: die sudoers-Vorlage muss genau die Units
abdecken, die `BALUHOST_UNITS` nennt.

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
                                └─► ein systemctl-Aufruf für alle fünf Units
                                     └─► KDE zeigt den polkit-Dialog
```

### Der Notweg und polkit

Auf BaluNode verifiziert (2026-09-22):

- `org.freedesktop.systemd1.manage-units` steht auf `implicit active:
  auth_admin_keep` (`pkaction --verbose`).
- `polkitd` und `polkit-kde-auth` laufen in der Sitzung.
- `/usr/share/polkit-1/rules.d/50-default.rules` setzt `unix-group:sudo` als
  AdminIdentity; `sven` ist in dieser Gruppe.
- `pkcheck --action-id org.freedesktop.systemd1.manage-units --process $$`
  antwortet „Authorization requires authentication" mit
  `retains_authorization_after_challenge=1`.

Daraus folgt: **kein eigener polkit-Policy-File und keine sudoers-Zeile für den
Desktop-Nutzer.** systemd bringt die Aktion mit, und sie ist bereits richtig
eingestellt. `NoNewPrivileges=yes` in `baluhost-tray.service` **bleibt** —
`systemctl` eskaliert nichts im eigenen Prozess, es spricht über D-Bus mit
systemd, und systemd fragt polkit nach dem Aufrufer.

**Was `auth_admin_keep` nicht bedeutet.** Der erste Entwurf schloss daraus, der
Dialog erscheine einmal und decke alle Units ab. Das ist falsch: die temporäre
Autorisierung hängt am **anfragenden Prozess** — `subject_equal_for_authz()`
vergleicht über `polkit_unix_process_equal()`, das PID-Gleichheit verlangt, und
eine Autorisierung mit Prozess-Subjekt wird entfernt, sobald der Prozess
verschwindet (polkit 126). Fünf einzelne `systemctl`-Aufrufe wären fünf
Prozesse und damit **fünf Dialoge**.

**Deshalb ein einziger Aufruf:** `systemctl restart <alle fünf Units>`. Ein
Prozess, fünf D-Bus-Aufrufe, ein Dialog. Der Zustand je Unit kommt danach aus
einem zweiten, lesenden Aufruf `systemctl is-active <alle fünf>` — der braucht
keine Autorisierung und keinen Dialog.

**Und deshalb diese Regel, die hier festgehalten werden muss:** Der Notweg
startet je Aufruf einen **kurzlebigen** `systemctl`-Prozess. Wer das später
„optimiert" und stattdessen `org.freedesktop.systemd1.Manager.RestartUnit`
direkt aus dem langlebigen Tray-Prozess über D-Bus ruft, erzeugt mit derselben
einen Passworteingabe ein **Fünf-Minuten-Fenster, in dem der Tray-Prozess
`manage-units` ohne jede weitere Abfrage ausführen darf**. `manage-units` deckt
auch `StartTransientUnit` ab — das ist `systemd-run` als root, also beliebige
Codeausführung. Die kurze Prozesslebensdauer ist kein Implementierungsdetail,
sie ist das, was den Radius klein hält.

Ist der Desktop-Nutzer *nicht* in der Gruppe `sudo`, fragt polkit nach dem
Passwort eines anderen Admins. Das ist kein Fehler, sondern die richtige
Antwort — gehört aber in die Feature-Doku, sonst liest sich der Dialog wie eine
Störung.

### Sichtbarkeit des Menüpunkts

Sichtbar, wenn das gekoppelte Konto Admin ist **oder** die Rolle nicht
ermittelbar war **oder** die API gerade nicht erreichbar ist. Verborgen also
nur im einen Fall: „wir haben gefragt, und das Konto ist kein Admin".

Ohne den mittleren Zweig fehlte der Knopf ausgerechnet im Notfall — Backend
seit der Anmeldung tot, Rolle deshalb nie erfahren. Er schwächt nichts, weil auf
diesem Weg ohnehin polkit entscheidet und nicht die Sichtbarkeit eines
Menüeintrags.

Die Rolle wird beim Start ermittelt und nach jedem erfolgreichen Reconnect
aufgefrischt. Ein abgelaufener Access-Token darf dabei nicht als „keine Rolle"
durchgehen — siehe „Der Stolperstein beim abgelaufenen Token".

## Backend: `POST /api/system/restart-all`

Neuer Endpunkt neben dem bestehenden `/api/system/restart`, das unverändert
bleibt (`localApi.ts:313` und die Companion-App benutzen es; Issue #699).

**Auth, drei Ebenen:**

1. `Depends(deps.get_current_admin)`.
2. **LAN-Gate:** `is_private_or_local_ip(request.client.host)`, sonst 403 mit
   `{"error": "local_network_required"}` und `log_security_event` samt IP —
   nach dem Muster von `/api/auth/recovery-reset` (`auth.py:629`). Das Tray
   spricht `http://localhost:8000`, es kostet also nichts. Begründung: `uvicorn`
   lauscht auf `0.0.0.0:8000` und es läuft kein Paketfilter (Issue #698) — der
   Endpunkt wäre sonst aus LAN und VPN **an nginx und dessen Rate-Limits vorbei**
   erreichbar. VPN-Adressen gelten wie überall im Projekt als privat.
3. **Step-up:** frisches TOTP, wenn `totp_enabled`, sonst `current_password`
   gegen `authenticate_user` — nach dem Muster von `/api/auth/recovery-codes`
   (`auth.py:570`). Fehlschlag → 401 und `log_security_event`.

**API-Keys werden abgelehnt.** `request.state.auth_method == "api_key"` → 403.
Zwei Gründe: ein Step-up soll Anwesenheit eines Menschen belegen, und ein
API-Key kann das nicht; und `get_user_identifier` (`rate_limiter.py:307`)
versteht nur JWTs, ein Key-Aufrufer fiele auf den **IP**-Schlüssel zurück und
könnte das Limit über beliebig viele Quell-IPs im VPN-Subnetz aufweichen.

**Der 401-Body ist Teil des Vertrags.** Ein fehlgeschlagener Step-up antwortet
strukturiert:

```json
{"detail": {"error": "step_up_failed", "totp_required": true, "message": "..."}}
```

Ohne diese Unterscheidung kann das Tray „falsches Passwort" nicht von
„Access-Token abgelaufen" trennen — beides ist 401, beides braucht eine andere
Reaktion. `totp_required` sagt dem Client zusätzlich, welches Feld die Route
erwartet; es ist die zuverlässigere Quelle als ein vorher abgefragter
2FA-Status, der bei abgelaufenem Token leer zurückkommt. Muster für den
strukturierten Body: `local_channel_required` (`deps.py:188`).

**Rate-Limit:** `user_limiter` mit dem neuen Schlüssel `system_restart`
(`5/minute`). Nur dieser eine — zwei gestapelte Limiter-Dekoratoren kommen im
Projekt nirgends vor, und sie brächten hier nichts: der Angreifer, um den es
geht, hält ein gültiges Admin-Token und sitzt hinter *einer* IP, sein
Kontoschlüssel ist also die engere Grenze. Die Lücke, die das Review zu Recht
benannt hat — ein API-Key-Aufrufer fällt in `get_user_identifier` auf den
IP-Schlüssel zurück —, schließt die Ablehnung von API-Keys, nicht ein zweiter
Limiter.

Was dieses Limit **nicht** leistet, gehört dazugesagt: Es liegt im
Prozessspeicher, gilt also pro uvicorn-Worker (vier davon, ohne `ip_hash` im
nginx-Upstream), und der Endpunkt startet genau diese Prozesse neu — ein
Angreifer mit Admin-Token kann seine eigenen Zähler über
`/api/system/restart` zurücksetzen. Ein belastbarer Schutz wäre ein
persistenter Fehlversuchszähler am Konto, wie ihn `pin_failed_attempts` schon
hat. Das ist bewusst nicht Teil dieser Runde, steht aber als Gap in
`security-agent.md` statt als Behauptung in einem Test.

**Schemata** (nach `schemas/`-Konvention, kein rohes `dict`):

```python
class SystemRestartAllRequest(BaseModel):
    current_password: str | None = None   # wenn 2FA aus
    code: str | None = None               # TOTP oder Backup-Code, wenn 2FA an

class UnitRestartResult(BaseModel):
    name: str
    success: bool
    message: str | None = None

class SystemRestartAllResponse(BaseModel):
    units: list[UnitRestartResult]        # die vier synchron gestarteten
    backend_restart_scheduled: bool
    eta_seconds: int
    initiated_by: str
```

`baluhost-backend` taucht **nicht** in `units` auf: sein Ergebnis ist zum
Antwortzeitpunkt noch nicht bekannt, und ein Feld, das immer „geplant"
bedeutet, gehört nicht in dieselbe Liste wie echte Ergebnisse.

**Ausführung:**

1. Die vier Nebendienste synchron, je `sudo systemctl restart <unit>` in
   `asyncio.to_thread` mit Timeout. Ein Fehlschlag bricht nicht ab.
2. `baluhost-backend` zuletzt, per Timer-Thread nach 1 s — die Antwort muss
   raus sein, bevor der Prozess stirbt.

**Kein SIGINT-Fallback.** Schlägt `systemctl restart baluhost-backend` fehl,
wird das protokolliert und sonst nichts getan. Der Fallback im bestehenden
`/api/system/restart` (`os.kill(os.getpid(), SIGINT)`) ist in Produktion
sachlich falsch: bei `--workers 4` trifft er einen Kindprozess, den uvicorn
binnen ~0,5 s neu startet, während drei Worker unverändert weiterlaufen und dem
Aufrufer „Neustart geplant" gemeldet wurde. Issue #695. Dieser Entwurf
übernimmt den Defekt nicht.

**Dev-Mode:** kein `systemctl` — SIGINT auf den eigenen Prozess wie bisher. Dort
läuft ein einzelner Prozess, dort stimmt es.

## Tray

**Neues Modul `backend/baluhost_tray/restart.py`, ohne Qt** — wie `loop.py` und
`state.py`. Dort liegt alles Entscheidbare:

| Funktion | Aufgabe |
|---|---|
| `probe_api(client)` | `GET /api/health`, 2 s, liefert erreichbar ja/nein |
| `fetch_account_facts(client, on_auth_expired)` | Rolle und 2FA-Zustand; einmaliger Refresh bei 401 |
| `restart_via_api(client, secret, totp, on_auth_expired)` | der POST samt Abbildung aller Fehlerfälle auf Klartext |
| `restart_via_systemctl(runner, units)` | **ein** `systemctl restart` für alle Units, danach `is-active` je Unit |
| `restart_flow(...)` | proben, fragen, Weg wählen, bis zu drei Versuche |
| `menu_visible(is_admin, api_reachable)` | die Sichtbarkeitsregel als reine Funktion |

`UNITS` steht damit zweimal im Repo. Das Tray kann die Liste nicht vom Backend
holen — auf dem Notweg ist es tot. Ein Test prüft beide auf Gleichheit.

**Eigener `BackendClient` für den Neustart**, nicht der aus der Schleife: der
Worker-Thread mutiert dessen Token beim Refresh, und zwei Threads auf demselben
Objekt sind eine Verabredung zum Rennen.

**`tray.py` bleibt dünn.** Menüpunkt, `QInputDialog`, `QMessageBox`. Der Ablauf
geht über Bridge-Signale, weil Dialoge auf den GUI-Thread gehören und Netzwerk
nicht; die Antwort des Dialogs kommt über eine `queue.Queue` zurück in den
Arbeitsthread.

### Der Stolperstein beim abgelaufenen Token

Der Normalfall beim Tray-Start ist ein abgelaufener Access-Token — dafür gibt es
seit #692 den Refresh im Abgleich. `fetch_account_facts` muss denselben Weg
gehen: ohne Refresh liefert ein 401 auf `/api/auth/me` „Rolle unbekannt, 2FA
aus", und ein 2FA-Konto würde dreimal nach einem Passwort gefragt, das die
Route gar nicht akzeptiert. Deshalb refresht `fetch_account_facts` einmal und
fragt erneut — und der 401-Body der Route trägt zusätzlich `totp_required`, so
dass der Dialog auch dann noch umschwenken kann.

### Timeout ist nicht dasselbe wie „Backend tot"

`restart_via_api` unterscheidet `httpx.TimeoutException` von den übrigen
Transportfehlern. Der Grund: die Route startet vier Units synchron, das dauert
im schlechtesten Fall so lange wie vier Unit-Timeouts. Würde ein Timeout wie ein
Verbindungsabbruch behandelt, böte das Tray den Notweg an — und der Nutzer
startete über polkit alle fünf Units ein zweites Mal, auf einem Backend, das
gerade dabei ist, sie ordentlich neu zu starten. Ein Timeout meldet deshalb
„dauert länger als erwartet, bitte Status prüfen" und bietet **nichts** an.

## Fehlerfälle

| Fall | Erkennung | Verhalten |
|---|---|---|
| Step-up falsch | 401 mit `error: step_up_failed` | „Passwort bzw. Code stimmt nicht", erneut fragen; nach 3 Versuchen Schluss |
| Token abgelaufen | einfaches 401 aus `get_current_user` | einmal `refresh_access()`, dann wiederholen; scheitert auch das → „Kopplung abgelaufen, `baluhost-tray --pair`" |
| Kein Admin | 403 | Meldung; Eintrag sollte ohnehin verborgen sein |
| Nicht aus dem lokalen Netz | 403 `local_network_required` | Meldung; im Betrieb unmöglich, das Tray spricht localhost |
| Zu viele Versuche | 429 | „In einer Minute erneut" |
| Eine Unit scheitert | Status je Unit in der Antwort | Dialog benennt die betroffene Unit |
| Zeitüberschreitung | `httpx.TimeoutException` | „dauert länger als erwartet", **kein** Wechsel auf den Notweg |
| API stirbt mitten im Aufruf | anderer Transportfehler nach grüner Probe | Notweg anbieten |
| polkit abgebrochen oder verweigert | `systemctl` exit ≠ 0 | „Abgebrochen bzw. keine Berechtigung", plus welche Units laut `is-active` trotzdem laufen |
| Kein polkit-Agent, kein systemctl | `FileNotFoundError`/Fehlerausgabe | ausdrücklich benennen statt stumm scheitern |

## Audit

**Normalweg:** `log_system_event(action="restart_all_initiated", …)` mit den
Unit-Ergebnissen; fehlgeschlagener Step-up und abgelehntes LAN-Gate als
`log_security_event` samt IP.

**Notweg: kein App-Audit.** Das Backend ist tot, es kann nichts schreiben. Die
Spur liegt im Journal — aber nur zur Hälfte, und das gehört genau so
aufgeschrieben:

- polkitd protokolliert Nutzer, Aktion, anfragenden Prozess und Zeit
  („Operator of unix-session:3 successfully authenticated as unix-user:sven to
  gain TEMPORARY authorization for action org.freedesktop.systemd1.manage-units
  …"). Das Journal ist persistent (`/var/log/journal`).
- **systemd nennt keinen Urheber.** Seine Zeile lautet „Restarted
  baluhost-webdav.service" — wer das ausgelöst hat, steht nur in der
  polkitd-Zeile.
- **Ein abgebrochener Dialog hinterlässt nichts.** Ein Abbruch ist kein
  fehlgeschlagener Authentisierungsversuch; ein versuchter, abgebrochener
  Notweg ist im Journal unsichtbar.

Ein Nachtrag-Endpunkt, der den Eintrag nachreicht, sobald die API wieder
antwortet, wird **bewusst nicht** gebaut: ein vom Client behaupteter
Audit-Eintrag ist schwächeres Beweismaterial als die Zeile, die polkitd selbst
geschrieben hat, und er verlängert die Kette um einen Endpunkt, der fremde
Behauptungen über die Vergangenheit annimmt. Die Lücke gehört mit allen drei
Einschränkungen in die „Known Gaps" von `security-agent.md`.

## Sicherheitsbetrachtung

**Was neu hinzukommt:** Das Tray erhält seinen ersten ausgehenden,
zustandsändernden Pfad. Der Tray-Entwurf sagte „es zeigt und meldet, es bedient
nicht" — das gilt ab hier nicht mehr.

**Bedrohungsmodell.** Der Angreifer, der hier zählt, ist jemand an einer
unbeaufsichtigt entsperrten Desktop-Sitzung, oder Code, der als Desktop-Nutzer
läuft. Für beide gilt:

- Der Normalweg verlangt das BaluHost-Passwort bzw. einen TOTP-Code. Das
  gekoppelte Token allein reicht für **diesen Endpunkt** nicht.
- Der Notweg verlangt die polkit-Authentifizierung. Eine NOPASSWD-Zeile hätte
  den Dialog im Tray zur Dekoration gemacht: das eigentliche Gate ist die
  Rechteregel, nicht die Abfrage im unprivilegierten Prozess.

**Was der Step-up nicht leistet.** Dieselbe Token startet `baluhost-backend`
weiterhin über `POST /api/system/restart` ohne zweiten Nachweis (Issue #699).
Der Step-up schützt den *Sammel*neustart, nicht die Fähigkeit „Backend neu
starten" als solche. Das steht so auch in `security-agent.md` — eine
Regelzeile, die mehr behauptet, wäre schlimmer als keine.

**Was „frisches TOTP" wirklich heißt.** Akzeptiert wird ein gültiger Code im
aktuellen ±1-Zeitfenster (~90 s) **oder ein Backup-Code**. Eine Frischeprüfung
gibt es nicht — derselbe Code ist im Fenster mehrfach verwendbar, auf allen
Step-up-Routen des Projekts (Issue #697). Der Entwurf übernimmt das vorhandene
Verhalten und benennt es, statt es weiterzubehaupten.

**Blast radius.** Nicht „eine Unterbrechung von Sekunden, kein Verlust" — das
war im ersten Entwurf zu optimistisch:

- `SchedulerWorker._recover_stale_executions()` markiert beim Start **jede**
  `RUNNING`-Ausführung als `CANCELLED`. Ein laufendes Backup, ein Sync oder ein
  RAID-Job wird abgebrochen, nicht fortgesetzt.
- Laufende Uploads sterben: `lifespan.py` räumt `upload_progress` und
  `chunked_upload` beim Herunterfahren ab.
- Der Sleep-Manager samt `CoreUptimeRtcGuard` läuft im Backend-Prozess und hält
  die systemd-Inhibitoren. Zwischen Stopp und erneutem Start (`RestartSec` plus
  Startzeit) gibt es ein Fenster, in dem ein Suspend durchgeht, ohne dass der
  RTC-Wecker gestellt wird.

Deshalb benennt der Bestätigungs- bzw. Passwortdialog, dass laufende Aufträge
und Uploads abgebrochen werden. Der Neustart bleibt trotzdem verhältnismäßig —
er ist eine Unterbrechung, kein Datenabfluss — aber der Nutzer soll wissen,
was er auslöst.

**Was ausdrücklich nicht passiert:** kein neues Recht für den Desktop-Nutzer,
kein polkit-Policy-File, keine Änderung an `NoNewPrivileges=yes`. Die einzige
Rechteerweiterung ist die fünfte sudoers-Zeile für `baluhost-backend-local`,
gleiche Form wie die vier bestehenden.

## Tests

Nach der Vorgehensweise des Repos: Test zuerst.

**Backend**
- Step-up richtig, falsch, 2FA-Variante; leerer Body ist ein gescheiterter
  Step-up, kein 422.
- Nicht-Admin → 403; ohne Token → 401; API-Key → 403; nicht-private IP → 403
  `local_network_required`.
- Reihenfolge mit gefaktem `subprocess`: `baluhost-backend` kommt zuletzt.
- Eine scheiternde Unit erscheint in der Antwort, ohne die übrigen zu
  verhindern.
- Dev-Mode ruft kein `systemctl`.
- Audit-Einträge für Erfolg, fehlgeschlagenen Step-up und abgelehntes LAN-Gate.
- Der Rate-Limit-Dekorator hängt tatsächlich an der Route (nicht nur der Wert
  in `RATE_LIMITS`).
- Die sudoers-Vorlage deckt genau `BALUHOST_UNITS` ab.

**Tray**
- `restart.py` vollständig ohne Qt: Pfadwahl, Refresh-Retry in `fetch_account_facts`
  *und* in `restart_via_api`, jede Zeile der Fehlertabelle, Timeout ≠ Abbruch,
  der eine `systemctl`-Aufruf mit allen Units, `is-active`-Auswertung.
- `restart_flow` als Ablauf: drei Versuche, Abbruch, Nicht-Admin, Wechsel auf
  den Notweg.
- Sichtbarkeitsregel als reine Funktion.
- **Ein Import-Test für `tray.py`** mit `QT_QPA_PLATFORM=offscreen`. Bisher
  importiert kein Test dieses Modul; ein Namensfehler auf Modul- oder
  Funktionsebene fiele sonst erst auf BaluNode auf.

**Übergreifend**
- Gleichheit der Unit-Listen in Tray und Backend.

## Doku und Regeln

- Im Tray-Entwurf vom 2026-09-21 **beide** Stellen als überholt markieren: das
  Nicht-Ziel „Service-Steuerung" und den Absatz „keinen ausgehenden Pfad … es
  bedient nicht".
- `docs/features/desktop-tray.{de,en}.md`: Menüeintrag, beide Wege, die
  Gruppenvoraussetzung `sudo`, und dass laufende Aufträge abgebrochen werden.
- `.claude/rules/security-agent.md`: der neue Endpunkt mit allen drei Gates;
  als Known Gaps die Audit-Lücke des Notwegs, die Reichweite des Step-ups
  (#699) und das zurücksetzbare Rate-Limit.
- `.claude/rules/architecture.md`: API-Liste ergänzen.

## Was das kritische Review geändert hat

Zwei Subagenten haben Entwurf und Plan gegen den Code geprüft. Korrigiert wurde:

| Ursprüngliche Behauptung | Befund |
|---|---|
| „Der Passwortdialog erscheint einmal und deckt alle Units ab" | Falsch — polkit bindet die temporäre Autorisierung an die PID. Gelöst durch **einen** `systemctl`-Aufruf für alle Units |
| „`baluhost-backend-local` … startet bei Bedarf selbst" | Falsch — sie läuft dauerhaft. Jetzt in der Liste, kostet eine sudoers-Zeile |
| „Keine sudoers-Erweiterung" | Gilt nur noch für den Notweg |
| „Der Wert entspricht `auth_password_change`" | Gleich ist nur die Zahl: jene Route liegt zusätzlich hinter nginx' `auth_limit`, diese nicht |
| „Blast radius: Unterbrechung von Sekunden, kein Verlust" | Laufende Scheduler-Jobs werden abgebrochen, Uploads sterben, ein Suspend-Fenster ohne RTC-Wecker entsteht |
| „Die Spur liegt im Journal" | Nur die polkitd-Zeile trägt den Urheber; ein Abbruch hinterlässt gar nichts |
| Kein LAN-Gate vorgesehen | Ergänzt — :8000 lauscht offen, ohne Paketfilter (#698) |
| API-Keys nicht betrachtet | Werden abgelehnt; sie verschöben sonst den Rate-Limit-Schlüssel auf die IP |
| SIGINT-Fallback aus `/api/system/restart` übernommen | Nicht übernommen — er trifft einen von vier Workern (#695) |
| „frisches TOTP" | Es gibt keine Frischeprüfung (#697); Backup-Codes gehen ebenfalls |
