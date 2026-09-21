# Desktop-Tray für KDE Plasma — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Tray-Icon im Plasma-Panel, dessen Farbe den Zustand der Anlage
trägt und das kritische Ereignisse als Desktop-Meldung zustellt — synchron mit
Web-App und BaluApp.

**Architecture:** Das Icon ist eine Projektion der ungelesenen Meldungen, kein
zweiter Gesundheitsbegriff. Phase A repariert zuerst zwei vorbestehende
Backend-Defekte, ohne die das Tray nicht funktionieren *kann*, und schließt
danach die Fan-out-Lücke; alle drei Teile nützen Web-App und BaluApp
unabhängig vom Tray. Phase B baut darauf das Tray als Python-Modul neben der
vorhandenen TUI.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, pytest/pytest-asyncio ·
PyQt6 (`QSystemTrayIcon`), `dbus-next`, `httpx`, `websockets` ·
React/TypeScript mit Vitest im Frontend.

**Spec:** `docs/superpowers/specs/2026-09-21-desktop-tray-design.md`

## Global Constraints

- **Branch:** `feat/desktop-tray`, Basis `main` @ `e143b21f`.
- **Keine `from __future__ import annotations` in Plugin-Routen.** Hinter dem
  `@user_limiter.limit`-Wrapper von slowapi werden zurückgestellte Annotationen
  zu ForwardRefs, die FastAPI nicht mehr auflöst — jeder Request wird 422.
  Der Warnkommentar steht wörtlich in `steam_gaming/routes.py:5-7`.
- **Routen mit `@user_limiter.limit` lassen sich nicht direkt aufrufen.**
  slowapi greift auf den `request`-Parameter zu und lehnt alles ab, was keine
  echte `starlette.requests.Request` ist — auch `MagicMock(spec=Request)`.
  Solche Routen werden über `TestClient` getestet; Muster:
  `backend/tests/plugins/test_steam_gaming_routes.py`.
- **Blockierende Aufrufe gehören in `asyncio.to_thread`.** Das gilt in
  FastAPI-Routen *und* im Tray: `BackendClient` benutzt einen synchronen
  `httpx.Client`, jeder Aufruf daraus in `async def` blockiert sonst den
  Socket-Read.
- **Der Fan-out sitzt in der Route-Ebene, nicht im Service.** Die
  Zustandsmethoden des `NotificationService` sind synchron (`def` mit
  `Session`); die Handler sind `async`.
- **`broadcast_to_user()` ist für den Fan-out unbrauchbar** — es setzt
  `"type": "notification"` fest (`websocket_manager.py:133`).
- **Qt-Objekte nur aus dem GUI-Thread anfassen.** Der asyncio-Worker berührt
  `QSystemTrayIcon` nie direkt, sondern ausschließlich über ein `pyqtSignal`
  (thread-übergreifend standardmäßig `QueuedConnection`).
- **`tray.py` enthält keine Logik.** Alles Entscheidbare liegt in `state.py`,
  `watch.py` und `loop.py` und ist ohne Qt prüfbar.
- **Kein root, keine sudoers-Erweiterung.**
- **PyQt6 nur als optionales Extra** `tray`.
- **Tests laufen ohne D-Bus, ohne Plasma, ohne echten WebSocket-Server.**
- **`asyncio_mode = "auto"`** ist in `backend/pyproject.toml:131` gesetzt;
  `@pytest.mark.asyncio` ist redundant, schadet aber nicht und wird aus
  Konsistenz mit den Nachbartests mitgeschrieben.
- **Frontend-Tests laufen mit `npx vitest run`**, nie mit `npm test`
  (das startet den Watch-Modus und hängt in einer `&&`-Kette).
- **Commit-Format:** Conventional Commits (`CONTRIBUTING.md`), deutsche
  Beschreibung, Footer `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

# Phase A — Meldungen erreichen ihre Empfänger

Tasks 1 und 2 sind vorbestehende Defekte, keine Tray-Vorarbeit. Beide haben
eigenständigen Wert und bleiben sinnvoll, auch wenn Phase B nie gebaut wird.

### Task 1: `emit_sync` verteilt seine Meldung über den WebSocket

**Files:**
- Modify: `backend/app/services/notifications/events.py` (Klasse `EventEmitter`, `emit_sync` ab Zeile 603)
- Modify: `backend/app/core/lifespan.py` (neben `get_log_buffer_handler().set_event_loop(...)`, Zeile 552)
- Test: `backend/tests/services/test_event_emitter_broadcast.py`

**Interfaces:**
- Consumes: `WebSocketManager.broadcast_to_user`, `broadcast_to_admins`, `get_websocket_manager()`.
- Produces:
  - `EventEmitter.set_event_loop(loop: asyncio.AbstractEventLoop) -> None`
  - `EventEmitter._broadcast_sync(notification) -> None` (intern, nicht blockierend)

**Der Defekt.** `emit_sync` legt die Notification per `db.add()`/`db.commit()`
an (`events.py:694-695`) und ruft danach **nur** `_send_push_sync()` (Zeile
700). Es ruft nie `NotificationService.create()` und damit nie `dispatch()` —
also nie `broadcast_to_user()`/`broadcast_to_admins()`. Nur der **async**
`emit()` (Zeile 536) erreicht den WebSocket.

Genau die kritischen Hardware-Ereignisse laufen über den sync-Pfad:
`emit_raid_degraded_sync` (`hardware/raid/mdadm_backend.py:115`, `raid/api.py:157`),
`emit_smart_failure_sync`/`emit_smart_warning_sync` (`hardware/smart/api.py:30,36,48`),
`emit_temperature_critical_sync` (`monitoring/orchestrator.py:245`, `power/fan_control.py:1339`),
`emit_disk_space_critical_sync` (`monitoring/orchestrator.py:261`).

Folge heute: SMART meldet FAILED → Datenbankzeile entsteht, Firebase-Push geht
aufs Handy, eine offene Web-UI erfährt nichts bis zum Neuladen. Ohne diesen
Task bliebe das Tray-Icon bei genau den Ereignissen grün, für die es gebaut
wird.

**Das Muster für den Übergang.** `emit_sync` läuft aus Worker-Threads, der
Broadcast ist `async`. Das Projekt löst das bereits bei `LogBufferHandler`
(`services/log_buffer.py:41-61`): Die Loop wird beim Start gemerkt und aus dem
fremden Thread über `call_soon_threadsafe` bedient. Für eine Coroutine ist das
Gegenstück `asyncio.run_coroutine_threadsafe`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/services/test_event_emitter_broadcast.py`:

```python
"""emit_sync must reach the websocket, not just Firebase.

The sync path is the one every critical hardware event uses (RAID, SMART,
temperature, disk space). Before this test existed it wrote a row, pushed to
Firebase and told no connected client anything.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.notifications.events import EventEmitter


@pytest.mark.asyncio
async def test_broadcast_sync_reaches_admins_for_system_notifications():
    emitter = EventEmitter()
    emitter.set_event_loop(asyncio.get_running_loop())

    manager = MagicMock()
    manager.broadcast_to_admins = AsyncMock(return_value=1)
    manager.broadcast_to_user = AsyncMock(return_value=1)

    notification = MagicMock()
    notification.user_id = None
    notification.to_dict.return_value = {"id": 1, "notification_type": "critical"}

    with patch(
        "app.services.notifications.events.get_websocket_manager",
        return_value=manager,
    ):
        emitter._broadcast_sync(notification)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    manager.broadcast_to_admins.assert_awaited_once()
    manager.broadcast_to_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_scoped_notification_goes_to_that_user():
    emitter = EventEmitter()
    emitter.set_event_loop(asyncio.get_running_loop())

    manager = MagicMock()
    manager.broadcast_to_admins = AsyncMock(return_value=0)
    manager.broadcast_to_user = AsyncMock(return_value=1)

    notification = MagicMock()
    notification.user_id = 7
    notification.to_dict.return_value = {"id": 2, "notification_type": "warning"}

    with patch(
        "app.services.notifications.events.get_websocket_manager",
        return_value=manager,
    ):
        emitter._broadcast_sync(notification)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    manager.broadcast_to_user.assert_awaited_once()
    assert manager.broadcast_to_user.await_args[0][0] == 7
    manager.broadcast_to_admins.assert_not_awaited()


def test_without_a_loop_it_stays_silent_instead_of_raising():
    """Worker ohne laufende App-Loop (Tests, Skripte) duerfen nicht platzen."""
    emitter = EventEmitter()  # set_event_loop nie gerufen
    notification = MagicMock()
    notification.user_id = None
    notification.to_dict.return_value = {"id": 3}

    emitter._broadcast_sync(notification)  # wirft nicht


@pytest.mark.asyncio
async def test_broadcast_failure_does_not_break_the_caller():
    """Ein kaputter Socket darf emit_sync nicht mitreissen — die Zeile steht
    zu diesem Zeitpunkt bereits in der Datenbank."""
    emitter = EventEmitter()
    emitter.set_event_loop(asyncio.get_running_loop())

    manager = MagicMock()
    manager.broadcast_to_admins = AsyncMock(side_effect=RuntimeError("gone"))

    notification = MagicMock()
    notification.user_id = None
    notification.to_dict.return_value = {"id": 4}

    with patch(
        "app.services.notifications.events.get_websocket_manager",
        return_value=manager,
    ):
        emitter._broadcast_sync(notification)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/services/test_event_emitter_broadcast.py -v`
Expected: FAIL mit `AttributeError: 'EventEmitter' object has no attribute 'set_event_loop'`

- [ ] **Step 3: Minimal implementieren**

In `backend/app/services/notifications/events.py` oben ergänzen:

```python
import asyncio
from typing import Optional

from app.services.websocket_manager import get_websocket_manager  # noqa: F401
```

Der Top-Level-Import dient als Patch-Ziel der Tests; `_send()` importiert
zusätzlich lokal, damit beim Modulimport keine Zyklen entstehen.

In `EventEmitter.__init__`:

```python
        # Set once at startup from the app's event loop (see lifespan). The
        # sync emit path runs on worker threads and needs a loop to hand its
        # broadcast to; same idiom as LogBufferHandler.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
```

Zwei neue Methoden auf der Klasse:

```python
    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the app loop so emit_sync can broadcast from a thread."""
        self._loop = loop

    def _broadcast_sync(self, notification) -> None:
        """Hand the notification to the websocket from synchronous code.

        emit_sync runs on worker threads (monitoring, fan control, SMART
        polling). Without this the whole sync path was invisible to every
        connected client: the row was written, Firebase was told, and an open
        web UI learned nothing until it reloaded.

        Fire and forget on purpose. The row is already committed when we get
        here, so a dead socket must not propagate back into the caller.
        """
        loop = self._loop
        if loop is None or not loop.is_running():
            logger.debug("No app loop bound — skipping websocket broadcast")
            return

        try:
            payload = notification.to_dict()
            user_id = notification.user_id
        except Exception as exc:
            logger.warning("Cannot serialise notification for broadcast: %s", exc)
            return

        async def _send() -> None:
            from app.services.websocket_manager import get_websocket_manager

            manager = get_websocket_manager()
            try:
                if user_id is None:
                    await manager.broadcast_to_admins(
                        {"type": "notification", "payload": payload}
                    )
                else:
                    await manager.broadcast_to_user(user_id, payload)
            except Exception as exc:
                logger.warning("Websocket broadcast from emit_sync failed: %s", exc)

        try:
            asyncio.run_coroutine_threadsafe(_send(), loop)
        except Exception as exc:
            logger.warning("Could not schedule broadcast: %s", exc)
```

**Achtung auf die zwei Signaturen.** `broadcast_to_user(user_id, message)`
wickelt selbst in `{"type": "notification", "payload": message}` ein
(`websocket_manager.py:133`), `broadcast_to_admins(message)` nicht — deshalb
trägt nur die Admin-Variante den Umschlag. Vor dem Schreiben beide
Methodenrümpfe gegenlesen und die Einwicklung danach setzen; ein doppelt
eingewickelter Frame ist genau der Fehler aus #511.

Dann in `emit_sync` direkt nach `db.commit()` (Zeile 695) und **vor**
`_send_push_sync`:

```python
            self._broadcast_sync(notification)
```

- [ ] **Step 4: Loop beim Start binden**

In `backend/app/core/lifespan.py` neben Zeile 552:

```python
    get_log_buffer_handler().set_event_loop(asyncio.get_running_loop())
    get_event_emitter().set_event_loop(asyncio.get_running_loop())
```

**Vor dem Schreiben prüfen**, wie die Emitter-Instanz aus `events.py` bezogen
wird — Fabrikfunktion oder Modulvariable — und den echten Namen einsetzen.

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/services/test_event_emitter_broadcast.py -v`
Expected: PASS (4 Tests)

Run: `cd backend && .venv/bin/pytest tests/services -k notification -q`
Expected: keine neuen Fehlschläge

- [ ] **Step 6: Committen**

```bash
git add backend/app/services/notifications/events.py backend/app/core/lifespan.py backend/tests/services/test_event_emitter_broadcast.py
git commit -m "fix(notifications): emit_sync erreicht endlich den WebSocket

emit_sync schrieb die Zeile, rief _send_push_sync und war fertig --
weder create() noch dispatch(), also nie ein Broadcast. Genau die
kritischen Hardware-Ereignisse laufen aber ueber diesen Pfad: RAID
degradiert, SMART-Ausfall, kritische Temperatur, volle Platte.

Praktisch hiess das: Firebase-Push aufs Handy ja, offene Web-UI nein.
Wer den Tab offen hatte, erfuhr vom Plattenausfall nichts bis zum
Neuladen.

Der Uebergang vom Worker-Thread auf die App-Loop folgt dem Muster von
LogBufferHandler: Loop beim Start merken, dann aus dem fremden Thread
einplanen. Fire and forget -- die Zeile steht schon in der Datenbank,
ein toter Socket darf den Aufrufer nicht mitreissen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Refresh-Token der Gerätekopplung wird gespeichert

**Files:**
- Modify: `backend/app/services/desktop_pairing.py` (bei `create_refresh_token`, Zeile 122-123)
- Test: `backend/tests/api/test_desktop_pairing_refresh.py`

**Interfaces:**
- Consumes: `TokenService.store_refresh_token` (`app/services/token_service.py:23`).
- Produces: keine neue Signatur; die Kopplung hinterlegt ihr Token künftig.

**Der Defekt.** `poll_device_code` macht

```python
refresh_token, _jti = create_refresh_token(user)
```

und **verwirft den jti**. `store_refresh_token` hat genau einen
Produktivaufrufer: `app/services/mobile.py:288`.

`/api/auth/refresh` prüft aber `token_service.is_token_revoked(db, jti)`
(`routes/auth.py:858`), und `is_token_revoked` liefert für unbekannte Tokens
`True` — der Kommentar sagt es wörtlich: *„Unknown token = revoked"*
(`token_service.py:97-99`). Ergebnis: **401, immer.**

Folgen: Ein per Gerätecode gekoppelter Client verliert nach Ablauf des
Access-Tokens die Verbindung und kann sie nicht erneuern. Das betrifft BaluDesk
genauso wie das Tray. Zweite Folge: `revoke_device_tokens()` hat nichts zu
widerrufen — die in der Spec zugesagte Widerrufbarkeit pro Gerät existiert ohne
diesen Task nicht.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/api/test_desktop_pairing_refresh.py`:

```python
"""A paired device must be able to refresh — today it cannot.

poll_device_code hands out a refresh token whose jti it throws away, and
/auth/refresh treats an unknown jti as revoked. The pairing therefore dies
with the access token.
"""

from unittest.mock import MagicMock, patch

from app.services import desktop_pairing


def test_pairing_stores_the_refresh_token_jti():
    """Der jti muss in der RefreshToken-Tabelle landen, sonst ist er wertlos."""
    stored = {}

    def _capture(db, **kwargs):
        stored.update(kwargs)
        return MagicMock()

    with patch(
        "app.services.desktop_pairing.create_refresh_token",
        return_value=("rt", "jti-123"),
    ), patch(
        "app.services.desktop_pairing.create_access_token", return_value="at"
    ), patch(
        "app.services.desktop_pairing.token_service.store_refresh_token",
        side_effect=_capture,
    ):
        desktop_pairing._issue_tokens(
            db=MagicMock(),
            user=MagicMock(id=5),
            device_id="dev-1",
        )

    assert stored.get("jti") == "jti-123"
    assert stored.get("user_id") == 5
    assert stored.get("device_id") == "dev-1"
```

**Vor dem Schreiben prüfen:** ob sich `poll_device_code` sinnvoll um einen
Helfer `_issue_tokens(db, user, device_id)` herum aufteilen lässt oder ob der
Test direkt gegen `poll_device_code` geführt werden muss. Maßgeblich für die
Parameternamen ist die echte Signatur von `store_refresh_token`
(`token_service.py:23`) — den Test daran ausrichten, nicht umgekehrt.

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/api/test_desktop_pairing_refresh.py -v`
Expected: FAIL — der jti wird nie weitergereicht

- [ ] **Step 3: Minimal implementieren**

In `backend/app/services/desktop_pairing.py` ergänzen:

```python
from app.services import token_service
```

Und an der Ausgabestelle (Zeile 122-123):

```python
        access_token = create_access_token(user)
        refresh_token, jti = create_refresh_token(user)
        # Without this row /auth/refresh rejects the token: is_token_revoked()
        # treats an unknown jti as revoked. A paired device would lose its
        # session when the access token expires and could never recover.
        token_service.store_refresh_token(
            db,
            jti=jti,
            user_id=user.id,
            device_id=pairing.device_id,
        )
```

Die tatsächlichen Parameternamen und weitere Pflichtfelder (Ablaufdatum,
Gerätename, IP) aus `token_service.store_refresh_token` übernehmen.

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/api/test_desktop_pairing_refresh.py -v`
Expected: PASS

Run: `cd backend && .venv/bin/pytest tests -k "pairing or refresh or token" -q`
Expected: keine neuen Fehlschläge

- [ ] **Step 5: Committen**

```bash
git add backend/app/services/desktop_pairing.py backend/tests/api/test_desktop_pairing_refresh.py
git commit -m "fix(auth): Geraetekopplung hinterlegt ihr Refresh-Token

poll_device_code gab ein Refresh-Token heraus und verwarf dessen jti.
/auth/refresh prueft aber is_token_revoked(), und das liefert fuer
unbekannte jti True -- 'Unknown token = revoked'. Jedes per Geraetecode
gekoppelte Geraet bekam also garantiert 401 und verlor die Sitzung,
sobald das Access-Token ablief. Betrifft BaluDesk ebenso.

Nebenwirkung, die kein Zufall ist: revoke_device_tokens() hatte bisher
nichts zu widerrufen. Mit der Zeile ist die Kopplung pro Geraet
tatsaechlich widerrufbar.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `send_notification_state()` im WebSocketManager

**Files:**
- Modify: `backend/app/services/websocket_manager.py` (nach `send_unread_count`, ab Zeile 250)
- Test: `backend/tests/services/test_websocket_manager.py`

**Interfaces:**
- Consumes: nichts.
- Produces: `async def send_notification_state(self, user_id: int, ids: list[int], action: str) -> int`
  — sendet `{"type": "notification_state", "payload": {"ids": [...], "action": "..."}}`
  an alle Verbindungen des Nutzers. Aktionen: `"read"`, `"dismissed"`,
  `"snoozed"`, `"deleted"`, `"restored"`, `"read_all"`, `"dismissed_all"`,
  `"deleted_all"`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

An `backend/tests/services/test_websocket_manager.py` anhängen; die Helfer
`_make_ws` und die `manager`-Fixture stehen dort bereits (Zeilen 10-19):

