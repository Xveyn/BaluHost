# Tray: gleitende Kopplung, Auto-Login, Always Awake im Menü

Stand: 2026-11-25 · Issue: #847 (Kopplung läuft nach 7 Tagen ab) · Paket 1 von 2
(Paket 2, automatische Zertifikatserneuerung mit eigener Domain, ist ein eigenes
Design).

## Absicht

Das Desktop-Tray (`backend/baluhost_tray/`) läuft auf der BaluHost-Maschine selbst,
in der Plasma-Sitzung des Besitzers. Heute hat es drei Schwächen im Alltag:

1. **Es stirbt nach 7 Tagen still.** Die Kopplung gibt einen Refresh-Token mit
   `REFRESH_TOKEN_EXPIRE_DAYS` (7) aus, `/api/auth/refresh` rotiert ihn nicht. Am
   7. Tag antwortet der Refresh mit 401, das Tray löscht `~/.baluhost/tray-tokens.json`
   und bleibt grau. Auf BaluNode zuletzt am 2026-11-23 22:10 beobachtet. Danach hilft
   nur `baluhost-tray --pair` **und** ein Neustart der Unit, und die Unit startet
   wegen `ConditionPathExists` nach einem Reboot gar nicht erst.
2. **„BaluHost öffnen“ landet auf der Login-Seite.** Die Web-UI hält nur ein
   Access-Token (Laufzeit per `auth_policy`), keinen Refresh. Wer vom Tray aus öffnet,
   muss sich fast immer neu anmelden — obwohl das Tray selbst längst angemeldet ist.
3. **Always Awake** ist nur über die Web-UI (Sleep-Seite) erreichbar.

Ziel: Das Tray bleibt gekoppelt, solange es benutzt wird; ein Klick auf „BaluHost
öffnen“ führt eingeloggt in die Web-UI; Always Awake ist mit zwei Klicks umschaltbar.

## Ziele

- Ein laufendes Tray verliert seine Kopplung nicht mehr durch Zeitablauf.
- Ein Desktop-/Tray-Gerät lässt sich in der Web-UI entfernen, und das widerruft
  seine Kopplung (heute nicht möglich, siehe A1b).
- Nach `baluhost-tray --pair` braucht es keinen Neustart der Unit mehr; ein Tray
  ohne Kopplung startet trotzdem, zeigt grau und erklärt im Tooltip, was zu tun ist.
- „BaluHost öffnen“ (Menü und Linksklick aufs Icon) öffnet die Web-UI eingeloggt
  als das gekoppelte Konto.
- Hat das Konto eine PIN, fragt das Tray vor dem Auto-Login danach.
- Always Awake: Untermenü *Aus / 1 Stunde / 8 Stunden / Dauerhaft*, nur für Admins.

## Nicht-Ziele

- Keine Änderung am Verhalten von BaluDesk und BaluApp (Mobile). Die Rotation ist
  opt-in.
- Kein Refresh-Token für die Web-UI, keine längeren Browser-Sitzungen generell.
- Kein Auto-Login für Browser auf anderen Rechnern. Das Tray läuft nur auf der Box.
- Keine eigene Tray-PIN; wiederverwendet wird die bestehende Konto-PIN.
- Keine Zertifikatsfragen (Paket 2).

## Anti-Ziele (wäre ein Fehlschlag, auch wenn es technisch läuft)

- Tray-Tokens tauchen in einer URL, der Browser-Historie oder einem Server-Log auf.
- Ein gestohlener alter Refresh-Token bleibt nach der Rotation benutzbar.
- Das Tray kann jemandem außerhalb des lokalen Netzes eine Web-Sitzung ausstellen.
- Ein Fehler im Auto-Login verhindert, dass sich die Web-UI überhaupt öffnet.
- Eine Rotation, die das Tray wegen eines Schreibfehlers nicht speichert, kostet
  die Kopplung (genau das Problem, das wir lösen wollen).

## Ansätze (gewählt: A1 + B1 + C, ergänzt um A1b)

**A — Kopplung am Leben halten**

- **A1 Gleitende Kopplung (gewählt).** Das Tray fordert beim Refresh ausdrücklich
  Rotation an; es bekommt einen neuen Refresh-Token mit frischer Laufzeit, der alte
  wird widerrufen. Widerruf pro Gerät bleibt. Opt-in, damit BaluDesk/BaluApp
  unverändert bleiben.
