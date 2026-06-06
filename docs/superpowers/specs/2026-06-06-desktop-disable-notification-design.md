# Desktop-Disable Notifications — Design Spec

**Date:** 2026-06-06
**Status:** Approved
**Author:** Sven (Xveyn) + Claude (via brainstorming session)
**Branch:** `feat/desktop-disable-notification`

## Problem

Das KDE-Desktop-Deaktivieren/-Aktivieren (Bildschirme via DPMS aus-/einschalten, damit
die dGPU von ~78W auf ~18W deep-idlen kann) ist seit Kurzem als Schnellaktion im PowerMenu
sowie im `DesktopTogglePanel` (System Control → Sleep) verfügbar
(`POST /api/system/sleep/desktop/disable|enable`). Anders als bei Suspend/Resume/Shutdown/Startup
gibt es dafür **keine Benachrichtigung** — der Admin (und ggf. ein delegierter User) bekommt
keinen nachvollziehbaren Hinweis, dass der Desktop-Zustand gewechselt wurde.

## Goals

- Push-/In-App-Notification beim **Deaktivieren** und **Reaktivieren** des Desktops.
- Den **auslösenden Benutzer** im Text nennen (Nachvollziehbarkeit bei mehreren Admins / delegierten Usern).
- **Pro-Event** durch Admins konfigurierbar (beide standardmäßig an).
- Bestehende `EventEmitter`-Pipeline 1:1 wiederverwenden (keine Parallel-Pipeline).

## Non-Goals