```python
@pytest.mark.asyncio
class TestSendNotificationState:
    async def test_sends_to_all_connections_of_user(self, manager: WebSocketManager):
        ws1, ws2 = _make_ws(), _make_ws()
        await manager.connect(ws1, user_id=1)
        await manager.connect(ws2, user_id=1)

        sent = await manager.send_notification_state(1, [7, 8], "read")

        assert sent == 2
        frame = ws1.send_json.call_args[0][0]
        assert frame == {
            "type": "notification_state",
            "payload": {"ids": [7, 8], "action": "read"},
        }

    async def test_other_users_untouched(self, manager: WebSocketManager):
        mine, theirs = _make_ws(), _make_ws()
        await manager.connect(mine, user_id=1)
        await manager.connect(theirs, user_id=2)

        await manager.send_notification_state(1, [7], "dismissed")

        assert theirs.send_json.call_count == 0

    async def test_no_connections_is_zero(self, manager: WebSocketManager):
        assert await manager.send_notification_state(99, [1], "read") == 0

    async def test_drops_broken_connection(self, manager: WebSocketManager):
        ws = _make_ws(send_json_side_effect=RuntimeError("gone"))
        await manager.connect(ws, user_id=1)

        sent = await manager.send_notification_state(1, [1], "read")

        assert sent == 0
        assert manager.get_connection_count(1) == 0
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/services/test_websocket_manager.py::TestSendNotificationState -v`
Expected: FAIL mit `AttributeError: 'WebSocketManager' object has no attribute 'send_notification_state'`

- [ ] **Step 3: Minimal implementieren**

Direkt nach `send_unread_count` — bewusst derselbe Aufbau, inklusive Aufräumen
toter Verbindungen:

```python
    async def send_notification_state(
        self, user_id: int, ids: list[int], action: str
    ) -> int:
        """Tell a user's connections that notification state changed elsewhere.

        Counterpart to send_unread_count: that one carries the number, this
        one carries which notifications changed and how, so an open client can
        update its list. broadcast_to_user() cannot be used here — it
        hardcodes "type": "notification".

        Args:
            user_id: Target user ID
            ids: Affected notification IDs; empty for the bulk actions, where
                "all" is exactly what the empty list means
            action: read | dismissed | snoozed | deleted | restored |
                read_all | dismissed_all | deleted_all

        Returns:
            Number of connections the message was sent to
        """
        sent_count = 0
        async with self._lock:
            connections = self._user_connections.get(user_id, [])
            disconnected = []

            for conn in connections:
                try:
                    await conn.websocket.send_json({
                        "type": "notification_state",
                        "payload": {"ids": ids, "action": action},
                    })
                    sent_count += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to send notification state to user {user_id}: {e}"
                    )
                    disconnected.append(conn)

            for conn in disconnected:
                if conn in connections:
                    connections.remove(conn)

        return sent_count
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/services/test_websocket_manager.py -v`
Expected: PASS, bestehende Klassen unverändert grün

- [ ] **Step 5: Committen**

```bash
git add backend/app/services/websocket_manager.py backend/tests/services/test_websocket_manager.py
git commit -m "feat(notifications): send_notification_state verteilt Zustandsaenderungen

Gegenstueck zu send_unread_count: traegt, welche Meldungen sich wie
geaendert haben, damit ein offener Client seine Liste nachziehen kann.
broadcast_to_user war dafuer unbrauchbar, weil es den Typ
'notification' festsetzt.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Fan-out-Helfer und Einbau in die acht Routen

**Files:**
- Create: `backend/app/api/routes/_notification_fanout.py`
- Modify: `backend/app/api/routes/notifications.py` (Handler `/read` 149, `/read-all` 170, `/dismiss-all` 190, `/{id}/dismiss` 208, `/{id}/snooze` 234, `/{id}/restore` 260, `DELETE /trash` 283, `DELETE /{id}` 298)
- Test: `backend/tests/api/test_notification_fanout.py`

**Interfaces:**
- Consumes: `send_notification_state` (Task 3), `send_unread_count`,
  `get_websocket_manager()`, `WebSocketManager.is_user_connected`,
  `NotificationService.get_unread_count`.
- Produces: `async def fanout_state(db: Session, user_id: int, ids: list[int], action: str, is_admin: bool) -> None`

**Warum acht und nicht sechs.** Der erste Entwurf hatte `restore` und
`empty_trash` übersehen. Für den *Zähler* sind sie unkritisch, weil `dismiss`
und `dismiss_all` immer `is_read=True` mitsetzen — Papierkorb-Zeilen sind nie
ungelesen. Für die *Liste* in Web-UI und BaluApp sind sie es sehr wohl, und die
Spec verspricht Bestandsgleichheit, nicht Zählergleichheit.

**Sammelaktionen tragen keine IDs, und das ist Absicht.** `mark_all_as_read`
nimmt einen optionalen `category`-Filter entgegen (`notifications.py:172-188`).
Eine Payload, die nur „alles gelesen" sagt, wäre bei gesetzter Kategorie eine
Lüge. Statt die Kategorie mitzuschicken und jeden Client sie nachbilden zu
lassen, bedeuten die `*_all`-Aktionen: **neu laden**. Der Client rät nicht, er
fragt. Das ist zugleich das Verhalten, das Web-UI und Tray ohnehin bei jedem
`notification_state` zeigen.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/api/test_notification_fanout.py`:

```python
"""Tests for the notification state fan-out helper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.routes._notification_fanout import fanout_state


@pytest.fixture
def ws_manager() -> MagicMock:
    manager = MagicMock()
    manager.is_user_connected = MagicMock(return_value=True)
    manager.send_notification_state = AsyncMock(return_value=1)
    manager.send_unread_count = AsyncMock(return_value=1)
    return manager


def _service(unread: int = 3) -> MagicMock:
    service = MagicMock()
    service.get_unread_count.return_value = unread
    return service


def _patches(ws_manager: MagicMock, service: MagicMock):
    return (
        patch(
            "app.api.routes._notification_fanout.get_websocket_manager",
            return_value=ws_manager,
        ),
        patch(
            "app.api.routes._notification_fanout.get_notification_service",
            return_value=service,
        ),
    )


@pytest.mark.asyncio
async def test_sends_state_then_count(ws_manager: MagicMock):
    service = _service(3)
    p1, p2 = _patches(ws_manager, service)
    with p1, p2:
        await fanout_state(MagicMock(), 1, [7], "read", is_admin=False)

    ws_manager.send_notification_state.assert_awaited_once_with(1, [7], "read")
    ws_manager.send_unread_count.assert_awaited_once_with(1, 3)


@pytest.mark.asyncio
async def test_bulk_action_sends_despite_empty_ids(ws_manager: MagicMock):
    service = _service(0)
    p1, p2 = _patches(ws_manager, service)
    with p1, p2:
        await fanout_state(MagicMock(), 1, [], "read_all", is_admin=False)

    ws_manager.send_notification_state.assert_awaited_once_with(1, [], "read_all")


@pytest.mark.asyncio
async def test_empty_ids_on_single_action_sends_nothing(ws_manager: MagicMock):
    service = _service(0)
    p1, p2 = _patches(ws_manager, service)
    with p1, p2:
        await fanout_state(MagicMock(), 1, [], "read", is_admin=False)

    ws_manager.send_notification_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_nothing_happens_without_a_connection(ws_manager: MagicMock):
    """Kein offener Client -> keine COUNT-Query. Der Zaehler kostet sonst
    eine Datenbankabfrage pro Klick, auch wenn niemand zuhoert."""
    ws_manager.is_user_connected.return_value = False
    service = _service(3)
    p1, p2 = _patches(ws_manager, service)
    with p1, p2:
        await fanout_state(MagicMock(), 1, [7], "read", is_admin=False)

    service.get_unread_count.assert_not_called()
    ws_manager.send_notification_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_failure_does_not_propagate(ws_manager: MagicMock):
    """Ein toter Socket darf aus einem erfolgreichen POST kein 500 machen."""
    ws_manager.send_notification_state.side_effect = RuntimeError("socket gone")
    service = _service(0)
    p1, p2 = _patches(ws_manager, service)
    with p1, p2:
        await fanout_state(MagicMock(), 1, [7], "read", is_admin=False)


@pytest.mark.asyncio
async def test_unknown_action_rejected(ws_manager: MagicMock):
    with pytest.raises(ValueError):
        await fanout_state(MagicMock(), 1, [7], "exploded", is_admin=False)
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/api/test_notification_fanout.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.api.routes._notification_fanout'`

- [ ] **Step 3: Minimal implementieren**

`backend/app/api/routes/_notification_fanout.py`:

```python
"""Fan-out of notification state changes to a user's open connections.

Lives in the route layer on purpose: the NotificationService state methods
are synchronous (def, Session), the send is async. A fan-out inside the
service would have to schedule a task on a foreign event loop from
synchronous code. All eight routes that change state call this one helper so
they cannot drift apart.
"""

import logging

from sqlalchemy.orm import Session

from app.services.notifications.service import get_notification_service
from app.services.websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)

# The bulk actions carry no ids on purpose: mark_all_as_read takes an optional
# category filter, so "everything" would be a lie whenever one is set. These
# actions mean "reload" — the client asks instead of guessing.
BULK_ACTIONS = frozenset({"read_all", "dismissed_all", "deleted_all"})
SINGLE_ACTIONS = frozenset({"read", "dismissed", "snoozed", "deleted", "restored"})
VALID_ACTIONS = SINGLE_ACTIONS | BULK_ACTIONS


async def fanout_state(
    db: Session,
    user_id: int,
    ids: list[int],
    action: str,
    is_admin: bool,
) -> None:
    """Tell the user's other clients that these notifications changed.

    Never raises: the database write has already happened when we get here,
    and a dead socket must not turn a successful state change into a failed
    request.
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"unknown action: {action!r}")
    if not ids and action not in BULK_ACTIONS:
        return

    manager = get_websocket_manager()
    if not manager.is_user_connected(user_id):
        # Nobody listening — skip the work, including the COUNT query.
        return

    try:
        await manager.send_notification_state(user_id, ids, action)
        count = get_notification_service().get_unread_count(
            db, user_id, is_admin=is_admin
        )
        await manager.send_unread_count(user_id, count)
    except Exception as e:
        logger.warning(f"notification fan-out failed for user {user_id}: {e}")
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/api/test_notification_fanout.py -v`
Expected: PASS (6 Tests)

- [ ] **Step 5: Die acht Routen anschließen**

Import in `backend/app/api/routes/notifications.py`:

```python
from app.api.routes._notification_fanout import fanout_state
```

Je Handler **nach** dem Service-Aufruf und der 404-Prüfung, **vor** dem `return`:

`mark_notification_as_read`:
```python
    await fanout_state(
        db, current_user.id, [notification.id], "read",
        is_admin=is_privileged(current_user),
    )
```

`dismiss_notification`:
```python
    await fanout_state(
        db, current_user.id, [notification.id], "dismissed",
        is_admin=is_privileged(current_user),
    )
```

`snooze_notification`:
```python
    await fanout_state(
        db, current_user.id, [notification.id], "snoozed",
        is_admin=is_privileged(current_user),
    )
```

`restore_notification`:
```python
    await fanout_state(
        db, current_user.id, [notification.id], "restored",
        is_admin=is_privileged(current_user),
    )
```

`delete_notification` (liefert 204, die ID steht als Pfadparameter bereit):
```python
    await fanout_state(
        db, current_user.id, [notification_id], "deleted",
        is_admin=is_privileged(current_user),
    )
```

`mark_all_as_read`:
```python
    if count:
        await fanout_state(
            db, current_user.id, [], "read_all",
            is_admin=is_privileged(current_user),
        )
```

`dismiss_all_notifications`:
```python
    if count:
        await fanout_state(
            db, current_user.id, [], "dismissed_all",
            is_admin=is_privileged(current_user),
        )
```

`empty_trash`:
```python
    if count:
        await fanout_state(
            db, current_user.id, [], "deleted_all",
            is_admin=is_privileged(current_user),
        )
```

**Vor dem Schreiben prüfen:** ob `empty_trash` und `restore_notification`
tatsächlich `count` bzw. `notification` zurückgeben — die Rümpfe ab Zeile 260
und 283 gegenlesen und die Variablennamen übernehmen.

- [ ] **Step 6: Volle Testrunde**

Run: `cd backend && .venv/bin/pytest tests/api/test_notification_fanout.py tests/services/test_websocket_manager.py -v`
Expected: PASS

Run: `cd backend && .venv/bin/pytest tests/api -k notification -q`
Expected: keine neuen Fehlschläge gegenüber dem Stand vor der Änderung

- [ ] **Step 7: Committen**

```bash
git add backend/app/api/routes/_notification_fanout.py backend/app/api/routes/notifications.py backend/tests/api/test_notification_fanout.py
git commit -m "feat(notifications): Zustandsaenderungen erreichen die offenen Clients

Lesen, Verwerfen, Snoozen, Loeschen, Wiederherstellen und Papierkorb
leeren verteilten bisher nichts: der WebSocket-Manager wurde in
notifications.py nur fuer connect/disconnect benutzt, send_unread_count
hatte ueberhaupt keinen Produktivaufrufer. Wer auf dem Handy wegwischte,
sah es in einer offenen Web-UI erst nach dem Neuladen.

Die Sammelaktionen tragen bewusst keine IDs: mark_all_as_read kennt
einen Kategoriefilter, 'alles gelesen' waere dann falsch. Sie bedeuten
'neu laden' -- der Client raet nicht, er fragt.

Ohne offene Verbindung passiert nichts, auch keine COUNT-Query. Der
Zaehler kostet sonst eine Datenbankabfrage pro Klick, ohne Zuhoerer.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: WS-Handler `mark_read` nutzt den Fan-out

**Files:**
- Modify: `backend/app/api/routes/notifications.py:641-656` (der `mark_read`-Zweig im WebSocket-Handler)
- Test: `backend/tests/api/test_notification_fanout.py`

**Interfaces:**
- Consumes: `fanout_state` (Task 4).
- Produces: nichts Neues.

**Warum.** Der Zweig antwortet heute mit `websocket.send_json(...)` nur der
auslösenden Verbindung. BaluDesk und BaluApp benutzen diesen Weg; markiert
einer von ihnen über den Socket als gelesen, erfährt eine offene Web-UI nichts.
(Das Tray selbst geht über REST — es hat in v1 keine Meldungsliste, siehe Spec
„Nicht-Ziele". Der Zweig ist trotzdem zu reparieren, nur eben nicht für das
Tray.)

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

An `backend/tests/api/test_notification_fanout.py` anhängen:

```python
@pytest.mark.asyncio
async def test_socket_mark_read_reaches_the_other_connections():
    """Der Socket-Zweig darf nicht nur dem Aufrufer antworten."""
    from app.services.websocket_manager import WebSocketManager

    manager = WebSocketManager()
    caller, other = MagicMock(), MagicMock()
    caller.send_json = AsyncMock()
    other.send_json = AsyncMock()
    await manager.connect(caller, user_id=1)
    await manager.connect(other, user_id=1)

    service = _service(2)
    with patch(
        "app.api.routes._notification_fanout.get_websocket_manager",
        return_value=manager,
    ), patch(
        "app.api.routes._notification_fanout.get_notification_service",
        return_value=service,
    ):
        await fanout_state(MagicMock(), 1, [5], "read", is_admin=False)

    types_seen = [c[0][0]["type"] for c in other.send_json.call_args_list]
    assert "notification_state" in types_seen
    assert "unread_count" in types_seen
```

- [ ] **Step 2: Test laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/api/test_notification_fanout.py::test_socket_mark_read_reaches_the_other_connections -v`
Expected: PASS — der Helfer aus Task 4 leistet das bereits; dieser Test sichert
die Eigenschaft für die Socket-Seite ab, bevor der Zweig umgebaut wird.

- [ ] **Step 3: Den WS-Zweig umbauen**

```python
                elif data.get("type") == "mark_read":
                    notification_id = data.get("payload", {}).get("notification_id")
                    if notification_id:
                        db = SessionLocal()
                        try:
                            service.mark_as_read(
                                db, notification_id, user_id, is_admin=is_admin
                            )
                            await fanout_state(
                                db, user_id, [notification_id], "read",
                                is_admin=is_admin,
                            )
                        except Exception as e:
                            logger.error(f"WebSocket: Failed to mark_read - {e}")
                        finally:
                            db.close()
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/api/test_notification_fanout.py -v`
Expected: PASS

- [ ] **Step 5: Committen**

```bash
git add backend/app/api/routes/notifications.py backend/tests/api/test_notification_fanout.py
git commit -m "fix(notifications): mark_read ueber den Socket erreicht alle Verbindungen

Der Zweig antwortete nur der ausloesenden Verbindung. Markierte BaluDesk
oder BaluApp ueber den Socket als gelesen, erfuhr die offene Web-UI
desselben Nutzers nichts davon.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Frontend zieht bei `notification_state` nach

**Files:**
- Modify: `client/src/hooks/useNotificationSocket.ts` (Options-Interface 16-22, onmessage-Switch ab 110)
- Modify: `client/src/contexts/NotificationContext.tsx` (Hook-Optionen 42-63)
- Test: `client/src/__tests__/hooks/useNotificationSocket.test.tsx`

**Interfaces:**
- Consumes: das WS-Ereignis `notification_state` aus Task 3/4.
- Produces: Option `onNotificationState?: (ids: number[], action: string) => void`.

**Das Testmuster dieser Datei ist eigen — bitte übernehmen, nicht erfinden.**
Es gibt kein `renderHook` und kein `mockSocket`. Stattdessen:
`installFakeWebSocket()` aus `__tests__/helpers/fakeWebSocket.ts`, eine
`Harness`-Komponente, ein `mount()`-Helfer, der über `renderWithProviders`
einloggt und `POST /api/notifications/ws-token` stubt, dazu Fake-Timer. Frames
kommen über `FakeWebSocket.last!.serverSend({...})` nach `serverAccept()`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

An `client/src/__tests__/hooks/useNotificationSocket.test.tsx` anhängen:

```typescript
it('reicht einen notification_state-Frame an den Handler weiter', async () => {
  const onNotificationState = vi.fn();
  await mount({ onNotificationState });

  await act(async () => {
    FakeWebSocket.last!.serverAccept();
  });
  await act(async () => {
    FakeWebSocket.last!.serverSend({
      type: 'notification_state',
      payload: { ids: [7, 8], action: 'read' },
    });
  });

  expect(onNotificationState).toHaveBeenCalledWith([7, 8], 'read');
});

it('uebersteht einen notification_state-Frame ohne Handler', async () => {
  await mount({});

  await act(async () => {
    FakeWebSocket.last!.serverAccept();
  });
  await act(async () => {
    FakeWebSocket.last!.serverSend({
      type: 'notification_state',
      payload: { ids: [1], action: 'deleted' },
    });
  });

  expect(screen.getByTestId('connected').textContent).toBe('verbunden');
});

it('nimmt eine Sammelaktion ohne ids entgegen', async () => {
  const onNotificationState = vi.fn();
  await mount({ onNotificationState });

  await act(async () => {
    FakeWebSocket.last!.serverAccept();
  });
  await act(async () => {
    FakeWebSocket.last!.serverSend({
      type: 'notification_state',
      payload: { ids: [], action: 'read_all' },
    });
  });

  expect(onNotificationState).toHaveBeenCalledWith([], 'read_all');
});
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd client && npx vitest run src/__tests__/hooks/useNotificationSocket.test.tsx`
Expected: FAIL — `onNotificationState` wird nicht aufgerufen

- [ ] **Step 3: Hook erweitern**

Options-Interface:

```typescript
export interface UseNotificationSocketOptions {
  enabled?: boolean;
  onNotification?: (notification: Notification) => void;
  onUnreadCountChange?: (count: number) => void;
  onNotificationState?: (ids: number[], action: string) => void;
  reconnectDelay?: number;
  maxReconnectAttempts?: number;
}
```

Destrukturierung ergänzen, dazu Ref und Sync-Effekt im Muster der Nachbarn
(`useNotificationSocket.ts:52-60`):

```typescript
  const onNotificationStateRef = useRef(onNotificationState);
  useEffect(() => { onNotificationStateRef.current = onNotificationState; }, [onNotificationState]);