- A2 Nur Laufzeit verlängern (z. B. 90 Tage): billig, verschiebt das Problem nur.
- A3 Tray koppelt sich selbst neu und zeigt den Code als Benachrichtigung: braucht
  trotzdem jedes Mal einen Klick in der Web-UI.

**B — Auto-Login**

- **B1 Einmal-Code (gewählt).** Das Tray holt einen kurzlebigen, einmal gültigen
  Code; der Browser öffnet `…/login#handoff=<code>`; das Frontend tauscht ihn gegen
  eine eigene, normale Sitzung. Optional PIN-Abfrage.
- B2 Tray-Tokens in die URL: abgelehnt (Historie, geteilte Sitzung, Widerruf
  verheddert).
- B3 Browser-Sitzungen generell verlängern: wirkt auf jeden Browser, auch von außen.

**C — Always Awake im Menü.** Nur ein sinnvoller Weg: bestehende Route
`PUT /api/sleep/config`, Untermenü mit festen Dauern.

## Design

### A1 — Gleitende Kopplung

**Backend**

- `schemas/auth.py`: `RefreshTokenRequest` bekommt `rotate: bool = False`.
  `TokenResponse` bekommt `refresh_token: Optional[str] = None` (nur gesetzt, wenn
  rotiert wurde). Bestehende Clients senden das Feld nicht und sehen keine Änderung.
- `api/routes/auth.py:refresh_token()`: Nach allen bestehenden Prüfungen, wenn
  `payload.rotate` **und** die gespeicherte Token-Zeile ein `device_id` trägt
  (also aus einer Gerätekopplung stammt):
  - **Rotation nur in der zweiten Lebenshälfte** (Restlaufzeit < 50 % von
    `REFRESH_TOKEN_EXPIRE_DAYS`). Sonst wird nicht rotiert und kein
    `refresh_token` zurückgegeben. *Meine Entscheidung:* Das senkt die Zahl der
    Rotationen von ~100/Tag (jeder Access-Refresh) auf eine alle ~3,5 Tage — weniger
    DB-Zeilen und weniger Gelegenheiten für verlorene Antworten.
  - Neuen Refresh-Token mit gleichem `user_id` und `device_id`, Laufzeit
    `REFRESH_TOKEN_EXPIRE_DAYS` ab jetzt, speichern. Die neue Zeile merkt sich ihren
    Vorgänger (neue Spalte `parent_jti` auf `refresh_tokens`, Migration).
  - **Der alte Token wird dabei noch nicht widerrufen** („lazy revoke“). Er wird
    erst widerrufen (`revocation_reason="rotated"`), wenn der Nachfolger zum ersten
    Mal benutzt wird. Grund: Kommt die Antwort mit dem neuen Token nicht beim Tray
    an (Timeout, Backend-Neustart im Deploy), benutzt das Tray weiter den alten —
    und bekommt bei der nächsten Rotation einfach einen neuen Nachfolger. Der
    unbenutzte vorige Nachfolger wird dabei widerrufen (`reason="superseded"`), es
    gibt also pro Gerät höchstens einen unbenutzten Nachfolger.
  - Audit: `refresh_token_rotated` (Nutzer, device_id, IP; **nie** der Token).
- Die Hilfsfunktion zum Ausstellen (heute `desktop_pairing._issue_tokens`) wird so
  geteilt, dass Kopplung und Rotation denselben Code nutzen.
- **Transaktion:** Ausstellen, Widerruf des alten bzw. überholten Tokens und
  Nutzungsvermerk laufen in einer DB-Transaktion. `token_service.store_refresh_token()`
  und `revoke_token()` committen heute selbst; sie bekommen eine Variante ohne
  eigenen Commit (Umsetzer entscheidet die Form).
- **Wiederverwendungserkennung:** Wird ein Token vorgelegt, der mit
  `revocation_reason == "rotated"` widerrufen ist (sein Nachfolger wurde also
  nachweislich benutzt), gilt das als Diebstahlsignal: alle Tokens dieses
  `device_id` widerrufen (`revoke_device_tokens`), Audit
  `refresh_token_reuse_detected`, 401. Diese Prüfung muss **vor** dem heutigen
  generischen `is_token_revoked()`-Zweig stehen, sonst sieht sie den Grund nie.
  Mit „lazy revoke“ braucht es keine Gnadenfrist: Das Tray serialisiert seine
  Refreshes (Lock, siehe unten), und ein rotierter Token ist erst ungültig, wenn
  der Nachfolger beim Tray angekommen und benutzt ist.