- **Lokalisierung der Notification-Inhalte** — der gesamte Bestand erzeugt Notification-Titel/-Texte
  hart auf Deutsch (siehe [Issue #166](https://github.com/Xveyn/BaluHost/issues/166)). Dieses Feature
  folgt demselben Muster; i18n der Inhalte ist hier explizit ausgeklammert.
- Neue Notification-Kategorie (`desktop`) oder neues DB-Table — unnötig, siehe Decisions.
- Änderungen am PowerMenu, am `DesktopTogglePanel` oder an den Desktop-Backends.
- Notifications für automatische/Idle-Auslöser — es gibt **keine**; Desktop-Toggle ist rein manuell.
- Pro-Admin-Stummschaltung in der Glocke (technisch nicht möglich für geteilte System-Notifications,
  siehe Decisions / Edge Cases).

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Events | Beide: `desktop_disabled` + `desktop_enabled` |
| Kategorie | Bestehende `lifecycle`-Kategorie (kein neues Table, keine Migration) |
| Default-Lautstärke | Immer an für Admins (priority=1, `info` — wie Suspend/Resume) |
| Wer-Kontext | Auslösender Benutzer (`current_user.username`) im Text |
| Konfigurierbarkeit | Pro-Event-Schalter (neu), beide default an; „any-admin-wants-it"-Gate |
| Persistenz der Prefs | `category_preferences["desktop_notifications"]` (JSON, keine Migration) |
| Cooldown | 30 s pro Event (`cooldown_entity="desktop"`) gegen Doppelauslösung |
| Trigger-Punkt | `desktop.py` Route-Handler, nur bei `ok==True`, best-effort |

## Architecture

```
desktop.py: desktop_disable() / desktop_enable()   [async route, beliebiger Worker]
  └─ nach erfolgreichem Toggle (ok==True):
       emit_desktop_disabled(username)  bzw.  emit_desktop_enabled(username)
            │
            ├─ Gate (NEU): "will mind. ein aktiver Admin dieses Event?"
            │     │  SessionLocal → category_preferences["desktop_notifications"]
            │     ├─ nein  → still (keine DB-Zeile, kein Push)
            │     └─ ja    → emit_for_admins_sync(EventType.DESKTOP_*, username=...)
            │
            └─ ab hier bestehende Mechanik 1:1:
                 emit_sync()  (priority=1/info passiert den generischen Gate ohnehin durch)
                 ├─ System-Notification (user_id=NULL) → Glocke (alle Admins)
                 ├─ 30 s-Cooldown
                 └─ _send_push_sync → Mobile-Push, respektiert lifecycle-`mobile`-Flag pro Admin
```

**Kernidee:** Der Pro-Event-Gate lebt isoliert im neuen Emit-Helfer; `emit_sync` bleibt unverändert.
Bei genau einem Admin (reale Lage) wirkt „any-admin-wants-it" wie ein persönlicher Schalter.

## Components

### Modified files

| File | Change |
|---|---|
| `backend/app/services/notifications/events.py` | 2 neue `EventType` (`DESKTOP_DISABLED`, `DESKTOP_ENABLED`); 2 `EVENT_CONFIGS` (category `lifecycle`, priority=1, `info`); 2 Cooldown-Einträge (30 s); neue Emit-Helfer `emit_desktop_disabled_sync/_async`, `emit_desktop_enabled_sync/_async` inkl. „any-admin-wants-it"-Gate |
| `backend/app/api/routes/desktop.py` | In `desktop_disable` / `desktop_enable` nach `ok==True`: best-effort Emit mit `current_user.username` (try/except, bricht Toggle nie ab) |
| `client/src/pages/NotificationPreferencesPage.tsx` | Neue Admin-only Sektion „Desktop-Benachrichtigungen" mit 2 Toggles; State `desktopEvents`; Load aus `category_preferences.desktop_notifications` (Default beide `true`); Merge in `handleSave`-Payload |
| `client/src/api/notifications.ts` | Typ `NotificationPreferencesUpdate.category_preferences` minimal lockern (Union mit `{disabled:boolean; enabled:boolean}`-Shape); optional `DesktopEventsPref`-Interface |
| `client/src/i18n/locales/de/notifications.json` | Neue Keys `desktopEvents.*` |
| `client/src/i18n/locales/en/notifications.json` | Neue Keys `desktopEvents.*` |

### New files

| File | Purpose |
|---|---|
| `backend/tests/test_desktop_notifications.py` | Unit-Tests (Gate, Texte, Route-on-success-only, best-effort, Cooldown) |

> Kein neues Model, keine Migration, keine neue API-Route.

## Event-Templates (Deutsch, konsistent mit Bestand)

```
DESKTOP_DISABLED:  title   "Desktop deaktiviert"
                   message "Die Bildschirme wurden von {username} ausgeschaltet — die GPU kann in den Idle gehen."
                   action_url "/admin/system-control?tab=sleep"
                   priority 1, type info

DESKTOP_ENABLED:   title   "Desktop reaktiviert"
                   message "Die Bildschirme wurden von {username} wieder eingeschaltet."
                   action_url "/admin/system-control?tab=sleep"
                   priority 1, type info
```

`EventType`-Werte: `DESKTOP_DISABLED = "lifecycle.desktop_disabled"`, `DESKTOP_ENABLED = "lifecycle.desktop_enabled"`.
Cooldown: `"lifecycle.desktop_disabled": 30`, `"lifecycle.desktop_enabled": 30`.

## Preference-Speicherung & Gate

**Befund:** `NotificationPreferencesPage.loadPreferences()` normalisiert jede Kategorie auf exakt
`{error,success,mobile,desktop}` und `handleSave()` speichert nur `categoryPrefs` — **jeder Zusatz-Key
in `category_preferences` würde beim nächsten Speichern verworfen.** Speicherung erfordert daher bewusste
Frontend-Behandlung (separater State + explizites Load/Merge).

**Speicherort:** `category_preferences["desktop_notifications"] = {"disabled": true, "enabled": true}`
(reservierter Key, JSON-Feld → keine Migration). Wird vom Backend `update_user_preferences` wholesale
persistiert; `_get_category_pref` wird damit **nie** aufgerufen (Events emittieren unter `lifecycle`),
also keine Interferenz.

**Gate-Helfer** (neu, in `events.py`): öffnet `SessionLocal`, iteriert aktive Admins
(`User.role == "admin", is_active == True`), liest je Admin
`prefs.category_preferences.get("desktop_notifications", {})` und prüft `.get(which, True)`
(`which ∈ {"disabled","enabled"}`). Wenn **mind. ein** Admin das jeweilige Event will →
`emit_for_admins_sync(...)`, sonst still zurück. Spiegelt die vorhandene „any-admin-wants-it"-Logik
aus `emit_sync`.

## Frontend (UI) & i18n

- Neue **Admin-only** Karte „Desktop-Benachrichtigungen" in `NotificationPreferencesPage.tsx`,
  platziert unter der Kategorie-Tabelle. Zwei Toggle-Switches (gleicher Stil wie Quiet-Hours):
  „Bei Deaktivierung benachrichtigen" / „Bei Reaktivierung benachrichtigen", beide default an.
- **State:** `const [desktopEvents, setDesktopEvents] = useState({disabled: true, enabled: true})`.
  - Load: aus `prefs.category_preferences?.desktop_notifications` (Default beide `true`).
  - Save: in `handleSave` als `{...categoryPrefs, desktop_notifications: desktopEvents}` mergen.
- **i18n-Keys** (DE + EN, `notifications`-Namespace):

| Key | Deutsch | English |
|---|---|---|
| `desktopEvents.title` | „Desktop-Benachrichtigungen" | "Desktop notifications" |
| `desktopEvents.description` | „Benachrichtigen, wenn der Desktop deaktiviert oder reaktiviert wird" | "Notify when the desktop is disabled or re-enabled" |
| `desktopEvents.onDisable` | „Bei Deaktivierung benachrichtigen" | "Notify on disable" |
| `desktopEvents.onEnable` | „Bei Reaktivierung benachrichtigen" | "Notify on re-enable" |

> Notification-**Inhalte** bleiben deutsch (Backend-Templates), siehe Non-Goals / Issue #166.
> Kategorie-Anzeigename (`getCategoryName`) ist bereits hardcodiert `Lifecycle` (unverändert).

## Data Flow

```
User klickt "Desktop deaktivieren" (PowerMenu / DesktopTogglePanel)
  │
  ▼
POST /api/system/sleep/desktop/disable   (require_power_toggle_desktop)
  │  ok, message = await get_desktop_service().disable()
  │  audit_logger.log_event(...)                         [bestehend, unverändert]
  │
  ├─ if ok:                                              [NEU]
  │     try:
  │         emit_desktop_disabled(current_user.username)
  │     except Exception: log.warning(...)               # best-effort
  │
  └─ return {"success": ok, "message": message}
```

Reaktivierung (`/enable`) analog mit `emit_desktop_enabled`.

## Edge Cases

| Fall | Verhalten |
|---|---|
| `disable()`/`enable()` schlägt fehl (`ok==False`) | Keine Notification (kein Zustandswechsel); Route gibt `{success:false}` |
| Emit wirft Exception | `try/except` → Toggle bricht nie ab, nur Log-Warnung |
| Kein Admin will das Event | Gate unterdrückt Erzeugung komplett (keine DB-Zeile, kein Push) |
| Pro-Event unabhängig | `disabled=false, enabled=true` → nur Enable feuert |
| Dev-Mode (`DevDesktopBackend`) | `ok==True` → Notification wird erzeugt (Tests/Konsistenz) |
| FCM nicht konfiguriert | `_send_push_sync` no-op; Glocken-Eintrag bleibt |
| Quiet Hours | priority=1 < 3 → aktive Zustellung unterdrückt, Eintrag gespeichert (bestehend) |
| Doppelklick / API-Doppelaufruf | 30 s-Cooldown pro Event schluckt die zweite Meldung |
| Mehrere Worker | Ein Emit pro Request, beliebiger Worker → kein Primary-Worker-Guard, keine Duplikate |
| Mehrere Admins | Geteilte System-Notification ist in der Glocke für alle Admins sichtbar (Mobile-Push pro Admin via lifecycle-`mobile`-Flag). Pro-Admin-Glockenfilter ist out of scope |

## Tests

`backend/tests/test_desktop_notifications.py`:

| Test | Prüft |
|---|---|
| `test_emit_desktop_disabled_creates_notification_when_admin_wants` | Default-Prefs → Notification mit `event_type=lifecycle.desktop_disabled`, `username` im Text |
| `test_emit_desktop_enabled_creates_notification` | Analog für Reaktivierung |
| `test_gate_suppresses_when_no_admin_wants` | `desktop_notifications.disabled=false` → keine Notification |
| `test_gate_per_event_independent` | `disabled=false, enabled=true` → nur Enable feuert |
| `test_route_emits_on_success_only` | `ok=True` → emit aufgerufen; `ok=False` → nicht |
| `test_emit_failure_does_not_break_toggle` | Emit wirft → Route liefert trotzdem `{success:true}` |
| `test_cooldown_suppresses_second_within_30s` | Zwei Disable-Emits < 30 s → zweiter unterdrückt |

Frontend: Smoke-Check, dass die zwei Toggles laden/speichern (bestehende
`NotificationPreferencesPage`-Tests erweitern, falls vorhanden). PowerMenu-Tests bleiben unberührt
(kein PowerMenu-Change).

## Build Order

1. `events.py`: 2 EventTypes + 2 EVENT_CONFIGS + 2 Cooldowns + Emit-Helfer mit Gate
2. Tests (`test_desktop_notifications.py`) — TDD, zuerst rot
3. `desktop.py`: best-effort Emit nach `ok==True` in beiden Routen
4. Frontend: `NotificationPreferencesPage` Sektion + State + Load/Merge; `notifications.ts` Typ
5. i18n-Keys DE + EN
6. Backend-Tests grün + Frontend-Smoke

## Manual Smoketest (post-deploy)

1. PowerMenu → „Desktop deaktivieren" → Glocke zeigt „Desktop deaktiviert … von <user>"; Mobile-Push (falls FCM)
2. System Control → Sleep → Desktop reaktivieren → „Desktop reaktiviert … von <user>"
3. Notification-Einstellungen → „Bei Deaktivierung benachrichtigen" aus → erneut deaktivieren → keine Notification
4. Beide Toggles aus → kein Event; beide an (Default) → beide Events
5. Zwei schnelle Deaktivierungen < 30 s → nur eine Notification (Cooldown)