```

Im `onmessage`-Switch vor `case 'pong'`:

```typescript
            case 'notification_state': {
              const ids = (data.payload?.ids ?? []) as number[];
              const action = data.payload?.action as string;
              onNotificationStateRef.current?.(ids, action);
              break;
            }
```

Weil der Handler in einem Ref liegt, löst ein inline übergebenes Objektliteral
keinen Reconnect aus — der Effekt, der den Socket aufbaut, hängt nicht daran.

- [ ] **Step 4: Kontext nachziehen, mit Entprellung**

In `client/src/contexts/NotificationContext.tsx`:

```typescript
  // Ein Zustandswechsel anderswo betrifft die ganze Liste, und bei den
  // Sammelaktionen kennen wir den Kategoriefilter des Absenders nicht. Also
  // neu laden statt raten. Entprellt, weil der Fan-out auch auf die eigene
  // Verbindung zurueckkommt: wer 15 Meldungen durchklickt, wuerde sonst 15
  // Nachladevorgaenge gegen ein 30/min-Limit ausloesen.
  const refetchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleRefetch = useCallback(() => {
    if (refetchTimer.current) clearTimeout(refetchTimer.current);
    refetchTimer.current = setTimeout(() => { fetchNotifications(); }, 400);
  }, [fetchNotifications]);

  useEffect(() => () => {
    if (refetchTimer.current) clearTimeout(refetchTimer.current);
  }, []);
```

und in den Hook-Optionen:

```typescript
    onNotificationState: () => { scheduleRefetch(); },
```

**Achtung auf die Reihenfolge:** `fetchNotifications` ist erst nach dem
Hook-Aufruf deklariert (Zeile 65). `scheduleRefetch` muss deshalb ebenfalls
danach stehen, und die Hook-Optionen greifen über eine Ref oder einen
nachgelagerten Effekt darauf zu — beim Schreiben die tatsächliche Reihenfolge
in der Datei prüfen und `scheduleRefetch` notfalls in ein Ref legen, statt die
Deklarationen umzusortieren.

- [ ] **Step 5: Tests, Lint und Build**

Run: `cd client && npx vitest run src/__tests__/hooks/useNotificationSocket.test.tsx`
Expected: PASS

Run: `cd client && npx eslint src/hooks/useNotificationSocket.ts src/contexts/NotificationContext.tsx`
Expected: exit 0

Run: `cd client && npm run build`
Expected: Build grün

- [ ] **Step 6: Committen**

```bash
git add client/src/hooks/useNotificationSocket.ts client/src/contexts/NotificationContext.tsx client/src/__tests__/hooks/useNotificationSocket.test.tsx
git commit -m "feat(notifications): Web-UI zieht bei Zustandsaenderungen anderer Geraete nach

Neuer WS-Ereignistyp notification_state. Der Kontext laedt darauf neu,
statt den Zustand lokal zu raten: bei den Sammelaktionen kennt er den
Kategoriefilter des Absenders nicht, und der Serverstand ist ohnehin die
Wahrheit.

Entprellt, weil der Fan-out auch auf die eigene Verbindung zurueckkommt
-- 15 Klicks sollen nicht 15 Nachladevorgaenge gegen ein 30/min-Limit
ausloesen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

**Ab hier ist Phase A lieferbar.** Kritische Hardware-Meldungen erreichen
offene Clients live (Task 1), gekoppelte Geräte bleiben gekoppelt (Task 2), und
Zustandsänderungen sind geräteübergreifend sichtbar (Tasks 3-6) — alles ohne
eine Zeile Tray-Code.

---

# Phase B — Das Tray

**Eine Entwurfsentscheidung vorweg, die mehrere Probleme auf einmal löst:** Das
Tray gleicht **alle 10 Minuten** per REST neu ab. Das ist kein Notnagel, es ist
die Korrekturinstanz für drei Dinge, die ein reiner Ereignisstrom nicht leisten
kann:

1. **Abgelaufene Snoozes.** `NotificationService.snooze()` setzt nur
   `snoozed_until` und lässt `is_read=False`; `get_unread_count()` und
   `get_user_notifications()` filtern gesnoozte Zeilen heraus, solange die
   Frist läuft. Es gibt **keinen Ablauf-Job** (`notifications/scheduler.py`
   kennt nur `check_and_send_warnings` und `_run_trash_cleanup`). Die Zeile
   taucht einfach wieder in Abfragen auf — ein Neuabgleich sieht sie also, ein
   Ereignisstrom nie.
2. **Verpasste Frames** in der Lücke zwischen Verbindungsabbruch und
   Wiederverbindung.
3. **Drift des Zählers**, falls ein Frame verloren ging.

Ohne diesen Takt wäre ein Snooze faktisch ein „für immer weg": Icon grün bis
zum nächsten Neustart, obwohl das RAID weiter degradiert ist.

### Task 7: Modulgerüst und Token-Speicher

**Files:**
- Create: `backend/baluhost_tray/__init__.py`, `backend/baluhost_tray/config.py`
- Create: `backend/tests/tray/__init__.py`, `backend/tests/tray/test_config.py`

**Interfaces:**
- Consumes: nichts.
- Produces:
  - `@dataclass(frozen=True) class Tokens: access: str; refresh: str`
  - `def save_tokens(tokens: Tokens) -> None`
  - `def load_tokens() -> Tokens | None`
  - `def clear_tokens() -> None`
  - `TOKEN_DIR: Path`, `TOKEN_FILE: Path` (`~/.baluhost/tray-tokens.json`)

**Eigene Datei statt `baluhost_tui.config`:** Dort hält `save_token()` einen
einzelnen String; der Device-Code-Flow liefert access *und* refresh. Zwei
Programme auf derselben Datei würden sich überschreiben.

**Rechte von Anfang an, nicht nachträglich.** Ein `write_text()` mit
anschließendem `chmod(0o600)` legt die Datei erst mit `0666 & ~umask` an —
üblicherweise `0644` — und sie enthält in diesem Fenster ein Token mit den
Rechten des Nutzers. Auf einem Rechner mit mehreren Konten ist das genau das
Rennen, das man nicht will. Deshalb: Verzeichnis mit `0o700`, Datei über
`os.open(..., 0o600)`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_config.py`:

```python
"""Tests for the tray token store."""

import json
import os
import stat

import pytest

from baluhost_tray import config as tray_config


@pytest.fixture(autouse=True)
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setattr(tray_config, "TOKEN_DIR", tmp_path / ".baluhost")
    monkeypatch.setattr(
        tray_config, "TOKEN_FILE", tmp_path / ".baluhost" / "tray-tokens.json"
    )
    return tmp_path


def test_roundtrip():
    tray_config.save_tokens(tray_config.Tokens(access="a", refresh="r"))
    assert tray_config.load_tokens() == tray_config.Tokens(access="a", refresh="r")


def test_missing_file_is_none():
    assert tray_config.load_tokens() is None


def test_file_is_owner_only():
    tray_config.save_tokens(tray_config.Tokens(access="a", refresh="r"))
    assert stat.S_IMODE(tray_config.TOKEN_FILE.stat().st_mode) == 0o600


def test_directory_is_owner_only():
    tray_config.save_tokens(tray_config.Tokens(access="a", refresh="r"))
    assert stat.S_IMODE(tray_config.TOKEN_DIR.stat().st_mode) == 0o700


def test_file_is_never_world_readable_even_briefly(monkeypatch):
    """Die Rechte muessen beim Anlegen stimmen, nicht erst danach.

    Wir fangen den Modus im Moment des Oeffnens ab: ein write_text() mit
    spaeterem chmod wuerde hier 0o666 zeigen.
    """
    seen = {}
    real_open = os.open

    def _spy(path, flags, mode=0o777):
        seen["mode"] = mode
        return real_open(path, flags, mode)

    monkeypatch.setattr(tray_config.os, "open", _spy)
    tray_config.save_tokens(tray_config.Tokens(access="a", refresh="r"))
    assert seen["mode"] == 0o600


def test_corrupt_file_is_none_not_crash():
    tray_config.TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    tray_config.TOKEN_FILE.write_text("{not json")
    assert tray_config.load_tokens() is None


def test_incomplete_file_is_none():
    tray_config.TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    tray_config.TOKEN_FILE.write_text(json.dumps({"access": "a"}))
    assert tray_config.load_tokens() is None


def test_clear_removes_file_and_is_idempotent():
    tray_config.save_tokens(tray_config.Tokens(access="a", refresh="r"))
    tray_config.clear_tokens()
    assert not tray_config.TOKEN_FILE.exists()
    tray_config.clear_tokens()
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_config.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray'`

- [ ] **Step 3: Minimal implementieren**

`backend/baluhost_tray/__init__.py`:

```python
"""BaluHost desktop tray for KDE Plasma.

Shows the state of the box in the panel and delivers critical notifications
to the desktop. Design: docs/superpowers/specs/2026-09-21-desktop-tray-design.md
"""
```

`backend/baluhost_tray/config.py`:

```python
"""Token store for the tray.

Separate from baluhost_tui.config on purpose: that one holds a single token
string, the device code flow yields an access *and* a refresh token, and two
programs writing the same file would clobber each other.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

TOKEN_DIR = Path.home() / ".baluhost"
TOKEN_FILE = TOKEN_DIR / "tray-tokens.json"


@dataclass(frozen=True)
class Tokens:
    access: str
    refresh: str


def save_tokens(tokens: Tokens) -> None:
    """Write tokens, owner-only from the first byte.

    write_text() + chmod would create the file world-readable for the length
    of the write, with a token inside it. On a multi-user box that is a real
    window, so the mode goes into the open() call instead.
    """
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(TOKEN_DIR, 0o700)

    payload = json.dumps(asdict(tokens))
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    # An existing file keeps its old mode through O_CREAT, so enforce it.
    os.chmod(TOKEN_FILE, 0o600)


def load_tokens() -> Tokens | None:
    """Read tokens, or None if absent, unreadable or incomplete."""
    if not TOKEN_FILE.exists():
        return None
    try:
        raw = json.loads(TOKEN_FILE.read_text())
        return Tokens(access=raw["access"], refresh=raw["refresh"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def clear_tokens() -> None:
    """Remove the token file. Idempotent."""
    TOKEN_FILE.unlink(missing_ok=True)
```

`backend/tests/tray/__init__.py` bleibt leer.

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_config.py -v`
Expected: PASS (8 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray backend/tests/tray
git commit -m "feat(tray): Modulgeruest und Token-Speicher

Eigene Token-Datei statt der TUI-Datei: der Device-Code-Flow liefert
access und refresh, waehrend baluhost_tui.config einen einzelnen String
haelt.

Die Rechte stehen im open()-Aufruf, nicht in einem chmod danach. Sonst
existiert die Datei fuer die Dauer des Schreibens mit 0644 und einem
Token darin.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Zustandsableitung — die Farbe des Icons

**Files:**
- Create: `backend/baluhost_tray/state.py`
- Test: `backend/tests/tray/test_state.py`

**Interfaces:**
- Consumes: nichts.
- Produces:
  - `class IconState(str, Enum): OFFLINE="offline"; OK="ok"; WARNING="warning"; CRITICAL="critical"`
  - `@dataclass class TrayState` mit `connected: bool`, `unread: dict[int, str]`
  - `def icon_state(self) -> IconState`
  - `def apply_snapshot(self, items: list[tuple[int, str]]) -> None`
  - `def add(self, notification_id: int, notification_type: str) -> None`
  - `def remove(self, ids: list[int]) -> None`
  - `def set_connected(self, connected: bool) -> None`
  - `def unread_count(self) -> int`
  - `def tooltip(self) -> str`

**Der ganze Sinn dieser Datei:** Sie ist die Logik ohne Qt. `tray.py` bleibt
dünn, damit hier geprüft werden kann, was zählt.

**Der Tooltip sagt die Wahrheit, nicht mehr.** Grün heißt „nichts Ungelesenes",
nicht „Anlage gesund" — wer eine Meldung liest, während das RAID degradiert
bleibt, bekommt ein grünes Icon. Der Tooltip benennt deshalb Ungelesenes und
verspricht keinen Gesundheitszustand.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_state.py`:

```python
"""Tests for the tray state machine — the icon colour is derived here."""

import pytest

from baluhost_tray.state import IconState, TrayState


@pytest.mark.parametrize(
    "connected,unread,expected",
    [
        (False, [], IconState.OFFLINE),
        (False, [(1, "critical")], IconState.OFFLINE),
        (True, [], IconState.OK),
        (True, [(1, "info")], IconState.OK),
        (True, [(1, "warning")], IconState.WARNING),
        (True, [(1, "critical")], IconState.CRITICAL),
        (True, [(1, "warning"), (2, "critical")], IconState.CRITICAL),
        (True, [(1, "critical"), (2, "warning")], IconState.CRITICAL),
    ],
)
def test_icon_state(connected, unread, expected):
    state = TrayState()
    state.set_connected(connected)
    state.apply_snapshot(unread)
    assert state.icon_state() == expected


def test_snapshot_replaces_previous_content():
    """Nach einer Offline-Phase ist der Snapshot die Wahrheit, kein Merge."""
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "critical")])
    state.apply_snapshot([(2, "warning")])
    assert state.icon_state() == IconState.WARNING


def test_snapshot_brings_back_an_expired_snooze():
    """Gesnoozte Meldungen filtert der Server heraus und spaeter wieder ein.
    Der periodische Neuabgleich ist der einzige Weg zurueck auf rot."""
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "critical")])
    state.remove([1])                       # gesnoozt
    assert state.icon_state() == IconState.OK
    state.apply_snapshot([(1, "critical")])  # Frist abgelaufen
    assert state.icon_state() == IconState.CRITICAL


def test_remove_clears_colour():
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "critical")])
    state.remove([1])
    assert state.icon_state() == IconState.OK


def test_remove_unknown_id_is_harmless():
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "critical")])
    state.remove([99])
    assert state.icon_state() == IconState.CRITICAL


def test_add_upgrades_colour():
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "warning")])
    state.add(2, "critical")
    assert state.icon_state() == IconState.CRITICAL


def test_unknown_type_does_not_colour():
    """Ein neuer Typ im Backend darf das Icon nicht auf rot raten."""
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "moonphase")])
    assert state.icon_state() == IconState.OK


def test_tooltip_counts_unread_without_promising_health():
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "critical"), (2, "warning")])
    assert "2" in state.tooltip()

    state.apply_snapshot([])
    assert state.tooltip() == "BaluHost — nichts Ungelesenes"


def test_tooltip_says_offline_when_disconnected():
    state = TrayState()
    state.set_connected(False)
    assert "erreichbar" in state.tooltip()
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_state.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray.state'`

- [ ] **Step 3: Minimal implementieren**

`backend/baluhost_tray/state.py`:

```python
"""Tray state: which notifications are unread, and what colour that makes.

No Qt in here on purpose. tray.py stays thin so everything worth testing is
testable without a display, a bus or a panel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class IconState(str, Enum):
    OFFLINE = "offline"
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class TrayState:
    """Unread notifications by id, plus whether we can reach the backend."""

    connected: bool = False
    unread: dict[int, str] = field(default_factory=dict)

    def set_connected(self, connected: bool) -> None:
        self.connected = connected

    def apply_snapshot(self, items: list[tuple[int, str]]) -> None:
        """Replace the whole set. The REST snapshot is the truth, not a merge.

        This is also how a snoozed notification comes back: the server hides
        it while the snooze runs and returns it afterwards, and nothing else
        would ever re-colour the icon.
        """
        self.unread = {nid: ntype for nid, ntype in items}

    def add(self, notification_id: int, notification_type: str) -> None:
        self.unread[notification_id] = notification_type

    def remove(self, ids: list[int]) -> None:
        for nid in ids:
            self.unread.pop(nid, None)

    def unread_count(self) -> int:
        return len(self.unread)

    def icon_state(self) -> IconState:
        """Worst unread severity wins; no connection beats everything.

        An unknown type counts as harmless: a new NotificationType in the
        backend must not make the panel guess red.
        """
        if not self.connected:
            return IconState.OFFLINE
        types = set(self.unread.values())
        if "critical" in types:
            return IconState.CRITICAL
        if "warning" in types:
            return IconState.WARNING
        return IconState.OK

    def tooltip(self) -> str:
        """What the icon actually knows — no health promise.

        Green means "nothing unread", not "the box is healthy": reading a
        notification clears the colour while the degraded array stays
        degraded. Saying so here keeps the icon honest.
        """
        if not self.connected:
            return "BaluHost — nicht erreichbar"
        count = self.unread_count()
        if not count:
            return "BaluHost — nichts Ungelesenes"
        if count == 1:
            return "BaluHost — 1 ungelesene Meldung"
        return f"BaluHost — {count} ungelesene Meldungen"
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_state.py -v`
Expected: PASS (16 Tests, davon 8 aus der Parametrisierung)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray/state.py backend/tests/tray/test_state.py
git commit -m "feat(tray): Zustandsableitung fuer die Icon-Farbe

Schlimmste ungelesene Schwere gewinnt, fehlende Verbindung schlaegt
alles. Ein unbekannter Typ faerbt bewusst nicht: ein neuer
NotificationType im Backend darf das Panel nicht auf rot raten.

Der Tooltip zaehlt Ungelesenes und verspricht keinen Gesundheitszustand
-- gruen heisst 'nichts Ungelesenes', nicht 'Anlage gesund'.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Warteschlange für zurückgehaltene Popups

**Files:**
- Modify: `backend/baluhost_tray/state.py`
- Test: `backend/tests/tray/test_state.py`

**Interfaces:**
- Consumes: nichts.
- Produces:
  - `@dataclass(frozen=True) class PendingPopup: notification_id: int; title: str; message: str`
  - `class PopupQueue` mit `hold(popup)`, `release() -> list[PendingPopup]`,
    `summary() -> tuple[str, str] | None`, `is_empty() -> bool`
  - `SUMMARY_THRESHOLD = 4`

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

An `backend/tests/tray/test_state.py` anhängen:

```python
from baluhost_tray.state import PendingPopup, PopupQueue


def _popup(n: int) -> PendingPopup:
    return PendingPopup(notification_id=n, title=f"Titel {n}", message=f"Text {n}")


def test_queue_starts_empty():
    assert PopupQueue().is_empty()


def test_release_returns_and_clears():
    queue = PopupQueue()
    queue.hold(_popup(1))
    queue.hold(_popup(2))
    released = queue.release()
    assert [p.notification_id for p in released] == [1, 2]
    assert queue.is_empty()


def test_below_threshold_no_summary():
    queue = PopupQueue()
    for n in (1, 2, 3):
        queue.hold(_popup(n))
    assert queue.summary() is None


def test_at_threshold_summarises():
    queue = PopupQueue()
    for n in (1, 2, 3, 4):
        queue.hold(_popup(n))
    title, message = queue.summary()
    assert "4" in title or "4" in message


def test_same_notification_held_once():
    """Ein Reconnect darf dieselbe Meldung nicht doppelt zustellen."""
    queue = PopupQueue()
    queue.hold(_popup(1))
    queue.hold(_popup(1))
    assert len(queue.release()) == 1
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_state.py -k Queue -v`
Expected: FAIL mit `ImportError: cannot import name 'PendingPopup'`