- Rate-Limit: unverändert `auth_refresh`.
- Die Docstrings in `auth.py:refresh_token` und `session.py:refresh_access`
  („der Server rotiert nicht“) werden umgeschrieben.

### A1b — Desktop-Gerät entfernen (Voraussetzung für A1)

Heute lässt sich eine Desktop- bzw. Tray-Kopplung nicht widerrufen: Die Web-UI kann
Desktop-Geräte nur umbenennen (`PATCH /api/devices/desktop/{id}/name`),
`token_service.revoke_device_tokens()` hat keinen Aufrufer. Bisher war der Ablauf
nach 7 Tagen die einzige Grenze für einen gestohlenen Token; mit gleitender
Kopplung gäbe es keine. Deshalb Teil dieses Pakets:

- `DELETE /api/devices/desktop/{device_id}` in `api/routes/devices.py`:
  `get_current_user`, Eigentum über `ensure_owner_or_privileged()` (Admin darf
  fremde Geräte entfernen), Rate-Limit über einen bestehenden oder neuen Schlüssel,
  Audit `desktop_device_removed`. Ruft `revoke_device_tokens()` für dieses
  `device_id` und Nutzer auf und entfernt bzw. markiert den Geräteeintrag so, dass
  er aus der Liste verschwindet (Umsetzer prüft, wo die Desktop-Geräteliste ihre
  Daten herholt — `SyncState`/`DesktopPairingCode`).
- Web-UI (`DevicesPage`/`DeviceManagement`, `client/src/api/devices.ts`):
  Entfernen-Button mit Bestätigungsdialog für Desktop-Geräte, i18n `de` + `en`.
- Folge im Tray: Der nächste Refresh bekommt 401 → `PairingLost` → Wartezustand
  (siehe unten). Ein entferntes Tray wird also grau und sagt, dass es neu gekoppelt
  werden muss.

**Tray**

- `session.refresh_access()` sendet `rotate: true`. Kommt ein `refresh_token`
  zurück, wird er gespeichert; sonst bleibt der alte.
- `config.save_tokens()` schreibt **atomar** (temporäre Datei im selben Verzeichnis
  mit Modus 0600 von Anfang an, `fsync`, `os.replace`). Ein Absturz mitten im
  Schreiben hinterlässt dann entweder die alte oder die neue Datei, nie eine leere.
- Nebenläufigkeit: Loop-Thread, Neustart-Thread und künftig Handoff/Always-Awake
  können refreshen. Ein prozessweites `threading.Lock` um „Tokens laden → Refresh →
  speichern“ in `Session` serialisiert das; wer das Lock bekommt, liest die Tokens
  frisch aus der Datei.
- **Kein Neustart mehr nach `--pair`:** Bei `PairingLost` beendet sich die Schleife
  nicht mehr, sondern wartet (grau, Tooltip „Nicht gekoppelt — `baluhost-tray --pair`
  ausführen“) und prüft alle 10 s, ob `tray-tokens.json` wieder gültige Tokens
  enthält. Sobald ja: Session lädt sie neu, Rollen-/PIN-Fakten werden neu geholt,
  die Schleife läuft wieder an.
- **Start ohne Kopplung:** `main.py` startet die Qt-Oberfläche auch ohne Tokens und
  geht direkt in diesen Wartezustand, statt mit `EXIT_DONE` zu enden.
- Die Begründungskommentare zu `EXIT_DONE` in `main.py` werden entsprechend
  umgeschrieben, nicht nur gelöscht.
- Unit-Vorlage `deploy/install/templates/baluhost-tray.service`:
  `ConditionPathExists=%h/.baluhost/tray-tokens.json` entfällt (samt Kommentar). Bestehende
  Installationen behalten die Zeile, bis die User-Unit neu installiert wird — das
  ist harmlos (gekoppelt startet sie wie bisher) und wird in der Tray-Doku als
  einmaliger Schritt beschrieben.
- Was bleibt: 401/403 beim Refresh löschen die Tokens weiterhin (echter Widerruf);
  alles andere ist vorübergehend.