- [ ] **Step 3: Minimal implementieren**

An `backend/baluhost_tray/state.py` anhängen:

```python
SUMMARY_THRESHOLD = 4


@dataclass(frozen=True)
class PendingPopup:
    notification_id: int
    title: str
    message: str


class PopupQueue:
    """Popups held back while a game is on screen or quiet mode runs.

    Held, not dropped: when the reason goes away the user still gets told. A
    reconnect may replay the same notification, so entries are keyed by id.
    """

    def __init__(self) -> None:
        self._held: dict[int, PendingPopup] = {}

    def hold(self, popup: PendingPopup) -> None:
        self._held.setdefault(popup.notification_id, popup)

    def is_empty(self) -> bool:
        return not self._held

    def release(self) -> list[PendingPopup]:
        """Return everything held and forget it."""
        items = list(self._held.values())
        self._held.clear()
        return items

    def summary(self) -> tuple[str, str] | None:
        """One line instead of a burst, once it would be a burst."""
        if len(self._held) < SUMMARY_THRESHOLD:
            return None
        return (
            "BaluHost",
            f"{len(self._held)} neue kritische Meldungen",
        )
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_state.py -v`
Expected: PASS (21 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray/state.py backend/tests/tray/test_state.py
git commit -m "feat(tray): Warteschlange fuer zurueckgehaltene Popups

Zurueckhalten statt verwerfen: faellt der Grund weg, wird zugestellt, ab
vier Eintraegen als Sammelmeldung. Eintraege sind nach ID verschluesselt,
damit ein Reconnect dieselbe Meldung nicht doppelt zustellt.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: Gaming-Endpunkt im steam_gaming-Plugin

**Files:**
- Modify: `backend/app/plugins/installed/steam_gaming/routes.py`
- Modify: `backend/app/plugins/installed/steam_gaming/models.py`
- Test: `backend/tests/plugins/test_steam_gaming_session_state.py`

**Interfaces:**
- Consumes: `app.services.power.gaming_presence`.
- Produces: `GET /api/plugins/steam_gaming/session-state` → `{"gaming_active": bool}`

**Welcher Zustand gefragt wird — und warum nicht der naheliegende.**
`gaming_mode_on_screen()` ist `_marker_is_active() and displays_on()`, und der
Marker bedeutet laut `steam_gaming/CLAUDE.md:30` ausdrücklich „Marker file
recording that *we* started gaming mode". Er wird von
`launch.start_gaming_mode()` gesetzt — also nur, wenn das Spiel über BaluHosts
Menü oder Launch-Route gestartet wurde. Ein Spiel, das direkt in Steam
angeklickt wird, setzt ihn nicht. Das ist der Normalfall, nicht die Ausnahme,
und ein Gate auf dieser Grundlage wäre fast immer offen.

Daneben liegt im selben Modul `game_is_running()` (`gaming_presence.py:80`) —
die echte „läuft ein Spiel"-Quelle, dieselbe, die Pill, Ledger und Panel
benutzen. Der Endpunkt kombiniert beides:

```
(game_is_running() or marker gesetzt) and displays_on()
```

Die Display-Bedingung aus `gaming_mode_on_screen()` bleibt erhalten: Sie ist
es, die einen verwaisten Marker von selbst verfallen lässt.

**Zwei Fallen dieser Datei:**
1. **Kein `from __future__ import annotations`** — der Warnkommentar steht in
   Zeile 5-7. Zurückgestellte Annotationen werden hinter dem slowapi-Wrapper zu
   ForwardRefs, und jeder Request wird 422.
2. **Direkter Funktionsaufruf im Test scheitert.** `@user_limiter.limit` greift
   auf `request` zu; `request=None` wirft „parameter `request` must be an
   instance of starlette.requests.Request", `MagicMock(spec=Request)` scheitert
   im key_func. Der Test geht über `TestClient`, Muster in
   `backend/tests/plugins/test_steam_gaming_routes.py`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/plugins/test_steam_gaming_session_state.py` — Dateiname flach,
wie die übrigen Steam-Tests; ein Unterverzeichnis `steam_gaming/` gibt es
nicht:

```python
"""The gaming gate the tray asks before it shows a popup.

Driven through TestClient on purpose: the route carries @user_limiter.limit,
and slowapi rejects anything that is not a real starlette Request.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps
from app.plugins.installed.steam_gaming import routes

BASE = "/api/plugins/steam_gaming"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router, prefix=BASE)
    app.dependency_overrides[deps.get_current_user] = lambda: object()
    return TestClient(app)


@pytest.mark.parametrize(
    "running,marker,displays,expected",
    [
        (True, False, True, True),    # direkt in Steam gestartet
        (False, True, True, True),    # ueber BaluHost gestartet
        (True, False, False, False),  # Spiel laeuft, Bildschirm aus
        (False, True, False, False),  # verwaister Marker, Bildschirm aus
        (False, False, True, False),  # nichts laeuft
    ],
)
def test_session_state(client, running, marker, displays, expected):
    with patch(
        "app.services.power.gaming_presence.game_is_running", return_value=running
    ), patch(
        "app.services.power.gaming_presence._marker_is_active", return_value=marker
    ), patch(
        "app.services.power.gaming_presence.displays_on", return_value=displays
    ):
        response = client.get(f"{BASE}/session-state")

    assert response.status_code == 200
    assert response.json()["gaming_active"] is expected


def test_unreadable_presence_counts_as_not_gaming(client):
    """Fail open: lieber eine Meldung zu viel als eine verschluckte."""
    with patch(
        "app.services.power.gaming_presence.game_is_running",
        side_effect=OSError("sysfs gone"),
    ):
        response = client.get(f"{BASE}/session-state")

    assert response.status_code == 200
    assert response.json()["gaming_active"] is False
```

**Vor dem Schreiben:** `test_steam_gaming_routes.py:1-30` lesen und den dortigen
Aufbau von App, Router-Prefix und `dependency_overrides` exakt übernehmen —
insbesondere, welche Dependency das Plugin tatsächlich verlangt.

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/plugins/test_steam_gaming_session_state.py -v`
Expected: FAIL mit 404 — die Route existiert noch nicht

- [ ] **Step 3: Antwortmodell ergänzen**

In `backend/app/plugins/installed/steam_gaming/models.py` — **`Field` ist dort
bisher nicht importiert**, Zeile 7 holt nur `BaseModel`:

```python
from pydantic import BaseModel, Field
```

```python
class SessionStateResponse(BaseModel):
    """Whether a gaming session is on screen right now."""

    gaming_active: bool = Field(
        ..., description="A game is running or gaming mode is up, and a display is lit"
    )
```

- [ ] **Step 4: Endpunkt implementieren**

In `backend/app/plugins/installed/steam_gaming/routes.py` — **`deps` ist dort
bisher nicht importiert**, Zeile 15 holt nur `require_power_launch_games`:

```python
from app.api import deps
from app.plugins.installed.steam_gaming.models import SessionStateResponse
```

**Rechte-Entscheidung, bewusst abweichend vom Rest der Datei:** Die beiden
vorhandenen Routen hängen an `require_power_launch_games`, weil sie Spiele
auflisten und starten. `session-state` gibt einen einzelnen Boolean zurück,
den das Tray jedes Mal braucht, bevor es ein Popup zeigt. Es an das Startrecht
zu binden, hieße dem Tray das Recht zu geben, Spiele zu starten. Deshalb
`get_current_user`.

```python
@router.get("/session-state", response_model=SessionStateResponse)
@user_limiter.limit(_READ_LIMIT)
async def session_state(
    request: Request,
    response: Response,
    current_user=Depends(deps.get_current_user),
) -> SessionStateResponse:
    """Whether a gaming session is on screen — the tray gates popups on this.

    Not gaming_mode_on_screen(): its marker means "*we* started gaming mode"
    (see CLAUDE.md), so a game launched straight from Steam would not count —
    which is the common case. game_is_running() is the real source, the marker
    stays as a second path for Big Picture, and the lit-display requirement is
    what lets an abandoned session expire on its own.

    Reads a marker file and sysfs, so it runs off the event loop. Any read
    error counts as "not gaming": rather one notification too many than a
    swallowed alarm.
    """
    from app.services.power import gaming_presence

    def _probe() -> bool:
        active = gaming_presence.game_is_running() or gaming_presence._marker_is_active()
        return bool(active and gaming_presence.displays_on())

    try:
        active = await asyncio.to_thread(_probe)
    except Exception:
        active = False
    return SessionStateResponse(gaming_active=active)
```

`import asyncio` steht bereits in Zeile 8.

**Wenn `_marker_is_active` als privat stört:** in `gaming_presence.py` eine
öffentliche `gaming_session_on_screen()` mit genau dieser Logik ergänzen und
hier aufrufen. Dann wandern auch die Tests aus Step 1 dorthin. Beides ist
vertretbar — die Entscheidung gehört in den Commit, nicht in eine stille
Abweichung.

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/plugins/test_steam_gaming_session_state.py -v`
Expected: PASS (6 Tests)

Run: `cd backend && .venv/bin/pytest tests/plugins -k steam_gaming -q`
Expected: bestehende Steam-Tests unverändert grün

- [ ] **Step 6: Committen**

```bash
git add backend/app/plugins/installed/steam_gaming/routes.py backend/app/plugins/installed/steam_gaming/models.py backend/tests/plugins/test_steam_gaming_session_state.py
git commit -m "feat(steam_gaming): session-state meldet laufende Spielsitzung

Grundlage ist game_is_running(), nicht der Marker allein: der bedeutet
laut CLAUDE.md 'did we start gaming mode' und bleibt leer, wenn das
Spiel direkt in Steam angeklickt wird -- also im Normalfall. Der Marker
bleibt als zweiter Pfad fuer Big Picture, die Display-Bedingung laesst
eine abgebrochene Sitzung von selbst verfallen.

Bewusst an get_current_user statt an require_power_launch_games: das
Tray fragt hier einen Boolean ab und soll dafuer nicht das Recht
bekommen, Spiele zu starten.

Lesefehler gelten als 'nicht im Gaming-Modus' -- lieber eine Meldung zu
viel als eine verschluckte.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: Gerätekopplung (Device-Code-Flow)

**Files:**
- Create: `backend/baluhost_tray/pairing.py`
- Test: `backend/tests/tray/test_pairing.py`

**Interfaces:**
- Consumes: `baluhost_tray.config.Tokens`.
- Produces:
  - `@dataclass(frozen=True) class PendingPairing: device_code; user_code; verification_url; interval; expires_in`
  - `def start_pairing(client) -> PendingPairing`
  - `def poll_once(client, device_code: str) -> Tokens | None`
  - `class PairingDenied(Exception)`, `class PairingExpired(Exception)`
  - `def device_identity() -> tuple[str, str]`

**Die Pfade heißen anders als erwartet.** Der Router trägt
`prefix="/desktop-pairing"` (`routes/desktop_pairing.py:25`) und wird ohne
weiteren Prefix eingebunden (`routes/__init__.py:77`), `api_prefix` ist `/api`.
Richtig sind also **`/api/desktop-pairing/device-code`** und
**`/api/desktop-pairing/poll`**. Unter `/api/desktop/` hängt nichts;
`desktop.py` liegt auf `/api/system/sleep/desktop`.

**Statuscode vor Body.** `poll_device_code` antwortet bei unbekanntem
`device_code` mit 404, und die Route ist auf **12/Minute** je IP begrenzt
(`core/rate_limiter.py:161`, `desktop_pairing_poll`). Der Service liefert
`interval=5` — ein Flow, der exakt alle 5 s pollt, sitzt genau auf der Grenze.
Deshalb: Statuscode zuerst auswerten, 429 als „weiter warten" behandeln, und
im Flow `interval + 1` schlafen.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_pairing.py`:

```python
"""Tests for the tray's device code pairing."""

from unittest.mock import MagicMock

import pytest

from baluhost_tray import pairing
from baluhost_tray.config import Tokens


def _client(payload: dict, status_code: int = 200) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    client.post.return_value = response
    return client


def test_start_pairing_uses_the_real_path():
    client = _client({
        "device_code": "dc",
        "user_code": "123456",
        "verification_url": "https://baluhost.local/devices?pair=1",
        "expires_in": 600,
        "interval": 5,
    })

    pending = pairing.start_pairing(client)

    assert pending.user_code == "123456"
    assert pending.interval == 5
    path = client.post.call_args[0][0]
    assert path == "/api/desktop-pairing/device-code"
    body = client.post.call_args[1]["json"]
    assert body["platform"] == "linux"
    assert body["device_id"] and body["device_name"]


def test_poll_uses_the_real_path():
    client = _client({"status": "authorization_pending"})
    pairing.poll_once(client, "dc")
    assert client.post.call_args[0][0] == "/api/desktop-pairing/poll"


def test_poll_pending_returns_none():
    assert pairing.poll_once(_client({"status": "authorization_pending"}), "dc") is None


def test_poll_approved_returns_tokens():
    client = _client({
        "status": "approved",
        "access_token": "at",
        "refresh_token": "rt",
        "token_type": "bearer",
    })
    assert pairing.poll_once(client, "dc") == Tokens(access="at", refresh="rt")


def test_poll_denied_raises():
    with pytest.raises(pairing.PairingDenied):
        pairing.poll_once(_client({"status": "denied"}), "dc")


def test_poll_expired_raises():
    with pytest.raises(pairing.PairingExpired):
        pairing.poll_once(_client({"status": "expired"}), "dc")


def test_rate_limited_means_keep_waiting():
    """429 ist kein Abbruch — die Poll-Route erlaubt nur 12/Minute."""
    assert pairing.poll_once(_client({}, status_code=429), "dc") is None


def test_unknown_device_code_raises_expired_not_typeerror():
    """404 ohne Body darf keinen 'unexpected status: None'-Absturz geben."""
    with pytest.raises(pairing.PairingExpired):
        pairing.poll_once(_client({}, status_code=404), "dc")


def test_server_error_keeps_waiting():
    assert pairing.poll_once(_client({}, status_code=503), "dc") is None


def test_device_identity_is_stable():
    first = pairing.device_identity()
    second = pairing.device_identity()
    assert first == second
    assert first[0] and first[1]
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_pairing.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray.pairing'`

- [ ] **Step 3: Minimal implementieren**

`backend/baluhost_tray/pairing.py`:

```python
"""Device code pairing, reusing the flow BaluDesk uses.

Nothing to type in: the tray shows a six digit code, the user approves it in
the web UI, and the pairing can be revoked per device there (which only works
because Task 2 stores the refresh token's jti).
"""

from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass
from pathlib import Path

from baluhost_tray.config import Tokens

# The router carries prefix="/desktop-pairing"; "/api/desktop/..." is not bound.
DEVICE_CODE_PATH = "/api/desktop-pairing/device-code"
POLL_PATH = "/api/desktop-pairing/poll"

_MACHINE_ID_PATHS = (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id"))


class PairingDenied(Exception):
    """The user rejected this device in the web UI."""


class PairingExpired(Exception):
    """The code timed out, or the backend no longer knows it."""


@dataclass(frozen=True)
class PendingPairing:
    device_code: str
    user_code: str
    verification_url: str
    interval: int
    expires_in: int


def device_identity() -> tuple[str, str]:
    """A stable id for this machine plus a human readable name.

    Falls back to a random uuid only if no machine-id is readable; pairing
    still works, the device just shows up as a new one after a reinstall.
    """
    device_id = ""
    for path in _MACHINE_ID_PATHS:
        try:
            device_id = path.read_text().strip()
        except OSError:
            continue
        if device_id:
            break
    if not device_id:
        device_id = str(uuid.uuid4())
    return device_id, f"BaluHost Tray auf {socket.gethostname()}"


def start_pairing(client) -> PendingPairing:
    """Ask the backend for a device code."""
    device_id, device_name = device_identity()
    response = client.post(
        DEVICE_CODE_PATH,
        json={
            "device_id": device_id,
            "device_name": device_name,
            "platform": "linux",
        },
    )
    data = response.json()
    return PendingPairing(
        device_code=data["device_code"],
        user_code=data["user_code"],
        verification_url=data["verification_url"],
        interval=int(data.get("interval", 5)),
        expires_in=int(data.get("expires_in", 600)),
    )


def poll_once(client, device_code: str) -> Tokens | None:
    """One poll. None means keep waiting.

    The status code is read before the body: the route answers 404 for an
    unknown device_code and 429 when the 12/minute limit bites, and neither
    carries a "status" field. Reading the body first turned both into an
    unexplained crash.
    """
    response = client.post(POLL_PATH, json={"device_code": device_code})

    if response.status_code == 429:
        return None            # Limit erreicht — der naechste Versuch kommt eh
    if response.status_code == 404:
        raise PairingExpired("backend does not know this device code")
    if response.status_code >= 500:
        return None            # Serverseitig, voruebergehend
    if response.status_code >= 400:
        raise PairingExpired(f"pairing refused: {response.status_code}")

    data = response.json()
    status = data.get("status")

    if status == "authorization_pending":
        return None
    if status == "denied":
        raise PairingDenied("device was denied in the web UI")
    if status == "expired":
        raise PairingExpired("device code expired before approval")
    if status == "approved":
        return Tokens(access=data["access_token"], refresh=data["refresh_token"])
    raise PairingExpired(f"unexpected pairing status: {status!r}")
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_pairing.py -v`
Expected: PASS (10 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray/pairing.py backend/tests/tray/test_pairing.py
git commit -m "feat(tray): Geraetekopplung ueber den vorhandenen Device-Code-Flow

Die Pfade heissen /api/desktop-pairing/..., nicht /api/desktop/... --
der Router traegt prefix='/desktop-pairing'.

Statuscode vor Body: die Poll-Route antwortet 404 fuer unbekannte Codes
und 429 ab 12 Anfragen pro Minute, und keine der beiden Antworten hat
ein 'status'-Feld. 429 heisst weiter warten, nicht abbrechen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 12: Sitzung, Token-Erneuerung und ws-Token

**Files:**
- Create: `backend/baluhost_tray/session.py`
- Test: `backend/tests/tray/test_session.py`

**Interfaces:**
- Consumes: `baluhost_tray.config`, `baluhost_tui.client.BackendClient`.
- Produces:
  - `class AuthExpired(Exception)` — 401, mit `refresh_access()` zu beheben
  - `class TemporaryFailure(Exception)` — 429/5xx/Netz, Backoff
  - `class PairingLost(Exception)` — endgültig, Kopplung weg
  - `class Session` mit `client()`, `ws_url()`, `ws_token()`,
    `refresh_access()`, `forget()`

**`BackendClient` nimmt kein `base_url`.** Die Signatur ist
`__init__(self, socket_path=None, server=None, token=None, timeout=30.0, *, _client=None)`
(`baluhost_tui/client.py:49`). Richtig ist **`BackendClient(server=base_url)`**.
Ohne `server=` entscheidet `resolve_transport()` und greift auf
`/run/baluhost/local.sock` zurück — ausgerechnet den Companion-Kanal, den die
Spec bewusst verwirft.

**`/auth/refresh` gibt kein neues Refresh-Token zurück.** Die Antwort ist
`TokenResponse` mit `access_token`, `token_type`, `user`
(`schemas/auth.py:82-85`); der Docstring sagt ausdrücklich, dass nicht rotiert
wird. Das alte Refresh-Token bleibt also in Gebrauch, bis es abläuft.

**Drei Fehlerklassen statt einer.** Ein 429 auf `/ws-token` — die Route ist mit
`user_operations` = 30/Minute limitiert — darf keine Entkopplung auslösen. Ein
Backoff, der bei 1 s beginnt, brennt das Kontingent sonst in einer halben
Minute durch und das Tray würde sich selbst abmelden.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_session.py`:

```python
"""Tests for token lifecycle in the tray session."""

from unittest.mock import MagicMock

import pytest

from baluhost_tray import config as tray_config
from baluhost_tray.session import AuthExpired, PairingLost, Session, TemporaryFailure


@pytest.fixture(autouse=True)
def tmp_tokens(tmp_path, monkeypatch):
    monkeypatch.setattr(tray_config, "TOKEN_DIR", tmp_path)
    monkeypatch.setattr(tray_config, "TOKEN_FILE", tmp_path / "tray-tokens.json")
    tray_config.save_tokens(tray_config.Tokens(access="old", refresh="rt"))


def _response(status_code: int, payload: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload or {}
    return response


def _session(response: MagicMock) -> Session:
    session = Session("http://localhost:8000")
    session._client = MagicMock()
    session._client.post.return_value = response
    return session


@pytest.mark.parametrize(
    "base,expected",
    [
        ("http://localhost:8000", "ws://localhost:8000/api/notifications/ws"),
        ("https://baluhost.local", "wss://baluhost.local/api/notifications/ws"),
        ("http://localhost:8000/", "ws://localhost:8000/api/notifications/ws"),
    ],
)
def test_ws_url(base, expected):
    assert Session(base).ws_url() == expected


def test_ws_token_returned():
    assert _session(_response(200, {"token": "wt"})).ws_token() == "wt"


def test_ws_token_401_is_recoverable():
    with pytest.raises(AuthExpired):
        _session(_response(401)).ws_token()


def test_ws_token_429_is_temporary_not_fatal():
    """Ein Ratelimit darf keine Entkopplung ausloesen."""
    with pytest.raises(TemporaryFailure):
        _session(_response(429)).ws_token()


def test_ws_token_500_is_temporary():
    with pytest.raises(TemporaryFailure):
        _session(_response(503)).ws_token()


def test_refresh_updates_access_and_keeps_refresh():
    """Der Server rotiert das Refresh-Token nicht — es muss erhalten bleiben."""
    session = _session(_response(200, {"access_token": "new", "token_type": "bearer"}))
    session.refresh_access()

    assert tray_config.load_tokens().access == "new"
    assert tray_config.load_tokens().refresh == "rt"
    session._client.set_token.assert_called_with("new")


def test_refresh_401_forgets_pairing():
    session = _session(_response(401))
    with pytest.raises(PairingLost):
        session.refresh_access()
    assert tray_config.load_tokens() is None


def test_refresh_429_keeps_the_pairing():
    session = _session(_response(429))
    with pytest.raises(TemporaryFailure):
        session.refresh_access()
    assert tray_config.load_tokens() is not None


def test_forget_clears_tokens():
    session = _session(_response(200))
    session.forget()
    assert tray_config.load_tokens() is None
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_session.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray.session'`

- [ ] **Step 3: Minimal implementieren**

`backend/baluhost_tray/session.py`:

```python
"""Token lifecycle for the tray.

Three error classes, not one. A 429 on /ws-token (30/minute) must never cost
the pairing: a backoff that starts at one second would burn the allowance in
half a minute and the tray would sign itself out.
"""

from __future__ import annotations

from baluhost_tray import config as tray_config
from baluhost_tui.client import BackendClient

WS_TOKEN_PATH = "/api/notifications/ws-token"
REFRESH_PATH = "/api/auth/refresh"
WS_PATH = "/api/notifications/ws"


class AuthExpired(Exception):
    """The access token is stale — refresh_access() should fix it."""


class TemporaryFailure(Exception):
    """Rate limit, server error or network. Back off and try again."""


class PairingLost(Exception):
    """The refresh token no longer works — the device must pair again."""


class Session:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        tokens = tray_config.load_tokens()
        # BackendClient takes `server=`, not `base_url=`. Without it
        # resolve_transport() falls back to /run/baluhost/local.sock — the
        # companion channel this design deliberately does not use.
        self._client = BackendClient(server=self._base_url)
        if tokens:
            self._client.set_token(tokens.access)

    def client(self) -> BackendClient:
        return self._client

    def ws_url(self) -> str:
        """Websocket URL derived from the base URL (http→ws, https→wss)."""
        scheme = "wss" if self._base_url.startswith("https") else "ws"
        host = self._base_url.split("://", 1)[-1]
        return f"{scheme}://{host}{WS_PATH}"

    def ws_token(self) -> str:
        """Short lived (60 s) token for the notification websocket.

        Fetched per connection attempt rather than cached — caching a token
        that lives one minute only produces a stale one after every outage.
        """
        response = self._client.post(WS_TOKEN_PATH)
        code = response.status_code
        if code == 200:
            return response.json()["token"]
        if code == 401:
            raise AuthExpired("ws-token rejected the access token")
        if code == 429 or code >= 500:
            raise TemporaryFailure(f"ws-token unavailable: {code}")
        raise PairingLost(f"ws-token refused: {code}")

    def refresh_access(self) -> None:
        """Exchange the refresh token for a fresh access token.

        The server does not rotate the refresh token (see TokenResponse), so
        the stored one is kept. Only a 401 means the pairing is gone; a rate
        limit must not delete credentials.
        """
        tokens = tray_config.load_tokens()
        if not tokens:
            raise PairingLost("no tokens stored")

        response = self._client.post(
            REFRESH_PATH, json={"refresh_token": tokens.refresh}
        )
        code = response.status_code

        if code == 429 or code >= 500:
            raise TemporaryFailure(f"refresh unavailable: {code}")
        if code != 200:
            self.forget()
            raise PairingLost(f"refresh refused: {code}")

        data = response.json()
        new_tokens = tray_config.Tokens(
            access=data["access_token"],
            refresh=tokens.refresh,
        )
        tray_config.save_tokens(new_tokens)
        self._client.set_token(new_tokens.access)

    def forget(self) -> None:
        tray_config.clear_tokens()
        self._client.clear_token()
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_session.py -v`
Expected: PASS (12 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray/session.py backend/tests/tray/test_session.py
git commit -m "feat(tray): Sitzung mit Token-Erneuerung und ws-Token

BackendClient nimmt server=, nicht base_url= -- ohne das faellt
resolve_transport auf den Companion-Unix-Socket zurueck.

Drei Fehlerklassen statt einer: ein 429 auf /ws-token (30/Minute) darf
keine Entkopplung ausloesen, sonst meldet sich das Tray bei einem
flatternden Backend selbst ab. Nur 401 auf dem Refresh ist endgueltig.

/auth/refresh rotiert das Refresh-Token nicht, also bleibt das alte
erhalten.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 13: WebSocket-Beobachter — Snapshot, Frames, Backoff

**Files:**
- Create: `backend/baluhost_tray/watch.py`
- Test: `backend/tests/tray/test_watch.py`

**Interfaces:**
- Consumes: `Session` (Task 12), `TrayState`, `PendingPopup` (Tasks 8/9).
- Produces:
  - `def backoff_delays(attempts: int, base: float = 1.0, cap: float = 60.0) -> list[float]`
  - `@dataclass class FrameOutcome: popups: list[PendingPopup]; reload_needed: bool`
  - `class Watcher` mit `load_snapshot() -> bool`, `handle_frame(frame) -> FrameOutcome`

**Drei Dinge, die hier richtig sein müssen:**

1. **`unread_only=True`.** Die Route liefert sonst *alle* Meldungen nach
   `created_at DESC`, und `page_size` ist bei 100 gedeckelt
   (`notifications.py:46`, `le=100`). Bei mehr als 100 Meldungen fielen ältere
   ungelesene aus der Seite — Icon grün, Server sagt ungelesen. Der Parameter
   existiert (`notifications.py:36`).
2. **Nicht-200 ist ein Fehlschlag, kein Erfolg.** Ein stilles `return` würde
   dazu führen, dass die Schleife danach `connected=True` setzt und den alten
   Zustand als aktuell ausgibt. `GET /api/notifications` ist mit
   `admin_operations` limitiert; bei einem Reconnect-Sturm käme 429, und das
   Tray behauptete „verbunden, alles gut".
3. **Sammelaktionen lösen einen Neuabgleich aus**, statt den Zustand zu leeren.
   `read_all` kann einen Kategoriefilter getragen haben — „alles gelesen"
   anzunehmen würde bei gesetzter Kategorie ein rotes Icon fälschlich auf grün
   schalten.

**Kein eigener Frame-Puffer.** Die Reihenfolge — erst Snapshot, dann Frames —
stellt `run_cycle` (Task 17) her, indem es den Socket **vor** dem Snapshot
öffnet: Die `websockets`-Bibliothek hält eingehende Frames, bis gelesen wird.
Ein zusätzlicher Puffer in dieser Klasse hätte keinen Aufrufer und wäre genau
die tote Verdrahtung, die dieser Plan dem Backend vorwirft.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_watch.py`:

```python
"""Tests for the tray's websocket watcher — ordering, snapshot, backoff."""

from unittest.mock import MagicMock

import pytest

from baluhost_tray.state import IconState, TrayState
from baluhost_tray.watch import Watcher, backoff_delays


def test_backoff_grows_and_caps():
    delays = backoff_delays(8, base=1.0, cap=60.0)
    assert all(b >= a for a, b in zip(delays, delays[1:]))
    assert max(delays) <= 60.0


def test_backoff_has_jitter():
    """Ohne Jitter kommen nach einem Backend-Neustart alle Clients gleichzeitig."""
    assert backoff_delays(8) != backoff_delays(8)


def _watcher(unread: list[dict], status: int = 200):
    session = MagicMock()
    response = MagicMock()
    response.status_code = status
    response.json.return_value = {
        "notifications": unread,
        "unread_count": len(unread),
        "total": len(unread),
    }
    session.client.return_value.get.return_value = response
    state = TrayState()
    state.set_connected(True)
    return Watcher(session, state), state, session


def test_snapshot_asks_for_unread_only():
    watcher, _, session = _watcher([])
    watcher.load_snapshot()
    params = session.client.return_value.get.call_args[1]["params"]
    assert params["unread_only"] is True
    assert params["page_size"] == 100


def test_snapshot_fills_state():
    watcher, state, _ = _watcher([
        {"id": 1, "notification_type": "critical", "is_read": False,
         "title": "RAID", "message": "degradiert"},
    ])
    assert watcher.load_snapshot() is True
    assert state.icon_state() == IconState.CRITICAL


def test_snapshot_failure_is_reported_not_swallowed():
    """429 darf nicht als 'verbunden, alles gut' durchgehen."""
    watcher, _, _ = _watcher([], status=429)
    assert watcher.load_snapshot() is False


def test_frame_after_snapshot_wins():
    """Ein 'gelesen', das nach dem Snapshot verarbeitet wird, gilt — die
    Reihenfolge selbst stellt run_cycle her (Task 17)."""
    watcher, state, _ = _watcher([
        {"id": 1, "notification_type": "critical", "is_read": False,
         "title": "RAID", "message": "degradiert"},
    ])
    watcher.load_snapshot()
    watcher.handle_frame({
        "type": "notification_state",
        "payload": {"ids": [1], "action": "read"},
    })
    assert state.icon_state() == IconState.OK


def test_new_critical_frame_yields_popup():
    watcher, state, _ = _watcher([])
    outcome = watcher.handle_frame({
        "type": "notification",
        "payload": {"id": 5, "notification_type": "critical",
                    "title": "SMART", "message": "Platte meldet Fehler"},
    })
    assert [p.notification_id for p in outcome.popups] == [5]
    assert state.icon_state() == IconState.CRITICAL


def test_warning_frame_colours_without_popup():
    watcher, state, _ = _watcher([])
    outcome = watcher.handle_frame({
        "type": "notification",
        "payload": {"id": 6, "notification_type": "warning",
                    "title": "Backup", "message": "uebersprungen"},
    })
    assert outcome.popups == []
    assert state.icon_state() == IconState.WARNING


def test_single_state_action_removes_the_ids():
    watcher, state, _ = _watcher([
        {"id": 1, "notification_type": "critical", "is_read": False,
         "title": "x", "message": "y"},
    ])
    watcher.load_snapshot()
    watcher.handle_frame({
        "type": "notification_state",
        "payload": {"ids": [1], "action": "dismissed"},
    })
    assert state.icon_state() == IconState.OK


def test_bulk_action_asks_for_reload_instead_of_clearing():
    """read_all kann einen Kategoriefilter getragen haben — leeren waere
    geraten, nachladen ist gewusst."""
    watcher, state, _ = _watcher([
        {"id": 1, "notification_type": "critical", "is_read": False,
         "title": "x", "message": "y"},
    ])
    watcher.load_snapshot()
    outcome = watcher.handle_frame({
        "type": "notification_state",
        "payload": {"ids": [], "action": "read_all"},
    })
    assert outcome.reload_needed is True
    assert state.icon_state() == IconState.CRITICAL  # unveraendert bis zum Neuabgleich


def test_unknown_frame_type_ignored():
    watcher, _, _ = _watcher([])
    outcome = watcher.handle_frame({"type": "pong", "payload": {}})
    assert outcome.popups == [] and outcome.reload_needed is False
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_watch.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray.watch'`

- [ ] **Step 3: Minimal implementieren**

`backend/baluhost_tray/watch.py`:

```python
"""Websocket watcher: keeps TrayState in step with the backend.

Ordering matters more than anything else here, but it is established by the
caller: run_cycle opens the socket before loading the snapshot, so the
websockets library holds incoming frames until they are read. The other way
round a snapshot would undo a "read" the socket already reported, and the
icon would jump back to red.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field

from baluhost_tray.state import PendingPopup, TrayState

logger = logging.getLogger(__name__)

POPUP_TYPES = frozenset({"critical"})
COLOURING_TYPES = frozenset({"critical", "warning"})
BULK_ACTIONS = frozenset({"read_all", "dismissed_all", "deleted_all"})
SNAPSHOT_PATH = "/api/notifications"
SNAPSHOT_PAGE_SIZE = 100


def backoff_delays(attempts: int, base: float = 1.0, cap: float = 60.0) -> list[float]:
    """Exponential backoff with jitter, capped.

    The jitter is not decoration: without it every client that dropped when
    the backend restarted comes back at the same instant.
    """
    return [
        round(min(cap, base * (2 ** attempt)) * random.uniform(0.5, 1.0), 3)
        for attempt in range(attempts)
    ]


@dataclass
class FrameOutcome:
    popups: list[PendingPopup] = field(default_factory=list)
    reload_needed: bool = False


class Watcher:
    def __init__(self, session, state: TrayState) -> None:
        self._session = session
        self._state = state

    def load_snapshot(self) -> bool:
        """Replace state from REST. Returns False if the snapshot failed.

        unread_only matters: without it the route returns everything newest
        first, capped at 100 rows, and an older unread notification would
        fall off the page — green icon, unread server.
        """
        try:
            response = self._session.client().get(
                SNAPSHOT_PATH,
                params={"unread_only": True, "page_size": SNAPSHOT_PAGE_SIZE},
            )
        except Exception as exc:
            logger.warning("snapshot request failed: %s", exc)
            return False

        if response.status_code != 200:
            # Never treat this as success: the loop would go on to claim
            # "connected" while showing stale state.
            logger.warning("snapshot refused: %s", response.status_code)
            return False

        body = response.json()
        items = [
            (int(raw["id"]), str(raw.get("notification_type", "")))
            for raw in body.get("notifications", [])
            if not raw.get("is_read")
        ]
        self._state.apply_snapshot(items)

        reported = body.get("unread_count")
        if isinstance(reported, int) and reported != len(items):
            # More unread than one page holds, or a filter surprise. The
            # count is the server's own answer, so trust it over our page.
            logger.info(
                "snapshot page holds %d of %d unread notifications",
                len(items), reported,
            )
        return True

    def handle_frame(self, frame: dict) -> FrameOutcome:
        """Apply one frame."""
        kind = frame.get("type")
        payload = frame.get("payload") or {}

        if kind == "notification":
            ntype = str(payload.get("notification_type", ""))
            nid = int(payload.get("id", 0))
            if ntype in COLOURING_TYPES:
                self._state.add(nid, ntype)
            if ntype in POPUP_TYPES:
                return FrameOutcome(popups=[PendingPopup(
                    notification_id=nid,
                    title=str(payload.get("title", "BaluHost")),
                    message=str(payload.get("message", "")),
                )])
            return FrameOutcome()

        if kind == "notification_state":
            action = payload.get("action")
            if action in BULK_ACTIONS:
                # The bulk actions carry no ids because mark_all_as_read may
                # have been scoped to a category. Clearing would be a guess.
                return FrameOutcome(reload_needed=True)
            self._state.remove([int(i) for i in payload.get("ids", [])])
            return FrameOutcome()

        return FrameOutcome()
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_watch.py -v`
Expected: PASS (11 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray/watch.py backend/tests/tray/test_watch.py
git commit -m "feat(tray): WebSocket-Beobachter mit Snapshot, Puffer und Backoff

Der Snapshot fragt unread_only an -- sonst liefert die Route alles
neueste zuerst, bei 100 gedeckelt, und eine aeltere ungelesene Meldung
faellt aus der Seite. Ein Nicht-200 wird als Fehlschlag gemeldet und
nicht stillschweigend als Erfolg gewertet.

Sammelaktionen loesen einen Neuabgleich aus statt den Zustand zu leeren:
read_all kann einen Kategoriefilter getragen haben.

Der Jitter im Backoff ist keine Zierde -- ohne ihn kommen nach einem
Backend-Neustart alle Clients im selben Moment zurueck.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 14: Desktop-Meldungen über D-Bus

**Files:**
- Create: `backend/baluhost_tray/notify.py`
- Test: `backend/tests/tray/test_notify.py`

**Interfaces:**
- Consumes: `dbus-next` (Kernabhängigkeit, `pyproject.toml:46`), `PendingPopup`.
- Produces: `class Notifier` mit `async connect()`, `async show(popup) -> int`,
  `async show_summary(title, message) -> int`; `class NotifierUnavailable(Exception)`

**Warum der Standardweg und kein Toolkit-Aufruf:** Über
`org.freedesktop.Notifications` greifen Plasmas eigenes „Nicht stören" und die
Vollbild-Regeln automatisch. Das Tray muss dafür nichts erkennen.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_notify.py`:

```python
"""Tests for desktop notifications — against a stub bus, never a real one."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from baluhost_tray.notify import Notifier, NotifierUnavailable
from baluhost_tray.state import PendingPopup


def _stub_interface() -> MagicMock:
    iface = MagicMock()
    iface.call_notify = AsyncMock(return_value=42)
    return iface


@pytest.mark.asyncio
async def test_show_passes_title_and_message():
    notifier = Notifier()
    notifier._iface = _stub_interface()

    result = await notifier.show(
        PendingPopup(notification_id=1, title="RAID", message="degradiert")
    )

    assert result == 42
    args = notifier._iface.call_notify.await_args[0]
    assert "RAID" in args and "degradiert" in args


@pytest.mark.asyncio
async def test_show_without_connection_raises():
    with pytest.raises(NotifierUnavailable):
        await Notifier().show(PendingPopup(notification_id=1, title="x", message="y"))


@pytest.mark.asyncio
async def test_summary_is_one_message():
    notifier = Notifier()
    notifier._iface = _stub_interface()
    await notifier.show_summary("BaluHost", "4 neue kritische Meldungen")
    assert notifier._iface.call_notify.await_count == 1


@pytest.mark.asyncio
async def test_connect_without_a_bus_raises_the_typed_error():
    """Start ausserhalb von Plasma darf keinen rohen dbus-Fehler durchreichen."""
    notifier = Notifier()
    with pytest.raises(NotifierUnavailable):
        await notifier.connect(_bus_factory=lambda: (_ for _ in ()).throw(OSError("no bus")))
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_notify.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray.notify'`

- [ ] **Step 3: Minimal implementieren**

`backend/baluhost_tray/notify.py`:

```python
"""Desktop notifications via org.freedesktop.Notifications.

Going through the standard interface rather than a toolkit call is what makes
Plasma's own Do-Not-Disturb and fullscreen rules apply for free — the tray
does not have to detect anything itself.
"""

from __future__ import annotations

from baluhost_tray.state import PendingPopup

_BUS_NAME = "org.freedesktop.Notifications"
_BUS_PATH = "/org/freedesktop/Notifications"
_APP_NAME = "BaluHost"
_TIMEOUT_MS = 10_000


class NotifierUnavailable(Exception):
    """No session bus or no notification server — e.g. started outside Plasma."""


class Notifier:
    def __init__(self) -> None:
        self._iface = None

    async def connect(self, _bus_factory=None) -> None:
        """Attach to the session bus.

        _bus_factory exists for the tests: it lets them drive the failure
        path without a bus and without patching module internals.
        """
        try:
            if _bus_factory is not None:
                bus = _bus_factory()
            else:
                from dbus_next import BusType
                from dbus_next.aio import MessageBus

                bus = await MessageBus(bus_type=BusType.SESSION).connect()

            introspection = await bus.introspect(_BUS_NAME, _BUS_PATH)
            obj = bus.get_proxy_object(_BUS_NAME, _BUS_PATH, introspection)
            self._iface = obj.get_interface(_BUS_NAME)
        except Exception as exc:
            raise NotifierUnavailable(str(exc)) from exc

    async def show(self, popup: PendingPopup) -> int:
        """Show one notification, return the server's id."""
        return await self._notify(popup.title, popup.message)

    async def show_summary(self, title: str, message: str) -> int:
        """Show the collapsed form used after a gaming session or quiet hour."""
        return await self._notify(title, message)

    async def _notify(self, title: str, message: str) -> int:
        if self._iface is None:
            raise NotifierUnavailable("not connected to a session bus")
        return await self._iface.call_notify(
            _APP_NAME,
            0,               # replaces_id: 0 = new notification
            "baluhost",      # icon name
            title,
            message,
            [],              # actions
            {},              # hints
            _TIMEOUT_MS,
        )
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_notify.py -v`
Expected: PASS (4 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray/notify.py backend/tests/tray/test_notify.py
git commit -m "feat(tray): Desktop-Meldungen ueber org.freedesktop.Notifications

Der Standardweg statt eines Toolkit-Aufrufs sorgt dafuer, dass Plasmas
eigenes 'Nicht stoeren' und die Vollbild-Regeln automatisch greifen --
das Tray muss selbst nichts erkennen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 15: Icon-Material

**Files:**
- Create: `backend/baluhost_tray/icons/__init__.py`
- Create: `backend/baluhost_tray/icons/baluhost-tray-{ok,warning,critical,offline}-{22,24,32,48}.png`
- Create: `backend/baluhost_tray/icons/README.md`
- Test: `backend/tests/tray/test_icons.py`

**Interfaces:**
- Consumes: `client/src-tauri/icons/icon.png` (1024×1024 RGBA) als Quelle.
- Produces: `def icon_path(state: IconState, size: int = 22) -> Path`,
  `SIZES: tuple[int, ...]`

**Handarbeit, kein Konvertierungsschritt.** `client/public/baluhost-logo.svg`
ist mit 1,2 MB kein Vektor-Logo, sondern ein nachgezeichnetes Bitmap; die PNGs
tragen ein dunkles Hintergrundquadrat, das im Panel als Kasten erschiene. Zu
tun: Quadrat entfernen, Katze freistellen, in vier Größen rendern, für
`warning`/`critical` einen Punkt unten rechts einsetzen, für `offline`
entsättigen.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_icons.py`:

```python
"""The icon set must be complete — a missing file means an invisible tray."""

from pathlib import Path

import pytest

from baluhost_tray.icons import SIZES, icon_path
from baluhost_tray.state import IconState


@pytest.mark.parametrize("state", list(IconState))
@pytest.mark.parametrize("size", SIZES)
def test_icon_exists_for_every_state_and_size(state: IconState, size: int):
    path = icon_path(state, size)
    assert path.exists(), f"fehlt: {path}"
    assert path.stat().st_size > 0


def test_unknown_size_falls_back_to_the_smallest():
    assert icon_path(IconState.OK, 17) == icon_path(IconState.OK, 22)


def test_icons_ship_inside_the_package():
    """Sie muessen neben dem Modul liegen, nicht irgendwo im Repo — sonst
    fehlen sie im installierten Paket."""
    from baluhost_tray import icons as icons_pkg

    package_dir = Path(icons_pkg.__file__).parent
    assert icon_path(IconState.OK, 22).parent == package_dir
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_icons.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray.icons'`

- [ ] **Step 3: Icons erzeugen**

ImageMagick liegt auf der Box; andernfalls von Hand in einem Bildeditor.

```bash
cd backend/baluhost_tray/icons
magick ../../../client/src-tauri/icons/icon.png \
  -fuzz 12% -fill none -draw "alpha 0,0 floodfill" base-1024.png

for s in 22 24 32 48; do
  magick base-1024.png -resize ${s}x${s} baluhost-tray-ok-${s}.png
  magick baluhost-tray-ok-${s}.png -colorspace Gray -alpha on \
    baluhost-tray-offline-${s}.png
  d=$(( s / 3 ))
  magick baluhost-tray-ok-${s}.png -fill '#F5A623' -stroke none \
    -draw "circle $((s-d/2-1)),$((s-d/2-1)) $((s-d/2-1)),$((s-1))" \
    baluhost-tray-warning-${s}.png
  magick baluhost-tray-ok-${s}.png -fill '#D0021B' -stroke none \
    -draw "circle $((s-d/2-1)),$((s-d/2-1)) $((s-d/2-1)),$((s-1))" \
    baluhost-tray-critical-${s}.png
done
rm base-1024.png
```

**Jede Datei bei 22 px im Panel ansehen, bevor es weitergeht.** Ist die Katze
dort nur ein Fleck, muss die Silhouette von Hand vereinfacht werden — das ist
der wahrscheinliche Fall und kein Grund, den Schritt zu überspringen.

`backend/baluhost_tray/icons/README.md`:

```markdown
# Tray-Icons

Abgeleitet aus `client/src-tauri/icons/icon.png` (1024²). Das dunkle
Hintergrundquadrat ist entfernt, sonst säße die Katze im Panel in einem Kasten.

`client/public/baluhost-logo.svg` ist **nicht** die Quelle: 1,2 MB, ein
nachgezeichnetes Bitmap mit tausenden Pfadpunkten.

Zustände: `ok` (Katze pur) · `warning` (gelber Punkt unten rechts) ·
`critical` (roter Punkt) · `offline` (entsättigt). Der Zustand steckt im
Badge, nicht in der Färbung der Katze — eine rote Katze liest sich als
anderes Logo, nicht als Alarm.

Weil die Katze farbig bleibt, funktioniert sie auf hellen wie dunklen Panels;
es gibt bewusst keine Hell/Dunkel-Varianten.

Alle vier Größen werden gebraucht: `tray.py` legt sie per `QIcon.addFile()` in
*ein* Icon, damit Plasma auf HiDPI-Panels die passende wählt.
```

- [ ] **Step 4: Nachschlagefunktion implementieren**

`backend/baluhost_tray/icons/__init__.py`:

```python
"""Icon lookup for the tray."""

from __future__ import annotations

from pathlib import Path

from baluhost_tray.state import IconState

_DIR = Path(__file__).parent
SIZES = (22, 24, 32, 48)
_DEFAULT_SIZE = 22


def icon_path(state: IconState, size: int = _DEFAULT_SIZE) -> Path:
    """Path to the icon file for this state, falling back to 22 px."""
    if size not in SIZES:
        size = _DEFAULT_SIZE
    return _DIR / f"baluhost-tray-{state.value}-{size}.png"
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_icons.py -v`
Expected: PASS (18 Tests)

- [ ] **Step 6: Committen**

```bash
git add backend/baluhost_tray/icons backend/tests/tray/test_icons.py
git commit -m "feat(tray): Icon-Material in vier Zustaenden und vier Groessen

Aus dem 1024er-PNG abgeleitet und freigestellt; das 1,2-MB-SVG ist ein
nachgezeichnetes Bitmap und als Quelle unbrauchbar. Der Zustand steckt
im Badge unten rechts, nicht in der Faerbung der Katze -- eine rote
Katze liest sich als anderes Logo, nicht als Alarm.

Alle vier Groessen werden spaeter in ein QIcon gelegt, damit HiDPI-Panels
nicht die 22er hochskalieren muessen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 16: Einzelinstanz-Sperre

**Files:**
- Create: `backend/baluhost_tray/single_instance.py`
- Test: `backend/tests/tray/test_single_instance.py`

**Interfaces:**
- Consumes: nichts.
- Produces: `class AlreadyRunning(Exception)`,
  `def acquire(name: str = "baluhost-tray") -> object`

**`$XDG_RUNTIME_DIR`, nicht `/tmp`:** sitzungsgebunden und beim Abmelden weg.
Die Lock-Datei wird **nicht** vor dem Öffnen gelöscht — genau das erzeugt das
Rennen, in dem zwei Prozesse je eine eigene Inode sperren und beide sich für
den einzigen halten.

**Der Name ist ein Parameter, weil `--pair` ihn braucht.** Läuft die
systemd-Unit, darf ein `baluhost-tray --pair` nicht mit „läuft bereits"
abbrechen — sonst ist Neukoppeln nur nach Stoppen des Dienstes möglich.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_single_instance.py`:

```python
"""One tray per session — but pairing must stay possible alongside it."""

import pytest

from baluhost_tray import single_instance


@pytest.fixture(autouse=True)
def runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return tmp_path


def test_first_acquire_succeeds():
    assert single_instance.acquire("test-tray") is not None


def test_second_acquire_refused():
    single_instance.acquire("test-tray-2")
    with pytest.raises(single_instance.AlreadyRunning):
        single_instance.acquire("test-tray-2")


def test_different_names_do_not_collide():
    """--pair laeuft neben dem Dienst, also braucht es einen eigenen Namen."""
    single_instance.acquire("test-tray-3")
    assert single_instance.acquire("test-tray-3-pair") is not None


def test_lock_file_lands_in_runtime_dir(runtime_dir):
    single_instance.acquire("test-tray-4")
    assert (runtime_dir / "test-tray-4.lock").exists()


def test_missing_runtime_dir_falls_back(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert single_instance.acquire("test-tray-fallback") is not None
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_single_instance.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray.single_instance'`

- [ ] **Step 3: Minimal implementieren**

`backend/baluhost_tray/single_instance.py`:

```python
"""One tray per desktop session.

The lock lives in $XDG_RUNTIME_DIR: session scoped and gone at logout. It is
never unlinked before opening — that is exactly the race where two processes
each lock their own inode and both believe they are the only one.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path


class AlreadyRunning(Exception):
    """Another process already holds this lock in this session."""


_handles: list = []


def _lock_dir() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime)
    return Path.home() / ".baluhost"


def acquire(name: str = "baluhost-tray") -> object:
    """Take the session lock. Keep the returned handle alive for the process.

    The name is a parameter so pairing can use its own: `--pair` has to work
    while the service is running, otherwise re-pairing would require stopping
    the unit first.
    """
    directory = _lock_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.lock"

    handle = open(path, "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise AlreadyRunning(f"another process holds {path}") from exc

    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    _handles.append(handle)  # keep the fd open for the process lifetime
    return handle
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_single_instance.py -v`
Expected: PASS (5 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray/single_instance.py backend/tests/tray/test_single_instance.py
git commit -m "feat(tray): Einzelinstanz-Sperre in XDG_RUNTIME_DIR

Sitzungsgebunden statt /tmp. Die Datei wird vor dem Oeffnen nicht
geloescht: genau das erzeugt das Rennen, in dem zwei Prozesse je eine
eigene Inode sperren und beide sich fuer den einzigen halten.

Der Lock-Name ist ein Parameter, damit --pair neben dem laufenden Dienst
funktioniert.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 17: Die Schleife — Zustellung, Gaming-Gate, Takt, Wiederanlauf

**Files:**
- Create: `backend/baluhost_tray/loop.py`
- Test: `backend/tests/tray/test_loop.py`

**Interfaces:**
- Consumes: `Session`, `Watcher`, `TrayState`, `PopupQueue`, `Notifier`.
- Produces:
  - `def is_gaming_active(client) -> bool`
  - `async def deliver(popups, queue, notifier, hold: bool) -> None`
  - `async def run_cycle(ctx: LoopContext) -> None`
  - `async def run_loop(ctx: LoopContext) -> None`
  - `@dataclass class LoopContext` mit allen Mitspielern und den einspeisbaren
    Zeit-/Socket-Funktionen

**Diese Datei ist der Grund, warum `tray.py` dünn bleibt.** Reconnect,
Backoff, Snapshot-Reihenfolge, der Takt des Gaming-Gates und die Entscheidung,
wann eine Kopplung als verloren gilt — alles hier, alles ohne Qt prüfbar.
`tray.py` liefert nur eine `sink`-Funktion, die eine Icon-Farbe entgegennimmt.

**Der Takt ist nicht optional.** Ein Gate, das nur bei eingehenden Frames
gefragt wird, hält eine Meldung für immer zurück: Kommt um 21:30 eine kritische
Meldung während des Spielens und danach kein Frame mehr, wird nie wieder
gefragt, ob das Spiel vorbei ist. Deshalb wartet die Schleife mit
`asyncio.wait_for(..., timeout=30)` auf Frames und arbeitet bei jedem Timeout
die Warteschlange ab. Dasselbe gilt für „eine Stunde stumm".

**Alle 10 Minuten ein Neuabgleich.** Fängt abgelaufene Snoozes (für die es
serverseitig keinen Job gibt), verpasste Frames und Zählerdrift.

**Blockierendes gehört in einen Thread.** `load_snapshot()`, `ws_token()` und
`is_gaming_active()` benutzen den synchronen `httpx.Client` aus `BackendClient`.
Direkt aus `async def` gerufen blockieren sie den Socket-Read und damit die
Zustellung.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_loop.py`:

```python
"""Delivery, the gaming gate and its cadence."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from baluhost_tray.loop import deliver, is_gaming_active
from baluhost_tray.state import PendingPopup, PopupQueue


def _popup(n: int) -> PendingPopup:
    return PendingPopup(notification_id=n, title=f"T{n}", message=f"M{n}")


def _notifier() -> MagicMock:
    notifier = MagicMock()
    notifier.show = AsyncMock()
    notifier.show_summary = AsyncMock()
    return notifier


@pytest.mark.asyncio
async def test_delivers_when_not_holding():
    notifier, queue = _notifier(), PopupQueue()
    await deliver([_popup(1)], queue, notifier, hold=False)
    notifier.show.assert_awaited_once()
    assert queue.is_empty()


@pytest.mark.asyncio
async def test_holds_while_holding():
    notifier, queue = _notifier(), PopupQueue()
    await deliver([_popup(1)], queue, notifier, hold=True)
    notifier.show.assert_not_awaited()
    assert not queue.is_empty()


@pytest.mark.asyncio
async def test_release_collapses_above_threshold():
    notifier, queue = _notifier(), PopupQueue()
    await deliver([_popup(n) for n in (1, 2, 3, 4)], queue, notifier, hold=True)
    await deliver([], queue, notifier, hold=False)
    notifier.show_summary.assert_awaited_once()
    notifier.show.assert_not_awaited()


@pytest.mark.asyncio
async def test_release_shows_each_below_threshold():
    notifier, queue = _notifier(), PopupQueue()
    await deliver([_popup(1), _popup(2)], queue, notifier, hold=True)
    await deliver([], queue, notifier, hold=False)
    assert notifier.show.await_count == 2
    notifier.show_summary.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_delivery_keeps_the_popups():
    """Ein D-Bus-Fehler darf die Warteschlange nicht leeren."""
    notifier, queue = _notifier(), PopupQueue()
    notifier.show.side_effect = RuntimeError("bus gone")
    await deliver([_popup(1)], queue, notifier, hold=False)
    assert not queue.is_empty()


def test_gaming_probe_404_counts_as_not_gaming():
    """Plugin abgeschaltet -> Route fehlt -> Popup wird gezeigt."""
    client = MagicMock()
    response = MagicMock()
    response.status_code = 404
    client.get.return_value = response
    assert is_gaming_active(client) is False


def test_gaming_probe_error_counts_as_not_gaming():
    client = MagicMock()
    client.get.side_effect = OSError("network down")
    assert is_gaming_active(client) is False


def test_gaming_probe_true():
    client = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"gaming_active": True}
    client.get.return_value = response
    assert is_gaming_active(client) is True
```

Und in derselben Datei die Schleife selbst, gegen einen eingespeisten Socket:

```python
import asyncio
import json

from baluhost_tray.loop import LoopContext, run_cycle
from baluhost_tray.state import IconState, TrayState
from baluhost_tray.watch import Watcher


class FakeSocket:
    """Liefert vorgegebene Frames, danach Timeouts — wie eine stille Leitung."""

    def __init__(self, frames: list[dict], then_idle: int = 0) -> None:
        self._frames = [json.dumps(f) for f in frames]
        self._idle_left = then_idle

    async def recv(self) -> str:
        if self._frames:
            return self._frames.pop(0)
        if self._idle_left > 0:
            self._idle_left -= 1
            raise asyncio.TimeoutError
        raise ConnectionError("closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _ctx(frames, snapshot=None, gaming=False, then_idle=0) -> LoopContext:
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "notifications": snapshot or [],
        "unread_count": len(snapshot or []),
    }
    session.client.return_value.get.return_value = response
    session.ws_token.return_value = "wt"
    session.ws_url.return_value = "ws://x/api/notifications/ws"

    state = TrayState()
    seen: list[IconState] = []

    return LoopContext(
        session=session,
        watcher=Watcher(session, state),
        state=state,
        queue=PopupQueue(),
        notifier=_notifier(),
        sink=seen.append,
        hold_probe=lambda: gaming,
        connect=lambda url: FakeSocket(frames, then_idle=then_idle),
        sleep=AsyncMock(),
        seen=seen,
    )


@pytest.mark.asyncio
async def test_cycle_loads_snapshot_before_reading_frames():
    ctx = _ctx(
        frames=[{"type": "notification_state",
                 "payload": {"ids": [1], "action": "read"}}],
        snapshot=[{"id": 1, "notification_type": "critical", "is_read": False,
                   "title": "RAID", "message": "degradiert"}],
    )
    with pytest.raises(ConnectionError):
        await run_cycle(ctx)
    assert ctx.state.icon_state() == IconState.OK


@pytest.mark.asyncio
async def test_idle_tick_drains_the_queue_without_any_frame():
    """Der Fall, der ohne Takt ewig haengt: nichts kommt mehr rein, das Spiel
    ist vorbei, die zurueckgehaltene Meldung muss trotzdem raus."""
    ctx = _ctx(
        frames=[{"type": "notification",
                 "payload": {"id": 9, "notification_type": "critical",
                             "title": "SMART", "message": "Fehler"}}],
        then_idle=2,
        gaming=True,
    )
    holds = {"value": True}
    ctx.hold_probe = lambda: holds["value"]

    async def _flip(*_args, **_kwargs):
        holds["value"] = False

    ctx.sleep = _flip
    with pytest.raises(ConnectionError):
        await run_cycle(ctx)

    ctx.notifier.show.assert_awaited()
```

**Vor dem Schreiben:** Die Testhilfen oben setzen voraus, dass `LoopContext`
ein änderbares Dataclass ist und `connect(url)` einen Kontextmanager mit
`recv()` liefert. Beim Implementieren beides so halten, sonst die Tests
mitziehen.

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_loop.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray.loop'`

- [ ] **Step 3: Minimal implementieren**

`backend/baluhost_tray/loop.py`:

```python
"""Delivery, the gaming gate, and the reconnect loop.

Everything decidable lives here rather than in tray.py: reconnect, backoff,
snapshot ordering, the cadence of the gaming probe and when a pairing counts
as lost. tray.py only supplies a sink that takes an icon state.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from baluhost_tray.session import AuthExpired, PairingLost, TemporaryFailure
from baluhost_tray.state import IconState, PendingPopup, PopupQueue, TrayState
from baluhost_tray.watch import Watcher, backoff_delays

logger = logging.getLogger(__name__)

GAMING_PATH = "/api/plugins/steam_gaming/session-state"
TICK_SECONDS = 30.0
RESNAPSHOT_SECONDS = 600.0


def is_gaming_active(client) -> bool:
    """Ask the plugin whether a session is on screen.

    Anything other than a clear yes counts as "not gaming": the plugin can be
    disabled, in which case the route is simply absent. Rather one
    notification too many than a swallowed alarm.
    """
    try:
        response = client.get(GAMING_PATH)
        if response.status_code != 200:
            return False
        return bool(response.json().get("gaming_active", False))
    except Exception as exc:
        logger.debug("gaming probe failed, treating as not gaming: %s", exc)
        return False


async def deliver(
    popups: list[PendingPopup],
    queue: PopupQueue,
    notifier,
    hold: bool,
) -> None:
    """Show popups, or hold them back.

    `hold` has two possible reasons — a game on screen or quiet mode — and
    deliver does not care which: held is held, and held is never dropped.

    A failed delivery puts everything back. Losing an alarm because the bus
    hiccuped is worse than showing it a minute late.
    """
    if hold:
        for popup in popups:
            queue.hold(popup)
        return

    pending = list(popups)
    if not queue.is_empty():
        summary = queue.summary()
        released = queue.release()
        if summary:
            try:
                await notifier.show_summary(*summary)
            except Exception as exc:
                logger.warning("summary delivery failed: %s", exc)
                for popup in released:
                    queue.hold(popup)
                return
        else:
            pending = released + pending

    for popup in pending:
        try:
            await notifier.show(popup)
        except Exception as exc:
            logger.warning("delivery failed, keeping the popup: %s", exc)
            queue.hold(popup)


@dataclass
class LoopContext:
    session: Any
    watcher: Watcher
    state: TrayState
    queue: PopupQueue
    notifier: Any
    sink: Callable[[IconState], None]
    hold_probe: Callable[[], bool]
    connect: Callable[[str], Any]
    sleep: Callable[..., Any] = asyncio.sleep
    now: Callable[[], float] = time.monotonic
    seen: list = field(default_factory=list)


def _publish(ctx: LoopContext) -> None:
    ctx.sink(ctx.state.icon_state())


async def run_cycle(ctx: LoopContext) -> None:
    """One connect-consume cycle. Returning or raising means: reconnect.

    Order: open the socket first, then load the snapshot, then read frames.
    The websockets library holds whatever arrived meanwhile, so those frames
    land on top of the snapshot. The other way round the snapshot undoes a
    "read" the socket already reported, and the icon jumps back to red.
    """
    token = await asyncio.to_thread(ctx.session.ws_token)
    url = f"{ctx.session.ws_url()}?token={token}"

    async with ctx.connect(url) as socket:
        ok = await asyncio.to_thread(ctx.watcher.load_snapshot)
        if not ok:
            raise TemporaryFailure("snapshot refused")

        ctx.state.set_connected(True)
        _publish(ctx)

        last_snapshot = ctx.now()

        while True:
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=TICK_SECONDS)
            except asyncio.TimeoutError:
                raw = None

            reload_needed = False
            popups: list[PendingPopup] = []

            if raw is not None:
                try:
                    frame = json.loads(raw)
                except ValueError:
                    continue
                result = ctx.watcher.handle_frame(frame)
                popups, reload_needed = result.popups, result.reload_needed

            due = ctx.now() - last_snapshot >= RESNAPSHOT_SECONDS
            if reload_needed or due:
                # Catches expired snoozes (the server has no job for them),
                # missed frames and counter drift.
                if await asyncio.to_thread(ctx.watcher.load_snapshot):
                    last_snapshot = ctx.now()

            if popups or not ctx.queue.is_empty():
                hold = await asyncio.to_thread(ctx.hold_probe)
                await deliver(popups, ctx.queue, ctx.notifier, hold)

            _publish(ctx)


async def run_loop(ctx: LoopContext) -> None:
    """Reconnect forever, with the failure classes kept apart.

    A 401 is worth one refresh and another try. A rate limit or a server
    error is worth a backoff. Only a lost pairing stops the loop — and even
    then it stops by going grey, not by killing the thread silently.
    """
    attempt = 0
    while True:
        try:
            await run_cycle(ctx)
            attempt = 0
        except AuthExpired:
            try:
                await asyncio.to_thread(ctx.session.refresh_access)
                continue
            except PairingLost:
                logger.warning("pairing lost — tray goes idle until re-paired")
                ctx.state.set_connected(False)
                _publish(ctx)
                return
            except TemporaryFailure as exc:
                logger.info("refresh temporarily unavailable: %s", exc)
        except PairingLost:
            logger.warning("pairing lost — tray goes idle until re-paired")
            ctx.state.set_connected(False)
            _publish(ctx)
            return
        except Exception as exc:
            logger.info("connection lost: %s", exc)

        ctx.state.set_connected(False)
        _publish(ctx)
        delay = backoff_delays(attempt + 1)[-1]
        await ctx.sleep(delay)
        attempt = min(attempt + 1, 7)
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_loop.py -v`
Expected: PASS (10 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray/loop.py backend/tests/tray/test_loop.py
git commit -m "feat(tray): Schleife mit Takt, Gaming-Gate und getrennten Fehlerklassen

Die Schleife wartet mit Timeout auf Frames und arbeitet bei jedem
Timeout die Warteschlange ab. Ohne diesen Takt bliebe eine waehrend des
Spielens zurueckgehaltene Meldung fuer immer liegen, wenn danach kein
Frame mehr kommt -- niemand wuerde je wieder fragen, ob das Spiel vorbei
ist.

Alle 10 Minuten ein Neuabgleich: faengt abgelaufene Snoozes, fuer die es
serverseitig keinen Job gibt, dazu verpasste Frames und Zaehlerdrift.

Reihenfolge: Socket auf, Frames puffern, Snapshot, Puffer anwenden.
Andersherum macht der Snapshot ein bereits gemeldetes 'gelesen' wieder
rueckgaengig.

401 kostet einen Refresh und einen neuen Versuch, Ratelimit und
Serverfehler kosten einen Backoff. Nur eine verlorene Kopplung beendet
die Schleife -- und auch dann sichtbar in grau, nicht als stiller Tod
des Threads.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 18: Verbindungsmeldungen und Stummschaltung

**Files:**
- Create: `backend/baluhost_tray/announce.py`
- Modify: `backend/baluhost_tray/loop.py` (`LoopContext`, `run_cycle`, `run_loop`)
- Test: `backend/tests/tray/test_announce.py`

**Interfaces:**
- Consumes: `Notifier`.
- Produces:
  - `class ConnectionAnnouncer` mit `went_offline(now) -> tuple[str,str] | None`,
    `came_online(now) -> tuple[str,str] | None`
  - `class QuietMode` mit `mute_for(seconds, now)`, `is_muted(now)`, `clear()`
  - `RECONNECT_ANNOUNCE_AFTER = 120.0`

**Beides ist Zustand über die Zeit** — deshalb eigene, prüfbare Einheiten statt
Flaggen in der Schleife.

**Die Stummschaltung reist auf demselben Weg wie das Gaming-Gate.** `deliver()`
bekommt keinen zweiten Parameter; `hold_probe` liefert künftig
`gaming or quiet.is_muted(now)`. Für `deliver` ist „zurückhalten" eine Tatsache,
kein Grund.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_announce.py`:

```python
"""Connection announcements and quiet mode."""

from baluhost_tray.announce import (
    RECONNECT_ANNOUNCE_AFTER,
    ConnectionAnnouncer,
    QuietMode,
)


def test_offline_announced_once():
    announcer = ConnectionAnnouncer()
    assert announcer.went_offline(now=100.0) is not None
    assert announcer.went_offline(now=160.0) is None, "kein Piepen im Minutentakt"


def test_short_outage_is_not_announced_on_return():
    announcer = ConnectionAnnouncer()
    announcer.went_offline(now=100.0)
    assert announcer.came_online(now=100.0 + RECONNECT_ANNOUNCE_AFTER - 1) is None


def test_long_outage_is_announced_on_return():
    announcer = ConnectionAnnouncer()
    announcer.went_offline(now=100.0)
    assert announcer.came_online(now=100.0 + RECONNECT_ANNOUNCE_AFTER + 1) is not None


def test_offline_can_be_announced_again_after_a_return():
    announcer = ConnectionAnnouncer()
    announcer.went_offline(now=100.0)
    announcer.came_online(now=500.0)
    assert announcer.went_offline(now=600.0) is not None


def test_return_without_prior_outage_is_silent():
    """Der erste Verbindungsaufbau beim Start ist keine Rueckkehr."""
    assert ConnectionAnnouncer().came_online(now=100.0) is None


def test_quiet_mode_expires():
    quiet = QuietMode()
    quiet.mute_for(3600.0, now=1000.0)
    assert quiet.is_muted(now=1000.0 + 3599)
    assert not quiet.is_muted(now=1000.0 + 3601)


def test_quiet_mode_off_by_default():
    assert not QuietMode().is_muted(now=1000.0)


def test_quiet_mode_can_be_cleared():
    quiet = QuietMode()
    quiet.mute_for(3600.0, now=1000.0)
    quiet.clear()
    assert not quiet.is_muted(now=1001.0)
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_announce.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray.announce'`

- [ ] **Step 3: Minimal implementieren**

`backend/baluhost_tray/announce.py`:

```python
"""When to speak about the connection, and when to stay quiet.

Both are state over time, which is why they live here as small testable units
rather than as flags scattered through the loop.
"""

from __future__ import annotations

RECONNECT_ANNOUNCE_AFTER = 120.0


class ConnectionAnnouncer:
    """Says "gone" once, and "back" only after a real outage.

    A backend that flaps must not produce a stream of popups: the outage is
    announced on first detection and then never again until the connection
    actually returned.
    """

    def __init__(self, reconnect_after: float = RECONNECT_ANNOUNCE_AFTER) -> None:
        self._reconnect_after = reconnect_after
        self._offline_since: float | None = None
        self._announced = False

    def went_offline(self, now: float) -> tuple[str, str] | None:
        if self._announced:
            return None
        self._offline_since = now
        self._announced = True
        return ("BaluHost", "Keine Verbindung zum Backend")

    def came_online(self, now: float) -> tuple[str, str] | None:
        since, self._offline_since = self._offline_since, None
        self._announced = False
        if since is None or now - since < self._reconnect_after:
            return None
        return ("BaluHost", "Verbindung wiederhergestellt")


class QuietMode:
    """Hold popups until a deadline, set from the tray menu."""

    def __init__(self) -> None:
        self._until = 0.0

    def mute_for(self, seconds: float, now: float) -> None:
        self._until = now + seconds

    def clear(self) -> None:
        self._until = 0.0

    def is_muted(self, now: float) -> bool:
        return now < self._until
```

- [ ] **Step 4: In die Schleife einhängen**

In `backend/baluhost_tray/loop.py`:

```python
from baluhost_tray.announce import ConnectionAnnouncer, QuietMode
```

`LoopContext` um zwei Felder erweitern:

```python
    announcer: ConnectionAnnouncer = field(default_factory=ConnectionAnnouncer)
    quiet: QuietMode = field(default_factory=QuietMode)
```

In `run_cycle`, direkt nach `ctx.state.set_connected(True)`:

```python
        back = ctx.announcer.came_online(ctx.now())
        if back:
            try:
                await ctx.notifier.show_summary(*back)
            except Exception as exc:
                logger.debug("reconnect notice failed: %s", exc)
```

In `run_loop`, vor dem Backoff (an der Stelle, an der bereits
`ctx.state.set_connected(False)` steht):

```python
        gone = ctx.announcer.went_offline(ctx.now())
        if gone:
            try:
                await ctx.notifier.show_summary(*gone)
            except Exception as exc:
                logger.debug("offline notice failed: %s", exc)
```

Und der Grund für „zurückhalten" bekommt seine zweite Quelle. Statt
`ctx.hold_probe` direkt zu rufen, überall:

```python
async def _should_hold(ctx: LoopContext) -> bool:
    """Two reasons, one answer: a game on screen or an active quiet hour."""
    if ctx.quiet.is_muted(ctx.now()):
        return True
    return await asyncio.to_thread(ctx.hold_probe)
```

und die drei Aufrufstellen in `run_cycle` darauf umstellen. Der
`hold_probe`-Aufruf entfällt damit, solange stumm geschaltet ist — das spart
zugleich die HTTP-Abfrage.

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/ -v`
Expected: PASS

- [ ] **Step 6: Committen**

```bash
git add backend/baluhost_tray/announce.py backend/baluhost_tray/loop.py backend/tests/tray/test_announce.py
git commit -m "feat(tray): Verbindungsmeldungen und Stummschaltung

Eine Meldung beim Verbindungsverlust, danach Ruhe; eine Rueckmeldung nur
nach mehr als zwei Minuten Unterbrechung. Ein flatterndes Backend darf
keinen Popup-Strom erzeugen.

Die Stummschaltung reist auf demselben Weg wie das Gaming-Gate: deliver()
bekommt keinen zweiten Parameter, sondern eine Tatsache. Zurueckgehaltenes
kommt in beiden Faellen spaeter an.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 19: Qt-Oberfläche, Einstiegspunkt und Paketierung

**Files:**
- Create: `backend/baluhost_tray/tray.py`, `backend/baluhost_tray/main.py`, `backend/baluhost_tray/__main__.py`
- Modify: `backend/pyproject.toml` (`[tool.setuptools.packages.find]`, `[tool.setuptools.package-data]`, `[project.optional-dependencies]`, `[project.scripts]`)
- Test: `backend/tests/tray/test_main_wiring.py`

**Interfaces:**
- Consumes: alle vorherigen Tasks.
- Produces: Konsolenskript `baluhost-tray`, Extra `tray`.

**Die Paketierung ist der Teil, der sonst erst in Produktion auffällt.**
`backend/pyproject.toml:84-86` sammelt Pakete mit
`include = ["app*", "baluhost_tui*"]`. Ein Geschwistermodul `baluhost_tray` ist
darin **nicht enthalten** — das Konsolenskript würde installiert, das Modul
nicht, und die systemd-Unit begänne mit `ModuleNotFoundError`. Dazu fehlen ohne
`package-data` die Icons im Wheel, und `icon_path()` zeigte auf nichts.

**Qt wird nur aus dem GUI-Thread angefasst.** Der Worker meldet Zustände über
ein `pyqtSignal`; thread-übergreifend ist das standardmäßig eine
`QueuedConnection` und damit genau der richtige Weg. `setIcon` direkt aus dem
asyncio-Thread zu rufen ist eine Regelverletzung mit unbestimmtem Ausgang.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_main_wiring.py`:

```python
"""The entry point must fail politely, never with a traceback.

It runs from a systemd user unit, where a stack trace lands in the journal
and nowhere anybody looks.
"""

from unittest.mock import patch

from baluhost_tray import main as tray_main
from baluhost_tray.single_instance import AlreadyRunning


def test_second_instance_exits_cleanly(capsys):
    with patch("baluhost_tray.main.single_instance.acquire",
               side_effect=AlreadyRunning("held")):
        code = tray_main.run(argv=[])
    assert code == 0
    assert "läuft bereits" in capsys.readouterr().out


def test_missing_pairing_exits_zero_and_points_at_pair(capsys):
    """Exit 0, nicht 2: mit Restart=on-failure wuerde systemd sonst alle zehn
    Sekunden neu starten, bis die Unit auf failed steht."""
    with patch("baluhost_tray.main.single_instance.acquire"), \
         patch("baluhost_tray.main.tray_config.load_tokens", return_value=None):
        code = tray_main.run(argv=[])
    assert code == 0
    assert "--pair" in capsys.readouterr().out


def test_pairing_does_not_take_the_tray_lock():
    """--pair muss neben dem laufenden Dienst funktionieren."""
    names = []

    def _acquire(name="baluhost-tray"):
        names.append(name)
        return object()

    with patch("baluhost_tray.main.single_instance.acquire", side_effect=_acquire), \
         patch("baluhost_tray.main.run_pairing", return_value=0):
        tray_main.run(argv=["--pair"])

    assert names and all(n != "baluhost-tray" for n in names)


def test_no_session_bus_exits_with_hint(capsys):
    from baluhost_tray.notify import NotifierUnavailable

    with patch("baluhost_tray.main.single_instance.acquire"), \
         patch("baluhost_tray.main.tray_config.load_tokens", return_value=object()), \
         patch("baluhost_tray.main.start_qt_app",
               side_effect=NotifierUnavailable("no bus")):
        code = tray_main.run(argv=[])
    assert code == 3
    assert "Plasma" in capsys.readouterr().out
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_main_wiring.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray.main'`

- [ ] **Step 3: Einstiegspunkt implementieren**

`backend/baluhost_tray/main.py`:

```python
"""Entry point for `baluhost-tray`.

Every failure here is a message, never a traceback.
"""

from __future__ import annotations

import argparse
import sys

from baluhost_tray import config as tray_config
from baluhost_tray import single_instance
from baluhost_tray.notify import NotifierUnavailable

DEFAULT_BASE_URL = "http://localhost:8000"
TRAY_LOCK = "baluhost-tray"
PAIR_LOCK = "baluhost-tray-pair"


def start_qt_app(base_url: str) -> int:
    """Import Qt lazily so --pair and the tests work without PyQt6."""
    from baluhost_tray.tray import run_tray

    return run_tray(base_url)


def run_pairing(base_url: str) -> int:
    from baluhost_tray.tray import run_pairing_flow

    return run_pairing_flow(base_url)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="baluhost-tray")
    parser.add_argument("--pair", action="store_true",
                        help="Dieses Gerät mit BaluHost koppeln")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args(argv)

    # Pairing takes its own lock so it works while the service is running.
    lock_name = PAIR_LOCK if args.pair else TRAY_LOCK
    try:
        single_instance.acquire(lock_name)
    except single_instance.AlreadyRunning:
        print("BaluHost Tray läuft bereits in dieser Sitzung.")
        return 0

    if args.pair:
        return run_pairing(args.base_url)

    if tray_config.load_tokens() is None:
        # Exit 0 on purpose: with Restart=on-failure a non-zero code would
        # have systemd restart this every ten seconds until the unit fails.
        print("Nicht gekoppelt. Einmalig ausführen: baluhost-tray --pair")
        return 0

    try:
        return start_qt_app(args.base_url)
    except NotifierUnavailable:
        print("Keine Desktop-Sitzung gefunden — das Tray braucht ein "
              "laufendes Plasma mit D-Bus.")
        return 3


def cli() -> None:
    sys.exit(run())
```

`backend/baluhost_tray/__main__.py`:

```python
from baluhost_tray.main import cli

cli()
```

- [ ] **Step 4: Qt-Oberfläche implementieren**

`backend/baluhost_tray/tray.py` — nur Darstellung:

```python
"""Qt surface. Rendering only — every decision lives in loop.py / state.py."""

from __future__ import annotations

import asyncio
import threading
import time

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from baluhost_tray.icons import SIZES, icon_path
from baluhost_tray.state import IconState, PopupQueue, TrayState

MENU_OPEN = "BaluHost öffnen"
MENU_QUIET = "Eine Stunde stumm"
MENU_REPAIR = "Neu koppeln"
MENU_QUIT = "Beenden"
QUIET_SECONDS = 3600.0


class _Bridge(QObject):
    """Carries worker-thread results into the GUI thread.

    A cross-thread signal is a QueuedConnection by default, which is the only
    correct way to touch a QSystemTrayIcon from asyncio.
    """

    state_changed = pyqtSignal(str)   # IconState.value
    tooltip_changed = pyqtSignal(str)


def _build_icons() -> dict[IconState, QIcon]:
    """One QIcon per state, all sizes inside it.

    Plasma picks the right size itself on HiDPI panels; handing it only the
    22 px file would make it upscale.
    """
    icons: dict[IconState, QIcon] = {}
    for state in IconState:
        icon = QIcon()
        for size in SIZES:
            icon.addFile(str(icon_path(state, size)))
        icons[state] = icon
    return icons


def run_tray(base_url: str) -> int:
    """Start the Qt loop with the asyncio work on a worker thread."""
    from baluhost_tray.announce import QuietMode
    from baluhost_tray.loop import LoopContext, is_gaming_active, run_loop
    from baluhost_tray.notify import Notifier
    from baluhost_tray.session import Session
    from baluhost_tray.watch import Watcher

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)

    icons = _build_icons()
    state = TrayState()
    queue = PopupQueue()
    quiet = QuietMode()

    tray_icon = QSystemTrayIcon(icons[IconState.OFFLINE])
    tray_icon.setToolTip(state.tooltip())

    bridge = _Bridge()
    bridge.state_changed.connect(
        lambda value: tray_icon.setIcon(icons[IconState(value)])
    )
    bridge.tooltip_changed.connect(tray_icon.setToolTip)

    menu = QMenu()
    open_action = menu.addAction(MENU_OPEN)
    open_action.triggered.connect(
        lambda: QDesktopServices.openUrl(QUrl(base_url))
    )
    quiet_action = menu.addAction(MENU_QUIET)
    quiet_action.triggered.connect(
        lambda: quiet.mute_for(QUIET_SECONDS, time.monotonic())
    )
    repair_action = menu.addAction(MENU_REPAIR)
    repair_action.triggered.connect(
        lambda: QDesktopServices.openUrl(QUrl(f"{base_url}/devices?pair=1"))
    )
    menu.addSeparator()
    menu.addAction(MENU_QUIT).triggered.connect(app.quit)
    tray_icon.setContextMenu(menu)
    tray_icon.show()

    session = Session(base_url)
    notifier = Notifier()

    def _sink(icon_state: IconState) -> None:
        bridge.state_changed.emit(icon_state.value)
        bridge.tooltip_changed.emit(state.tooltip())

    async def _main() -> None:
        import websockets

        await notifier.connect()
        ctx = LoopContext(
            session=session,
            watcher=Watcher(session, state),
            state=state,
            queue=queue,
            notifier=notifier,
            sink=_sink,
            hold_probe=lambda: is_gaming_active(session.client()),
            connect=websockets.connect,
            quiet=quiet,
        )
        await run_loop(ctx)

    threading.Thread(target=lambda: asyncio.run(_main()), daemon=True).start()
    return app.exec()


def run_pairing_flow(base_url: str) -> int:
    """Console pairing: print the code, poll until approved."""
    from baluhost_tray import pairing
    from baluhost_tray.config import save_tokens
    from baluhost_tui.client import BackendClient

    client = BackendClient(server=base_url)
    pending = pairing.start_pairing(client)
    print(f"Code: {pending.user_code}")
    print(f"Freigeben unter: {pending.verification_url}")
    print("Hinweis: zeigt der Link auf den Backend-Port, stattdessen die "
          "normale Web-UI öffnen und dort unter Geräte freigeben.")

    deadline = time.monotonic() + pending.expires_in
    while time.monotonic() < deadline:
        tokens = pairing.poll_once(client, pending.device_code)
        if tokens:
            save_tokens(tokens)
            print("Gekoppelt.")
            return 0
        time.sleep(pending.interval + 1)   # 12/min Limit, nicht auf der Kante

    print("Code abgelaufen — bitte erneut versuchen.")
    return 4
```

**Zwei Dinge, die beim Schreiben zu prüfen sind:** ob `websockets.connect(url)`
als Kontextmanager mit `recv()` zum `LoopContext.connect` passt (die Version im
venv gegenlesen), und ob `NotifierUnavailable` aus `_main()` sichtbar wird —
die Exception fliegt im Worker-Thread und beendet ihn still. Sie muss vor dem
Thread-Start ausgelöst oder über `_sink` sichtbar gemacht werden; der Test
`test_no_session_bus_exits_with_hint` setzt voraus, dass `start_qt_app` sie
durchreicht.

- [ ] **Step 5: Paketierung eintragen**

In `backend/pyproject.toml`:

```toml
[tool.setuptools.packages.find]
include = ["app*", "baluhost_tui*", "baluhost_tray*"]

[tool.setuptools.package-data]
baluhost_tray = ["icons/*.png"]
```

```toml
tray = [
  "PyQt6>=6.6.0,<7.0.0",
  "websockets>=12.0,<16.0"
]
```

```toml
baluhost-tray = "baluhost_tray.main:cli"
```

- [ ] **Step 6: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/ -v`
Expected: PASS — `test_main_wiring.py` läuft ohne PyQt6, weil der Qt-Import in
`start_qt_app` gekapselt ist

Run: `cd backend && .venv/bin/python -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text()); print(d['tool']['setuptools']['packages']['find']['include']); print(d['tool']['setuptools'].get('package-data'))"`
Expected: `baluhost_tray*` ist enthalten, `package-data` nennt die Icons

- [ ] **Step 7: Committen**

```bash
git add backend/baluhost_tray/tray.py backend/baluhost_tray/main.py backend/baluhost_tray/__main__.py backend/pyproject.toml backend/tests/tray/test_main_wiring.py
git commit -m "feat(tray): Qt-Oberflaeche, Einstiegspunkt und Paketierung

Der Worker fasst Qt nie direkt an: Zustaende gehen ueber ein pyqtSignal,
thread-uebergreifend also eine QueuedConnection. setIcon aus dem
asyncio-Thread waere eine Regelverletzung mit offenem Ausgang.

packages.find sammelte nur app* und baluhost_tui* -- das Konsolenskript
waere installiert worden, das Modul nicht, und die Unit haette mit
ModuleNotFoundError begonnen. Ohne package-data fehlten ausserdem die
Icons im Wheel.

--pair nimmt einen eigenen Lock, damit Neukoppeln neben dem laufenden
Dienst funktioniert, und 'nicht gekoppelt' endet mit 0 statt 2: sonst
startet systemd das alle zehn Sekunden neu, bis die Unit auf failed steht.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 20: Autostart, Installation, Dokumentation und Abnahme

**Files:**
- Create: `deploy/install/templates/baluhost-tray.service`
- Modify: `deploy/install/modules/10-systemd-services.sh`
- Create: `docs/features/desktop-tray.md`
- Test: `backend/tests/tray/test_unit_template.py`

**Interfaces:**
- Consumes: Konsolenskript `baluhost-tray` (Task 19).
- Produces: `baluhost-tray.service` als systemd-`--user`-Unit.

**Die Benutzerfrage muss gestellt, nicht geraten werden.** Das Modul kennt
`BALUHOST_USER` — das vom Installer angelegte **Dienstkonto**
(`03-user-setup.sh`, `useradd --create-home`). Das ist nicht zwingend der
Mensch, der sich in Plasma anmeldet. Eine User-Unit im Home des Dienstkontos
startet in keiner Desktop-Sitzung. Deshalb: Zielbenutzer explizit bestimmen
(Variable `TRAY_DESKTOP_USER`, Vorgabe `SUDO_USER`), und wenn er nicht
feststeht, die Unit ablegen und den Schritt zum manuellen Aktivieren melden —
nicht stillschweigend ins falsche Home schreiben.

**Platzhalter-Konvention:** `@@KEY@@` plus `process_template()`
(`deploy/install/lib/common.sh:115-148`), wie in
`deploy/install/templates/baluhost-monitoring.service`. Rohes `sed` umgeht den
`patsub_replacement`-Schutz aus #581.

**Einhängepunkt:** `10-systemd-services.sh` endet mit `exit 0` in Zeile 266.
Alles danach ist toter Code. Die Funktion gehört vor die Summary, der Aufruf in
den Abschlussblock ab Zeile 228.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_unit_template.py`:

```python
"""The unit template must stay a user unit and stay unprivileged."""

from pathlib import Path

import pytest

TEMPLATE = (
    Path(__file__).resolve().parents[3]
    / "deploy" / "install" / "templates" / "baluhost-tray.service"
)


@pytest.fixture
def text() -> str:
    return TEMPLATE.read_text()


def test_template_exists():
    assert TEMPLATE.exists()


def test_is_bound_to_the_graphical_session(text: str):
    assert "graphical-session.target" in text


def test_restarts_on_failure(text: str):
    assert "Restart=on-failure" in text


def test_never_asks_for_root(text: str):
    """Ein User=root hier waere ein Bruch der Zusage aus der Spec."""
    assert "User=root" not in text
    assert "sudo" not in text


def test_uses_the_repo_placeholder_convention(text: str):
    """@@KEY@@ plus process_template, nicht rohes sed."""
    assert "@@INSTALL_DIR@@" in text
    assert "__INSTALL_DIR__" not in text


def test_does_not_thrash_when_unpaired(text: str):
    """Ohne Token soll die Unit gar nicht erst starten."""
    assert "ConditionPathExists=" in text
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_unit_template.py -v`
Expected: FAIL — die Vorlage fehlt

- [ ] **Step 3: Unit-Vorlage schreiben**

`deploy/install/templates/baluhost-tray.service`:

```ini
[Unit]
Description=BaluHost Desktop Tray (KDE Plasma)
PartOf=graphical-session.target
After=graphical-session.target
# Ohne Kopplung gibt es nichts zu zeigen. Ohne diese Bedingung wuerde die
# Unit starten, sich sofort beenden und von Restart=on-failure im
# Zehnsekundentakt wiederbelebt, bis das Startlimit greift.
ConditionPathExists=%h/.baluhost/tray-tokens.json

[Service]
Type=simple
ExecStart=@@INSTALL_DIR@@/backend/.venv/bin/baluhost-tray
Restart=on-failure
RestartSec=10s
# Kein root, keine Rechteerweiterung: das Tray liest nur.
NoNewPrivileges=yes

[Install]
WantedBy=graphical-session.target
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_unit_template.py -v`
Expected: PASS (6 Tests)

- [ ] **Step 5: Installationsschritt ergänzen**

In `deploy/install/modules/10-systemd-services.sh`, **vor** dem Abschlussblock
(ab Zeile 228) definieren und dort aufrufen — nicht hinter `exit 0` in Zeile
266:

```bash
install_tray_user_unit() {
    # BALUHOST_USER ist das Dienstkonto, nicht zwingend der Mensch an der
    # Tastatur. Eine User-Unit im Home des Dienstkontos startet in keiner
    # Desktop-Sitzung, deshalb wird der Desktop-Benutzer getrennt bestimmt.
    local target_user="${TRAY_DESKTOP_USER:-${SUDO_USER:-}}"
    if [ -z "$target_user" ]; then
        log_warn "Kein Desktop-Benutzer bekannt — Tray-Unit nicht installiert."
        log_warn "Nachtraeglich: TRAY_DESKTOP_USER=<name> erneut ausfuehren."
        return 0
    fi

    local user_home
    user_home="$(getent passwd "$target_user" | cut -d: -f6)"
    if [ -z "$user_home" ] || [ ! -d "$user_home" ]; then
        log_warn "Kein Home fuer $target_user — Tray-Unit uebersprungen."
        return 0
    fi

    local unit_dir="$user_home/.config/systemd/user"
    install -d -o "$target_user" -g "$target_user" "$unit_dir"
    process_template \
        "$TEMPLATE_DIR/baluhost-tray.service" \
        "$unit_dir/baluhost-tray.service" \
        "INSTALL_DIR=$INSTALL_DIR"
    chown "$target_user:$target_user" "$unit_dir/baluhost-tray.service"

    local uid runtime
    uid="$(id -u "$target_user")"
    runtime="/run/user/$uid"
    if [ -d "$runtime" ] && sudo -u "$target_user" \
        XDG_RUNTIME_DIR="$runtime" systemctl --user daemon-reload 2>/dev/null; then
        sudo -u "$target_user" XDG_RUNTIME_DIR="$runtime" \
            systemctl --user enable baluhost-tray.service
        log_info "Tray-Unit installiert und aktiviert fuer $target_user"
    else
        log_info "Tray-Unit fuer $target_user abgelegt — beim naechsten Login aktiv"
    fi
}
```

**Vor dem Schreiben gegenlesen:** die genaue Signatur von `process_template`
(`deploy/install/lib/common.sh:115-148`) sowie die Namen `INSTALL_DIR`,
`TEMPLATE_DIR`, `log_info`, `log_warn` im Modul. `SERVICE_USER` existiert dort
**nicht** — die Variable wird nur in `lib/features.sh:113,117` für
Feature-Subskripte exportiert.

- [ ] **Step 6: Dokumentation schreiben**

`docs/features/desktop-tray.md` mit:

- Was das Icon zeigt: vier Zustände, und ausdrücklich, dass **grün „nichts
  Ungelesenes" heißt und keine Gesundheitsaussage ist** — wer eine Meldung
  liest, während das RAID degradiert bleibt, sieht grün.
- Kopplung: `baluhost-tray --pair`, sechsstelliger Code, Freigabe in der Web-UI
  unter Geräte. Funktioniert auch, während der Dienst läuft.
- Verhalten beim Spielen: Popups werden zurückgehalten und nach der Sitzung
  zugestellt, ab vier Meldungen gesammelt. Plasmas „Nicht stören" greift
  zusätzlich.
- Stummschaltung: eine Stunde über das Menü, danach kommt Zurückgehaltenes.
- Wo die Zugangsdaten liegen: `~/.baluhost/tray-tokens.json`, `0600`. Es ist
  ein vollwertiges Nutzer-Token — wer Zugriff auf die Datei hat, hat Zugriff
  auf die API mit den Rechten dieses Kontos.
- Widerruf: in der Web-UI unter Geräte; das Tray geht danach in den Zustand
  „nicht gekoppelt" und meldet sich einmal.
- Dienst: `systemctl --user status baluhost-tray`, Logs über
  `journalctl --user -u baluhost-tray`.

- [ ] **Step 7: Manuelle Abnahme auf dem Zielrechner**

Kein CI-Ersatz — diese Schritte muss ein Mensch sehen:

1. `systemctl --user start baluhost-tray` → Icon erscheint im Panel.
2. Backend stoppen → Icon wird grau, **eine** Meldung, danach Ruhe.
3. Backend starten → Icon wird grün; Rückmeldung nur bei Unterbrechung über
   zwei Minuten.
4. Kritische Testmeldung erzeugen → rotes Icon plus Popup.
   **Achtung bei der Wahl der Testmeldung:** Einen spontan degradierenden RAID
   gibt es nicht zu simulieren — `emit_raid_degraded_sync` wird nur aus
   `degrade()` gerufen, also wenn BaluHost selbst ein Device ausfallen lässt.
   Für die Abnahme entweder `simulate_failure` im Dev-Backend benutzen oder
   eine Meldung über `POST /api/notifications` erzeugen.
5. Dieselbe Meldung **auf dem Handy** wegwischen → Icon wird ohne Zutun grün.
6. Meldung snoozen, Frist kurz wählen → Icon grün, und nach spätestens zehn
   Minuten (Neuabgleich) wieder rot.
7. Spiel im Vollbild starten — **direkt aus Steam, nicht über BaluHost** —,
   Testmeldung erzeugen → kein Popup, Icon rot.
8. Spiel beenden → innerhalb von 30 Sekunden wird die zurückgehaltene Meldung
   zugestellt.
9. „Eine Stunde stumm" wählen, Meldung erzeugen → kein Popup; Menüpunkt erneut
   wählen oder abwarten → Zustellung.
10. Zweites `baluhost-tray` starten → beendet sich mit Hinweis.
11. `baluhost-tray --pair` bei laufendem Dienst → zeigt einen Code, statt sich
    zu beenden.
12. Kopplung in der Web-UI widerrufen → Icon grau, eine Meldung, kein Sturm
    von Anfragen im Log.

- [ ] **Step 8: Committen**

```bash
git add deploy/install/templates/baluhost-tray.service deploy/install/modules/10-systemd-services.sh docs/features/desktop-tray.md backend/tests/tray/test_unit_template.py
git commit -m "feat(tray): Autostart als systemd-user-Unit, Installation und Doku

Bewusst eine User-Unit an graphical-session.target: das Tray gehoert zur
Desktop-Sitzung, nicht zum Systemstart, und braucht kein root.

Der Zielbenutzer wird getrennt bestimmt statt aus BALUHOST_USER
abgeleitet -- das ist das Dienstkonto, und eine User-Unit in dessen Home
startet in keiner Desktop-Sitzung. Ohne bekannten Benutzer wird die Unit
abgelegt und der Schritt gemeldet, nicht ins falsche Home geschrieben.

ConditionPathExists auf die Token-Datei: ohne Kopplung soll die Unit gar
nicht erst starten, statt im Zehnsekundentakt gegen Restart=on-failure
zu laufen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Abschluss

- [ ] **Volle Testrunde**

Run: `cd backend && .venv/bin/pytest tests/tray tests/api/test_notification_fanout.py tests/api/test_desktop_pairing_refresh.py tests/services/test_websocket_manager.py tests/services/test_event_emitter_broadcast.py tests/plugins -k "tray or notification or steam_gaming or pairing" -v`

Run: `cd backend && .venv/bin/ruff check baluhost_tray/ app/api/routes/_notification_fanout.py`

Run: `cd client && npx vitest run src/__tests__/hooks/useNotificationSocket.test.tsx && npm run build`

- [ ] **Gegenprobe: Paketierung greift wirklich**

Run: `cd backend && .venv/bin/python -m build --wheel --outdir /tmp/tray-wheel 2>/dev/null || .venv/bin/pip wheel . --no-deps -w /tmp/tray-wheel`
Run: `python3 -c "import zipfile,glob; z=zipfile.ZipFile(glob.glob('/tmp/tray-wheel/*.whl')[0]); names=z.namelist(); assert any(n.startswith('baluhost_tray/') for n in names), 'Modul fehlt im Wheel'; assert any(n.endswith('.png') for n in names if 'baluhost_tray' in n), 'Icons fehlen im Wheel'; print('Wheel enthaelt Modul und Icons')"`

Das ist die einzige Prüfung, die den Fehler „Konsolenskript installiert, Modul
nicht" tatsächlich fängt.

- [ ] **Branch abschließen**

REQUIRED SUB-SKILL: `superpowers:finishing-a-development-branch`