**Übergang bestehender Kopplungen:** Ein heute gekoppeltes Tray mit
Rest-Laufzeit < 3,5 Tage rotiert beim ersten Refresh nach dem Deploy und ist ab dann
gleitend. Eines mit mehr Restlaufzeit rotiert, sobald es in die zweite Hälfte kommt.
Ein bereits abgelaufenes muss einmal neu gekoppelt werden.

### B1 — Auto-Login per Einmal-Code

**Backend**

- Neues Modell `SessionHandoffCode` (Tabelle `session_handoff_codes`) mit
  `id`, `user_id` (FK), `token_hash` (SHA-256 des Codes, Spaltenname so gewählt,
  dass `REDACT_PATTERN` greift), `expires_at`, `used_at` (nullable), `created_at`,
  `created_ip`. Alembic-Migration. Datenbank statt Speicher, weil vier
  Uvicorn-Worker plus Local-Channel-Worker den Code sehen müssen.
- `POST /api/auth/handoff` — Code ausstellen.
  - **Nur für gekoppelte Geräte.** Nachweis ist nicht das Access-Token, sondern der
    Refresh-Token einer Gerätekopplung im Body. Er wird wie in `/auth/refresh`
    geprüft (Typ `refresh`, nicht widerrufen, Nutzer aktiv) und muss eine
    gespeicherte Zeile mit `device_id` haben. Damit kann sich eine Browser-Sitzung
    nicht selbst immer neu verlängern — sie hat keinen Refresh-Token. Das Benutzen
    zählt als Nutzung des Tokens (wie ein Refresh, inklusive „lazy revoke“ des
    Vorgängers). Kein `Authorization`-Header nötig; API-Keys kommen damit gar nicht
    erst in Frage.
  - LAN-Gate: `is_private_or_local_ip(request.client.host)`, sonst 403 + Audit
    `session_handoff_remote_denied` mit IP.
  - Body (Pydantic) `HandoffRequest { refresh_token: str, pin: Optional[str] }`.
    Hat das Konto eine PIN
    (`pin_hash` gesetzt), ist sie Pflicht und wird mit `pin_service` geprüft —
    inklusive bestehender Sperre (`is_pin_locked`, `register_pin_failure`,
    `reset_pin_failures`). Fehlende/falsche PIN → 401 mit
    `{"error": "pin_required" | "pin_invalid" | "pin_locked"}`, damit das Tray
    passend reagiert. Ohne PIN am Konto wird das Feld ignoriert.
    Unabhängig von `auth_policy.pin_login_enabled` und von 2FA: hier ersetzt die PIN
    kein Passwort, sondern ist eine zusätzliche Hürde vor einer Sitzung, die das
    Tray ohnehin schon hat.
  - **Kein Passwort, keine 2FA — bewusst** (vom Besitzer am 2026-11-25 bestätigt).
    Vertrauensmodell: Der Aufrufer sitzt auf der BaluHost-Maschine selbst (LAN-Gate,
    Tray nur dort), hält einen Gerätetoken, dessen Kopplung aus einer eingeloggten
    Sitzung heraus bestätigt wurde, und die Desktop-Sitzung ist entsperrt. Wer so
    weit ist, hat die Maschine. Damit ist der Handoff der einzige Weg zu einer vollen
    Web-Sitzung ohne Passwort und 2FA; das wird in `security-agent.md` so
    festgehalten.
  - Code: `secrets.token_urlsafe(32)`, gültig **30 s**, gespeichert nur als Hash.
  - Antwort `{ "code": "...", "expires_in": 30 }`.
  - Rate-Limit neuer Schlüssel `auth_handoff` (10/minute), Audit `session_handoff_issued`.
- `POST /api/auth/handoff/redeem` — Code einlösen. **Öffentlich** (keine Auth, der
  Code ist der Nachweis).
  - Body `HandoffRedeemRequest { code: str }`.
  - Einlösen atomar: `UPDATE … SET used_at = now WHERE token_hash = :h AND used_at
    IS NULL AND expires_at > now`; genau eine betroffene Zeile = gültig. Sonst 401
    generisch (kein Unterschied zwischen unbekannt/abgelaufen/benutzt).
  - Nutzer aktiv? Sonst 401.
  - Ausstellung über `_issue_session_token()` (Pflicht laut Sicherheitsregeln, sonst
    wird die `auth_policy`-Laufzeit ignoriert und `test_session_token_ttl.py` schlägt
    an). Antwort `TokenResponse` wie `/login`.
  - Rate-Limit `auth_handoff_redeem` (10/minute, IP-basiert), Audit
    `session_handoff_redeemed` bzw. `session_handoff_redeem_failed` mit IP.
  - **Kein LAN-Gate beim Einlösen.** *Meine Entscheidung,* bitte prüfen: Das Tray
    öffnet die konfigurierte `--web-url`. Ist das eine öffentliche Domain (auf
    BaluNode per Drop-in `https://baluhost.duckdns.org`, Vorgabe ist
    `https://baluhost.local`), kann die Anfrage je nach Router (Hairpin-NAT) bei
    nginx mit der öffentlichen IP ankommen, und ein Gate würde genau diesen Fall
    brechen. Der Code ist 256 Bit, 30 s gültig, einmalig, und wird nur
    im LAN-gegateten Schritt ausgestellt; er steht im URL-Fragment und erreicht
    daher weder nginx- noch Backend-Logs.
- Aufräumen: Abgelaufene Codes löscht der bestehende Cleanup-Pfad für Tokens (oder
  ein Löschen älterer Zeilen bei jedem Ausstellen) — *dem Umsetzer überlassen*,
  Hauptsache die Tabelle wächst nicht unbegrenzt.

**Frontend** (`client/src/pages/Login.tsx` bzw. ein kleiner Hook)

- Beim Laden der Login-Seite: Steht im Fragment `handoff=<code>`, sofort
  `history.replaceState` ohne Fragment (der Code verschwindet aus der Adresszeile
  und der Historie), dann `POST /api/auth/handoff/redeem`.
- Erfolg: `login(user, access_token)` aus `AuthContext`, Weiterleitung auf `/`.
- Fehlschlag: normale Login-Maske mit Hinweis „Automatische Anmeldung fehlgeschlagen
  — bitte normal anmelden“ (i18n `de` + `en`).
- Ist schon jemand eingeloggt, wird der Code trotzdem eingelöst und ersetzt die
  Sitzung (das Tray-Konto ist gewollt). *Meine Entscheidung.*
- Die Login-Route muss mit Fragment erreichbar sein, auch wenn bereits eine Sitzung
  besteht (heute leitet sie evtl. sofort weiter) — beim Umsetzen prüfen.

**Tray**

- „BaluHost öffnen“ und Linksklick lösen denselben Ablauf aus, in einem
  Arbeitsthread (Netzwerk nicht im GUI-Thread):
  1. Konto-PIN-Status ist beim Start mitgeholt (`GET /api/auth/pin`, in
     `fetch_account_facts` ergänzt).
  2. Hat das Konto eine PIN: Passwortdialog „PIN für BaluHost“ (GUI-Thread, über die
     bestehende Brücke wie beim Neustart). Abbruch → Web-UI ohne Auto-Login öffnen.
  3. `POST /api/auth/handoff` mit dem gespeicherten Refresh-Token (unter dem
     Session-Lock gelesen).
  4. Erfolg → `QDesktopServices.openUrl(f"{web_url}/login#handoff={code}")`.
     `pin_invalid` → Dialog einmal erneut („PIN stimmt nicht. Noch einmal:“).
     `pin_locked` → Hinweis „PIN gesperrt — bitte mit Passwort anmelden“ und normal
     öffnen. Jeder andere Fehler → einfach `web_url` öffnen.
- **Niemals blockieren:** Jeder Fehlerpfad endet im Öffnen der Web-UI ohne Code.
  Der Code wird nie geloggt.
- Doppelklick-Schutz: Läuft der Ablauf schon, wird ein zweiter Klick ignoriert.

### C — Always Awake im Menü

- Untermenü „Always Awake“ mit vier exklusiven, abhakbaren Einträgen:
  *Aus*, *1 Stunde*, *8 Stunden*, *Dauerhaft*.
- Sichtbar nur, wenn `fetch_account_facts` Admin meldet (wie der Neustart-Punkt).
  Bei unbekannter Rolle ausgeblendet — anders als der Neustart gibt es hier keinen
  Notweg, der ohne API sinnvoll wäre.
- Setzen: `PUT /api/sleep/config` mit
  - Aus: `{"always_awake_enabled": false, "always_awake_until": null}`
  - 1 h / 8 h: `{"always_awake_enabled": true, "always_awake_until": <now+X, UTC>}`
  - Dauerhaft: `{"always_awake_enabled": true, "always_awake_until": null}`
  Antwort enthält den tatsächlich gültigen Zustand (das Backend kann die Frist an
  einem Kern-Betriebsfenster kürzen). Bei 401 einmal refreshen. Audit macht die
  Route bereits (`always_awake_toggled`).
- Anzeige: Beim Öffnen des Menüs (`aboutToShow`) holt ein Arbeitsthread
  `GET /api/sleep/config`; das Ergebnis setzt den Haken. Ist Always Awake mit Frist
  aktiv, trägt der Untermenü-Titel sie: „Always Awake — bis 18:30“. Haken nach
  Setzen aus der PUT-Antwort, nicht aus der Annahme.
- Welcher Eintrag ist abgehakt, wenn eine Frist aktiv ist, die keinem Eintrag
  entspricht (z. B. in der Web-UI auf 3 h gesetzt)? Keiner der beiden
  Fristeinträge; der Titel zeigt die Frist. *Meine Entscheidung.*
- Fehler (Netz, 4xx/5xx) → Desktop-Benachrichtigung „Always Awake konnte nicht
  gesetzt werden“, Haken bleibt beim letzten bekannten Stand.

### Testbarkeit

Wie bisher liegen Entscheidungen in Modulen ohne Qt (`session.py`, `loop.py`,
neue Module z. B. `handoff.py`, `awake.py`), `tray.py` bleibt reine Darstellung.

- Backend-Tests: Rotation (nur mit `rotate`, nur mit `device_id`, nur zweite
  Lebenshälfte), „lazy revoke“ (alter Token gültig bis zur ersten Nutzung des
  Nachfolgers; verlorene Antwort → nächste Rotation ersetzt den unbenutzten
  Nachfolger), Reuse-Erkennung (rotierter Token → ganzes Gerät widerrufen),
  Desktop-Gerät entfernen (eigenes/fremdes/Admin, Tokens danach ungültig),
  Handoff ausstellen (LAN-Gate, Refresh-Token ohne `device_id` abgelehnt,
  Access-Token allein reicht nicht, PIN Pflicht/falsch/gesperrt, Konto ohne PIN), Einlösen (einmalig, abgelaufen, Laufzeit aus
  `auth_policy`), Rate-Limit-Schlüssel registriert.
- Tray-Tests ohne Display: Speichern des rotierten Tokens, atomares Schreiben,
  Lock gegen doppelten Refresh, Wartezustand und Wiederaufnahme nach neuer
  Token-Datei, Handoff-Ablauf inklusive aller Fallbacks, Always-Awake-Payloads und
  Haken-Logik.
- Frontend: Fragment wird entfernt und eingelöst; Fehlschlag zeigt Maske.

### Dokumentation

- `docs/features/desktop-tray.de.md` (und ggf. `.en`): Auto-Login, Always Awake,
  kein Neustart nach `--pair`, einmaliges Neu-Installieren der User-Unit.
- `.claude/rules/security-agent.md`: Eintrag zum Handoff (Gerätetoken als Nachweis,
  LAN-Gate beim Ausstellen, kein Gate beim Einlösen und warum, PIN, bewusst ohne
  Passwort/2FA samt Vertrauensmodell) und zur Rotation mit „lazy revoke“ und
  Reuse-Erkennung; Desktop-Geräte sind jetzt widerrufbar. `.claude/rules/architecture.md`: Routen ergänzen.
- `backend/app/api/CLAUDE.md` / `models/CLAUDE.md` gemäß Konvention.

### Ausrollen

- Alembic-Migration läuft im Deploy.
- Tray ist eine User-Unit: nach dem Deploy `systemctl --user restart baluhost-tray`,
  sonst läuft der alte Code weiter.
- Auf BaluNode einmalig: `baluhost-tray --pair` (Kopplung ist seit 23.11. weg).

## Dem Umsetzer überlassen

- Genaue Modulaufteilung im Tray, Namen der Helfer.
- Aufräumstrategie für abgelaufene Handoff-Codes.
- Ob `fetch_account_facts` erweitert oder ein zweiter Helfer gebaut wird.
- Wortlaut von Tooltips und Dialogen innerhalb des hier vorgegebenen Sinns.
