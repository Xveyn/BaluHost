# Desktop-Tray für KDE Plasma — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Tray-Icon im Plasma-Panel, dessen Farbe den Zustand der Anlage
trägt und das kritische Ereignisse als Desktop-Meldung zustellt — synchron mit
Web-App und BaluApp.

**Architecture:** Das Icon ist eine Projektion der ungelesenen Meldungen, kein
zweiter Gesundheitsbegriff. Phase A schließt die Lücke im Backend
(Zustandsänderungen erreichen offene Clients nicht) und ist für sich lieferbar;
Web und Android profitieren sofort. Phase B baut darauf das Tray als
Python-Modul neben der vorhandenen TUI.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, pytest/pytest-asyncio ·
PyQt6 (`QSystemTrayIcon`), `dbus-next`, `httpx`, `websockets` ·
React/TypeScript mit Vitest im Frontend.

**Spec:** `docs/superpowers/specs/2026-09-21-desktop-tray-design.md`

## Global Constraints

- **Branch:** `feat/desktop-tray`, Basis `main` @ `2ed58e59`.
- **Keine `from __future__ import annotations` in Plugin-Routen.** Hinter dem
  `@user_limiter.limit`-Wrapper von slowapi werden zurückgestellte Annotationen
  zu ForwardRefs, die FastAPI nicht mehr auflöst — jeder Request wird 422.
  Gilt für Task 10. (Kommentar steht so in `steam_gaming/routes.py`.)
- **Blockierende Dateisystem-Zugriffe in async-Routen über `asyncio.to_thread`.**
- **Der Fan-out sitzt in der Route-Ebene, nicht im Service.** Die
  Zustandsmethoden des `NotificationService` sind synchron (`def` mit
  `Session`); der Versand ist `async`.
- **`broadcast_to_user()` ist für den Fan-out unbrauchbar** — es setzt
  `"type": "notification"` fest.
- **Kein root, keine sudoers-Erweiterung.** Das Tray fasst nichts
  Privilegiertes an.
- **PyQt6 nur als optionales Extra** `tray`, damit der Server die
  GUI-Abhängigkeit nicht mitschleppt.
- **Tests laufen ohne D-Bus, ohne Plasma, ohne echten WebSocket-Server.**
- **Commit-Format:** Conventional Commits (`CONTRIBUTING.md`), deutsche
  Beschreibung, Footer `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

# Phase A — Fan-out der Zustandsänderungen

Eigenständig lieferbar. Nach Task 4 ziehen offene Web-UIs live nach, ohne dass
eine Zeile Tray-Code existiert.

### Task 1: `send_notification_state()` im WebSocketManager

**Files:**
- Modify: `backend/app/services/websocket_manager.py` (nach `send_unread_count`, ab Zeile 250)
- Test: `backend/tests/services/test_websocket_manager.py`

**Interfaces:**
- Consumes: nichts.
- Produces: `async def send_notification_state(self, user_id: int, ids: list[int], action: str) -> int`
  — sendet `{"type": "notification_state", "payload": {"ids": [...], "action": "..."}}`
  an alle Verbindungen des Nutzers, gibt die Zahl der erreichten Verbindungen
  zurück. Erlaubte `action`-Werte: `"read"`, `"dismissed"`, `"snoozed"`,
  `"deleted"`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

An `backend/tests/services/test_websocket_manager.py` anhängen:

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

In `backend/app/services/websocket_manager.py` direkt nach `send_unread_count`
einfügen — bewusst derselbe Aufbau wie dort, inklusive Aufräumen toter
Verbindungen:

```python
    async def send_notification_state(
        self, user_id: int, ids: list[int], action: str
    ) -> int:
        """Tell a user's connections that notification state changed elsewhere.

        Counterpart to send_unread_count: that one carries the number, this
        one carries which notifications changed and how, so an open client can
        update its list without refetching. broadcast_to_user() cannot be used
        here — it hardcodes "type": "notification".

        Args:
            user_id: Target user ID
            ids: Affected notification IDs
            action: "read" | "dismissed" | "snoozed" | "deleted"

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

- [ ] **Step 4: Tests laufen lassen, Erfolg bestätigen**

Run: `cd backend && .venv/bin/pytest tests/services/test_websocket_manager.py -v`
Expected: PASS (auch die bestehenden Klassen)

- [ ] **Step 5: Committen**

```bash
git add backend/app/services/websocket_manager.py backend/tests/services/test_websocket_manager.py
git commit -m "feat(notifications): send_notification_state verteilt Zustandsaenderungen an alle Verbindungen eines Nutzers

Gegenstueck zu send_unread_count: traegt, welche Meldungen sich wie
geaendert haben, damit ein offener Client seine Liste nachziehen kann
ohne neu zu laden. broadcast_to_user war dafuer unbrauchbar, weil es
den Typ 'notification' festsetzt.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Fan-out-Helfer und Einbau in die sechs Routen

**Files:**
- Create: `backend/app/api/routes/_notification_fanout.py`
- Modify: `backend/app/api/routes/notifications.py` (Handler ab Zeile 149: `/read`, `/read-all`, `/dismiss-all`, `/{id}/dismiss`, `/{id}/snooze`, `/{id}` DELETE)
- Test: `backend/tests/api/test_notification_fanout.py`

**Interfaces:**
- Consumes: `WebSocketManager.send_notification_state` (Task 1), das vorhandene
  `send_unread_count`, `get_websocket_manager()`, `NotificationService.get_unread_count`.
- Produces: `async def fanout_state(db: Session, user_id: int, ids: list[int], action: str, is_admin: bool) -> None`
  — ruft `send_notification_state` und danach `send_unread_count` mit dem
  frisch berechneten Zählerstand. Schluckt Versandfehler.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

Neue Datei `backend/tests/api/test_notification_fanout.py`:

```python
"""Tests for the notification state fan-out helper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.routes._notification_fanout import fanout_state


@pytest.fixture
def ws_manager() -> MagicMock:
    manager = MagicMock()
    manager.send_notification_state = AsyncMock(return_value=1)
    manager.send_unread_count = AsyncMock(return_value=1)
    return manager


@pytest.mark.asyncio
async def test_sends_state_then_count(ws_manager: MagicMock):
    db = MagicMock()
    service = MagicMock()
    service.get_unread_count.return_value = 3

    with patch(
        "app.api.routes._notification_fanout.get_websocket_manager",
        return_value=ws_manager,
    ), patch(
        "app.api.routes._notification_fanout.get_notification_service",
        return_value=service,
    ):
        await fanout_state(db, user_id=1, ids=[7], action="read", is_admin=False)

    ws_manager.send_notification_state.assert_awaited_once_with(1, [7], "read")
    ws_manager.send_unread_count.assert_awaited_once_with(1, 3)


@pytest.mark.asyncio
async def test_empty_ids_sends_nothing(ws_manager: MagicMock):
    db = MagicMock()
    with patch(
        "app.api.routes._notification_fanout.get_websocket_manager",
        return_value=ws_manager,
    ):
        await fanout_state(db, user_id=1, ids=[], action="read", is_admin=False)

    ws_manager.send_notification_state.assert_not_awaited()
    ws_manager.send_unread_count.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_failure_does_not_propagate(ws_manager: MagicMock):
    """A dead socket must never turn a successful POST /read into a 500."""
    db = MagicMock()
    service = MagicMock()
    service.get_unread_count.return_value = 0
    ws_manager.send_notification_state.side_effect = RuntimeError("socket gone")

    with patch(
        "app.api.routes._notification_fanout.get_websocket_manager",
        return_value=ws_manager,
    ), patch(
        "app.api.routes._notification_fanout.get_notification_service",
        return_value=service,
    ):
        await fanout_state(db, user_id=1, ids=[7], action="read", is_admin=False)
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/api/test_notification_fanout.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.api.routes._notification_fanout'`

- [ ] **Step 3: Minimal implementieren**

Neue Datei `backend/app/api/routes/_notification_fanout.py`:

```python
"""Fan-out of notification state changes to a user's open connections.

Lives in the route layer on purpose: the NotificationService state methods
are synchronous (def, Session), the send is async. A fan-out inside the
service would have to schedule a task on a foreign event loop from
synchronous code — fragile and hard to test. All six routes that change
state call this one helper so they cannot drift apart.
"""

import logging

from sqlalchemy.orm import Session

from app.services.notifications.service import get_notification_service
from app.services.websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)

VALID_ACTIONS = frozenset({"read", "dismissed", "snoozed", "deleted"})


async def fanout_state(
    db: Session,
    user_id: int,
    ids: list[int],
    action: str,
    is_admin: bool,
) -> None:
    """Tell the user's other clients that these notifications changed.

    Never raises: a dead socket must not turn a successful state change into
    a failed request. The database write has already happened when we get
    here; the client that made it has its answer either way.
    """
    if not ids:
        return
    if action not in VALID_ACTIONS:
        raise ValueError(f"unknown action: {action!r}")

    manager = get_websocket_manager()
    try:
        await manager.send_notification_state(user_id, ids, action)
        count = get_notification_service().get_unread_count(
            db, user_id, is_admin=is_admin
        )
        await manager.send_unread_count(user_id, count)
    except Exception as e:
        logger.warning(f"notification fan-out failed for user {user_id}: {e}")
```

- [ ] **Step 4: Tests laufen lassen, Erfolg bestätigen**

Run: `cd backend && .venv/bin/pytest tests/api/test_notification_fanout.py -v`
Expected: PASS (3 Tests)

- [ ] **Step 5: Die sechs Routen anschließen**

In `backend/app/api/routes/notifications.py` den Import ergänzen:

```python
from app.api.routes._notification_fanout import fanout_state
```

Dann in jedem Handler **nach** dem Service-Aufruf und **vor** dem `return`:

`mark_notification_as_read` (nach der 404-Prüfung):
```python
    await fanout_state(
        db, current_user.id, [notification.id], "read",
        is_admin=is_privileged(current_user),
    )
```

`dismiss_notification` (nach der 404-Prüfung):
```python
    await fanout_state(
        db, current_user.id, [notification.id], "dismissed",
        is_admin=is_privileged(current_user),
    )
```

`snooze_notification` (nach der 404-Prüfung, Handler ab Zeile 234):
```python
    await fanout_state(
        db, current_user.id, [notification.id], "snoozed",
        is_admin=is_privileged(current_user),
    )
```

`delete_notification` (Handler ab Zeile 298; liefert 204, gibt den Datensatz
nicht zurück — die ID steht als Pfadparameter zur Verfügung):
```python
    await fanout_state(
        db, current_user.id, [notification_id], "deleted",
        is_admin=is_privileged(current_user),
    )
```

`mark_all_as_read` und `dismiss_all` liefern nur `count`, keine IDs. Eine
leere ID-Liste mit `action="read"` wäre aussagelos — der Empfänger wüsste
nicht, ob nichts passiert ist oder alles. Beide Sammelrouten bekommen deshalb
eine **eigene Aktion**, bei der die leere Liste genau das Richtige bedeutet:
„alles". `VALID_ACTIONS` in `_notification_fanout.py` um `"read_all"` und
`"dismissed_all"` erweitern und die Leerprüfung entsprechend anpassen:

```python
BULK_ACTIONS = frozenset({"read_all", "dismissed_all"})
VALID_ACTIONS = frozenset({"read", "dismissed", "snoozed", "deleted"}) | BULK_ACTIONS
```

```python
    if not ids and action not in BULK_ACTIONS:
        return
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

- [ ] **Step 6: Den Test für die Sammel-Aktionen nachziehen**

An `backend/tests/api/test_notification_fanout.py` anhängen:

```python
@pytest.mark.asyncio
async def test_bulk_action_sends_despite_empty_ids(ws_manager: MagicMock):
    db = MagicMock()
    service = MagicMock()
    service.get_unread_count.return_value = 0

    with patch(
        "app.api.routes._notification_fanout.get_websocket_manager",
        return_value=ws_manager,
    ), patch(
        "app.api.routes._notification_fanout.get_notification_service",
        return_value=service,
    ):
        await fanout_state(db, user_id=1, ids=[], action="read_all", is_admin=False)

    ws_manager.send_notification_state.assert_awaited_once_with(1, [], "read_all")
    ws_manager.send_unread_count.assert_awaited_once_with(1, 0)


@pytest.mark.asyncio
async def test_unknown_action_rejected(ws_manager: MagicMock):
    with pytest.raises(ValueError):
        await fanout_state(MagicMock(), 1, [7], "exploded", is_admin=False)
```

- [ ] **Step 7: Volle Testrunde**

Run: `cd backend && .venv/bin/pytest tests/api/test_notification_fanout.py tests/services/test_websocket_manager.py -v`
Expected: PASS (7 Tests)

Run: `cd backend && .venv/bin/pytest tests/api -k notification -q`
Expected: keine neuen Fehlschläge gegenüber dem Stand vor der Änderung

- [ ] **Step 8: Committen**

```bash
git add backend/app/api/routes/_notification_fanout.py backend/app/api/routes/notifications.py backend/tests/api/test_notification_fanout.py
git commit -m "feat(notifications): Zustandsaenderungen erreichen jetzt die offenen Clients

Lesen, Verwerfen, Snoozen und Loeschen verteilten bisher nichts: der
WebSocket-Manager wurde in notifications.py nur fuer connect/disconnect
benutzt, send_unread_count hatte ueberhaupt keinen Produktivaufrufer.
Wer auf dem Handy wegwischte, sah es in einer offenen Web-UI erst nach
dem Neuladen.

Der Fan-out sitzt in der Route-Ebene, weil die Service-Methoden synchron
sind. Ein gemeinsamer Helfer bedient alle sechs Routen, damit sie nicht
auseinanderlaufen, und schluckt Versandfehler: ein toter Socket darf aus
einem erfolgreichen POST kein 500 machen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: WS-Handler `mark_read` nutzt den Fan-out

**Files:**
- Modify: `backend/app/api/routes/notifications.py:641-655` (der `mark_read`-Zweig im WebSocket-Handler)
- Test: `backend/tests/api/test_notification_fanout.py`

**Interfaces:**
- Consumes: `fanout_state` (Task 2).
- Produces: nichts Neues.

**Warum:** Der Zweig antwortet heute mit `websocket.send_json(...)` nur der
auslösenden Verbindung. Markiert das Tray über den Socket als gelesen, erfährt
die Web-UI desselben Nutzers nichts.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

```python
@pytest.mark.asyncio
async def test_ws_mark_read_fans_out_to_all_connections():
    """The socket branch must not answer only the caller."""
    from app.services.websocket_manager import WebSocketManager

    manager = WebSocketManager()
    caller, other = MagicMock(), MagicMock()
    caller.send_json = AsyncMock()
    other.send_json = AsyncMock()
    await manager.connect(caller, user_id=1)
    await manager.connect(other, user_id=1)

    db = MagicMock()
    service = MagicMock()
    service.get_unread_count.return_value = 2

    with patch(
        "app.api.routes._notification_fanout.get_websocket_manager",
        return_value=manager,
    ), patch(
        "app.api.routes._notification_fanout.get_notification_service",
        return_value=service,
    ):
        await fanout_state(db, user_id=1, ids=[5], action="read", is_admin=False)

    types_seen = [c[0][0]["type"] for c in other.send_json.call_args_list]
    assert "notification_state" in types_seen
    assert "unread_count" in types_seen
```

- [ ] **Step 2: Test laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/api/test_notification_fanout.py::test_ws_mark_read_fans_out_to_all_connections -v`
Expected: PASS (der Helfer aus Task 2 leistet das bereits — dieser Test sichert
die Eigenschaft für die Socket-Seite ab)

- [ ] **Step 3: Den WS-Zweig umbauen**

In `backend/app/api/routes/notifications.py` den `mark_read`-Zweig ersetzen —
statt der Einzelantwort der gemeinsame Helfer:

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
Expected: PASS (8 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/app/api/routes/notifications.py backend/tests/api/test_notification_fanout.py
git commit -m "fix(notifications): mark_read ueber den Socket erreicht alle Verbindungen

Der Zweig antwortete nur der ausloesenden Verbindung. Markierte ein
Client ueber den Socket als gelesen, erfuhr die Web-UI desselben
Nutzers nichts davon.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Frontend zieht bei `notification_state` nach

**Files:**
- Modify: `client/src/hooks/useNotificationSocket.ts:16-22` (Options-Interface), `:110-135` (onmessage-Switch)
- Modify: `client/src/contexts/NotificationContext.tsx:42-64` (Hook-Optionen)
- Test: `client/src/__tests__/hooks/useNotificationSocket.test.tsx`

**Interfaces:**
- Consumes: das WS-Ereignis `notification_state` aus Task 1/2.
- Produces: Option `onNotificationState?: (ids: number[], action: string) => void`
  in `UseNotificationSocketOptions`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

An `client/src/__tests__/hooks/useNotificationSocket.test.tsx` anhängen — das
vorhandene Mock-Muster der Datei weiterverwenden:

```typescript
it('ruft onNotificationState bei einem notification_state-Frame', async () => {
  const onNotificationState = vi.fn();
  renderHook(() => useNotificationSocket({ onNotificationState }));

  await act(async () => {
    mockSocket.onmessage?.({
      data: JSON.stringify({
        type: 'notification_state',
        payload: { ids: [7, 8], action: 'read' },
      }),
    } as MessageEvent);
  });

  expect(onNotificationState).toHaveBeenCalledWith([7, 8], 'read');
});

it('ignoriert einen notification_state-Frame ohne Handler', async () => {
  renderHook(() => useNotificationSocket({}));

  await act(async () => {
    mockSocket.onmessage?.({
      data: JSON.stringify({
        type: 'notification_state',
        payload: { ids: [1], action: 'deleted' },
      }),
    } as MessageEvent);
  });
  // kein Wurf = bestanden
});
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd client && npm test -- useNotificationSocket`
Expected: FAIL — `onNotificationState` wird nicht aufgerufen

- [ ] **Step 3: Hook erweitern**

In `client/src/hooks/useNotificationSocket.ts` das Options-Interface ergänzen:

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

Destrukturierung und Ref analog zu `onNotification` ergänzen:

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

- [ ] **Step 4: Kontext nachziehen**

In `client/src/contexts/NotificationContext.tsx` die Hook-Optionen um den
Handler erweitern. Ein Zustandswechsel anderswo ist selten und betrifft die
ganze Liste — statt lokaler Teilmutation wird schlicht neu geladen:

```typescript
    onNotificationState: () => {
      // Ein anderes Geraet hat gelesen/verworfen/gesnoozt/geloescht.
      // Der Serverstand ist die Wahrheit, also neu laden statt raten.
      fetchNotifications();
    },
```

`fetchNotifications` ist bereits als `useCallback` definiert (Zeile 65) und
steht in der Abhängigkeitsliste des Hook-Aufrufs.

- [ ] **Step 5: Tests und Build laufen lassen**

Run: `cd client && npm test -- useNotificationSocket`
Expected: PASS

Run: `cd client && npx eslint src/hooks/useNotificationSocket.ts src/contexts/NotificationContext.tsx && npm run build`
Expected: exit 0, Build grün

- [ ] **Step 6: Committen**

```bash
git add client/src/hooks/useNotificationSocket.ts client/src/contexts/NotificationContext.tsx client/src/__tests__/hooks/useNotificationSocket.test.tsx
git commit -m "feat(notifications): Web-UI zieht bei Zustandsaenderungen anderer Geraete nach

Neuer WS-Ereignistyp notification_state. Der Kontext laedt darauf neu,
statt den Zustand lokal zu raten: der Serverstand ist die Wahrheit, und
ein Zustandswechsel anderswo ist selten genug fuer einen Refetch.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

**Ab hier ist Phase A lieferbar.** Web und Android profitieren, auch wenn Phase
B nie gebaut wird.

---

# Phase B — Das Tray

### Task 5: Modulgerüst und Token-Speicher

**Files:**
- Create: `backend/baluhost_tray/__init__.py`, `backend/baluhost_tray/config.py`
- Test: `backend/tests/tray/test_config.py`, `backend/tests/tray/__init__.py`

**Interfaces:**
- Consumes: `baluhost_tui.config` (Muster für Pfad und Rechte).
- Produces:
  - `@dataclass(frozen=True) class Tokens: access: str; refresh: str`
  - `def save_tokens(tokens: Tokens) -> None`
  - `def load_tokens() -> Tokens | None`
  - `def clear_tokens() -> None`
  - `TOKEN_FILE: Path` (`~/.baluhost/tray-tokens.json`)

**Warum eine eigene Datei statt `baluhost_tui.config`:** Dort hält
`save_token()` einen einzelnen String; der Device-Code-Flow liefert access
*und* refresh. Eine eigene Datei vermeidet, dass Tray und TUI sich gegenseitig
die Datei überschreiben.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_config.py`:

```python
"""Tests for the tray token store."""

import json
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
    loaded = tray_config.load_tokens()
    assert loaded == tray_config.Tokens(access="a", refresh="r")


def test_missing_file_is_none():
    assert tray_config.load_tokens() is None


def test_file_is_owner_only():
    tray_config.save_tokens(tray_config.Tokens(access="a", refresh="r"))
    mode = stat.S_IMODE(tray_config.TOKEN_FILE.stat().st_mode)
    assert mode == 0o600


def test_corrupt_file_is_none_not_crash():
    tray_config.TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    tray_config.TOKEN_FILE.write_text("{not json")
    assert tray_config.load_tokens() is None


def test_incomplete_file_is_none():
    tray_config.TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    tray_config.TOKEN_FILE.write_text(json.dumps({"access": "a"}))
    assert tray_config.load_tokens() is None


def test_clear_removes_file():
    tray_config.save_tokens(tray_config.Tokens(access="a", refresh="r"))
    tray_config.clear_tokens()
    assert not tray_config.TOKEN_FILE.exists()
    tray_config.clear_tokens()  # zweimal loeschen darf nicht werfen
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
from dataclasses import asdict, dataclass
from pathlib import Path

TOKEN_DIR = Path.home() / ".baluhost"
TOKEN_FILE = TOKEN_DIR / "tray-tokens.json"


@dataclass(frozen=True)
class Tokens:
    access: str
    refresh: str


def save_tokens(tokens: Tokens) -> None:
    """Write tokens with owner-only permissions."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(asdict(tokens)))
    TOKEN_FILE.chmod(0o600)


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
Expected: PASS (6 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray backend/tests/tray
git commit -m "feat(tray): Modulgeruest und Token-Speicher

Eigene Token-Datei statt der TUI-Datei: der Device-Code-Flow liefert
access und refresh, waehrend baluhost_tui.config einen einzelnen String
haelt. Zwei Programme auf derselben Datei wuerden sich ueberschreiben.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Zustandsableitung — die Farbe des Icons

**Files:**
- Create: `backend/baluhost_tray/state.py`
- Test: `backend/tests/tray/test_state.py`

**Interfaces:**
- Consumes: nichts.
- Produces:
  - `class IconState(str, Enum): OFFLINE = "offline"; OK = "ok"; WARNING = "warning"; CRITICAL = "critical"`
  - `@dataclass class TrayState` mit `connected: bool`, `unread: dict[int, str]`
    (Notification-ID → `notification_type`)
  - `def icon_state(self) -> IconState`
  - `def apply_snapshot(self, items: list[tuple[int, str]]) -> None`
  - `def add(self, notification_id: int, notification_type: str) -> None`
  - `def remove(self, ids: list[int]) -> None`
  - `def set_connected(self, connected: bool) -> None`

**Der ganze Sinn dieser Datei:** Sie ist die Logik ohne Qt. `tray.py` bleibt
dünn, damit hier getestet werden kann, was zählt.

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
        (False, [(1, "critical")], IconState.OFFLINE),  # offline schlaegt alles
        (True, [], IconState.OK),
        (True, [(1, "info")], IconState.OK),            # info faerbt nicht
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
    """Nach einer Offline-Phase ist der Snapshot die Wahrheit, nicht ein Merge."""
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "critical")])
    state.apply_snapshot([(2, "warning")])
    assert state.icon_state() == IconState.WARNING


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
        """Replace the whole set. The REST snapshot is the truth, not a merge."""
        self.unread = {nid: ntype for nid, ntype in items}

    def add(self, notification_id: int, notification_type: str) -> None:
        self.unread[notification_id] = notification_type

    def remove(self, ids: list[int]) -> None:
        for nid in ids:
            self.unread.pop(nid, None)

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
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_state.py -v`
Expected: PASS (13 Tests, davon 8 aus der Parametrisierung)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray/state.py backend/tests/tray/test_state.py
git commit -m "feat(tray): Zustandsableitung fuer die Icon-Farbe

Schlimmste ungelesene Schwere gewinnt, fehlende Verbindung schlaegt
alles. Ein unbekannter Typ faerbt bewusst nicht: ein neuer
NotificationType im Backend darf das Panel nicht auf rot raten.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Gaming-Endpunkt im steam_gaming-Plugin

**Files:**
- Modify: `backend/app/plugins/installed/steam_gaming/routes.py`
- Modify: `backend/app/plugins/installed/steam_gaming/models.py` (Antwortmodell)
- Test: `backend/tests/plugins/steam_gaming/test_session_state.py`

**Interfaces:**
- Consumes: `app.services.power.gaming_presence.gaming_mode_on_screen()`.
- Produces: `GET /api/plugins/steam_gaming/session-state` → `{"gaming_active": bool}`

**Zwei Fallen, die im Plan stehen müssen:**
1. **Kein `from __future__ import annotations`** in dieser Datei — hinter dem
   `@user_limiter.limit`-Wrapper werden Annotationen zu ForwardRefs, die
   FastAPI nicht auflöst, und jeder Request wird 422. Der Kommentar steht
   bereits oben in der Datei.
2. `gaming_mode_on_screen()` liest Marker-Datei und sysfs — blockierend, also
   über `asyncio.to_thread`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/plugins/steam_gaming/test_session_state.py`:

```python
"""Tests for the gaming session-state endpoint the tray gates on."""

from unittest.mock import patch

import pytest

from app.plugins.installed.steam_gaming import routes


@pytest.mark.asyncio
@pytest.mark.parametrize("on_screen,expected", [(True, True), (False, False)])
async def test_reports_gaming_presence(on_screen, expected):
    with patch(
        "app.services.power.gaming_presence.gaming_mode_on_screen",
        return_value=on_screen,
    ):
        result = await routes.session_state(request=None, response=None, current_user=None)
    assert result.gaming_active is expected


@pytest.mark.asyncio
async def test_unreadable_presence_counts_as_not_gaming():
    """Fail open: rather one notification too many than a swallowed alarm."""
    with patch(
        "app.services.power.gaming_presence.gaming_mode_on_screen",
        side_effect=OSError("sysfs gone"),
    ):
        result = await routes.session_state(request=None, response=None, current_user=None)
    assert result.gaming_active is False
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/plugins/steam_gaming/test_session_state.py -v`
Expected: FAIL mit `AttributeError: module ... has no attribute 'session_state'`

- [ ] **Step 3: Antwortmodell ergänzen**

In `backend/app/plugins/installed/steam_gaming/models.py`:

```python
class SessionStateResponse(BaseModel):
    """Whether a gaming session is on screen right now."""

    gaming_active: bool = Field(
        ..., description="Gaming mode marker set AND a display is lit"
    )
```

- [ ] **Step 4: Endpunkt implementieren**

In `backend/app/plugins/installed/steam_gaming/routes.py`, Import ergänzen:

```python
from app.plugins.installed.steam_gaming.models import SessionStateResponse
```

Und den Endpunkt:

```python
@router.get("/session-state", response_model=SessionStateResponse)
@user_limiter.limit(_READ_LIMIT)
async def session_state(
    request: Request,
    response: Response,
    current_user=Depends(deps.get_current_user),
) -> SessionStateResponse:
    """Whether a gaming session is on screen — the tray gates popups on this.

    Uses gaming_mode_on_screen() rather than the bare marker: an abandoned
    session leaves the marker behind, and a stale marker would mute the
    desktop indefinitely. Requiring a lit display is what clears that.

    Reads a marker file and sysfs, so it runs off the event loop. Any read
    error counts as "not gaming": rather one notification too many than a
    swallowed alarm.
    """
    from app.services.power import gaming_presence

    try:
        active = await asyncio.to_thread(gaming_presence.gaming_mode_on_screen)
    except Exception:
        active = False
    return SessionStateResponse(gaming_active=bool(active))
```

Sicherstellen, dass `from app.api import deps` in der Datei importiert ist.

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/plugins/steam_gaming/ -v`
Expected: PASS (3 neue Tests, bestehende unverändert)

- [ ] **Step 6: Committen**

```bash
git add backend/app/plugins/installed/steam_gaming/routes.py backend/app/plugins/installed/steam_gaming/models.py backend/tests/plugins/steam_gaming/test_session_state.py
git commit -m "feat(steam_gaming): session-state meldet laufende Gaming-Sitzung

Das Tray haelt Popups zurueck, solange gespielt wird. Grundlage ist
gaming_mode_on_screen() und nicht der blosse Marker: eine abgebrochene
Sitzung laesst den Marker liegen, und ein verwaister Marker wuerde den
Desktop dauerhaft stummschalten.

Lesefehler gelten als 'nicht im Gaming-Modus' — lieber eine Meldung zu
viel als eine verschluckte.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Gaming-Warteschlange in der Zustandslogik

**Files:**
- Modify: `backend/baluhost_tray/state.py`
- Test: `backend/tests/tray/test_state.py`

**Interfaces:**
- Consumes: `TrayState` (Task 6).
- Produces:
  - `@dataclass class PendingPopup: notification_id: int; title: str; message: str`
  - `class PopupQueue` mit
    `def hold(self, popup: PendingPopup) -> None`,
    `def release(self) -> list[PendingPopup]`,
    `def summary(self) -> tuple[str, str] | None`,
    `def is_empty(self) -> bool`
  - Konstante `SUMMARY_THRESHOLD = 4`

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
    """Popups held back while a game is on screen.

    Held, not dropped: when the session ends the user still gets told. A
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
        count = len(self._held)
        return (
            "BaluHost",
            f"{count} neue kritische Meldungen während der Spielsitzung",
        )
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_state.py -v`
Expected: PASS (18 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray/state.py backend/tests/tray/test_state.py
git commit -m "feat(tray): Warteschlange fuer Popups waehrend einer Spielsitzung

Zurueckhalten statt verwerfen: bei Sitzungsende wird zugestellt, ab vier
Eintraegen als Sammelmeldung. Eintraege sind nach ID verschluesselt,
damit ein Reconnect dieselbe Meldung nicht doppelt zustellt.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Gerätekopplung (Device-Code-Flow)

**Files:**
- Create: `backend/baluhost_tray/pairing.py`
- Test: `backend/tests/tray/test_pairing.py`

**Interfaces:**
- Consumes: `baluhost_tray.config.Tokens`, `save_tokens` (Task 5).
- Produces:
  - `@dataclass(frozen=True) class PendingPairing: device_code: str; user_code: str; verification_url: str; interval: int; expires_in: int`
  - `def start_pairing(client) -> PendingPairing`
  - `def poll_once(client, device_code: str) -> Tokens | None` —
    `None` bei `authorization_pending`, `Tokens` bei `approved`
  - `class PairingDenied(Exception)`, `class PairingExpired(Exception)`
  - `def device_identity() -> tuple[str, str]` — `(device_id, device_name)`

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


def test_start_pairing_returns_codes():
    client = _client({
        "device_code": "dc",
        "user_code": "123456",
        "verification_url": "https://baluhost.local/pair",
        "expires_in": 600,
        "interval": 5,
    })

    pending = pairing.start_pairing(client)

    assert pending.user_code == "123456"
    assert pending.interval == 5
    path = client.post.call_args[0][0]
    assert path.endswith("/desktop/device-code")
    body = client.post.call_args[1]["json"]
    assert body["platform"] == "linux"
    assert body["device_id"]
    assert body["device_name"]


def test_poll_pending_returns_none():
    client = _client({"status": "authorization_pending"})
    assert pairing.poll_once(client, "dc") is None


def test_poll_approved_returns_tokens():
    client = _client({
        "status": "approved",
        "access_token": "at",
        "refresh_token": "rt",
        "token_type": "bearer",
    })
    assert pairing.poll_once(client, "dc") == Tokens(access="at", refresh="rt")


def test_poll_denied_raises():
    client = _client({"status": "denied"})
    with pytest.raises(pairing.PairingDenied):
        pairing.poll_once(client, "dc")


def test_poll_expired_raises():
    client = _client({"status": "expired"})
    with pytest.raises(pairing.PairingExpired):
        pairing.poll_once(client, "dc")


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
the web UI, and the pairing can be revoked per device there.
"""

from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass
from pathlib import Path

from baluhost_tray.config import Tokens

_MACHINE_ID_PATHS = (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id"))


class PairingDenied(Exception):
    """The user rejected this device in the web UI."""


class PairingExpired(Exception):
    """The code timed out before anyone approved it."""


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
        "/api/desktop/device-code",
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
    """One poll. None means keep waiting."""
    response = client.post("/api/desktop/poll", json={"device_code": device_code})
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
    raise RuntimeError(f"unexpected pairing status: {status!r}")
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_pairing.py -v`
Expected: PASS (6 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray/pairing.py backend/tests/tray/test_pairing.py
git commit -m "feat(tray): Geraetekopplung ueber den vorhandenen Device-Code-Flow

Wiederverwendung des Flows aus desktop_pairing.py, der platform=linux
bereits kennt. Nichts abzutippen, pro Geraet widerrufbar.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: Sitzung, Token-Erneuerung und ws-Token

**Files:**
- Create: `backend/baluhost_tray/session.py`
- Test: `backend/tests/tray/test_session.py`

**Interfaces:**
- Consumes: `baluhost_tray.config` (Task 5), `baluhost_tui.client.BackendClient`.
- Produces:
  - `class PairingLost(Exception)`
  - `class Session` mit
    `def __init__(self, base_url: str)`,
    `def client(self) -> BackendClient`,
    `def refresh_access(self) -> None`,
    `def ws_token(self) -> str`,
    `def forget(self) -> None`

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_session.py`:

```python
"""Tests for token lifecycle in the tray session."""

from unittest.mock import MagicMock, patch

import pytest

from baluhost_tray import config as tray_config
from baluhost_tray.session import PairingLost, Session


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


def test_ws_token_returned():
    session = Session("http://localhost:8000")
    session._client = MagicMock()
    session._client.post.return_value = _response(200, {"token": "wt"})

    assert session.ws_token() == "wt"


def test_refresh_updates_stored_access_token():
    session = Session("http://localhost:8000")
    session._client = MagicMock()
    session._client.post.return_value = _response(
        200, {"access_token": "new", "refresh_token": "rt2"}
    )

    session.refresh_access()

    assert tray_config.load_tokens().access == "new"
    assert tray_config.load_tokens().refresh == "rt2"
    session._client.set_token.assert_called_with("new")


def test_refresh_failure_forgets_pairing():
    """A revoked device must stop hammering the backend."""
    session = Session("http://localhost:8000")
    session._client = MagicMock()
    session._client.post.return_value = _response(401)

    with pytest.raises(PairingLost):
        session.refresh_access()

    assert tray_config.load_tokens() is None


def test_forget_clears_tokens():
    session = Session("http://localhost:8000")
    session._client = MagicMock()
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

The ws token is short lived (60 s) and scoped to the notification socket, so
it is fetched fresh per connection attempt rather than cached.
"""

from __future__ import annotations

from baluhost_tray import config as tray_config
from baluhost_tui.client import BackendClient


class PairingLost(Exception):
    """The refresh token no longer works — the device must pair again."""


class Session:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url
        tokens = tray_config.load_tokens()
        self._client = BackendClient(base_url=base_url)
        if tokens:
            self._client.set_token(tokens.access)

    def client(self) -> BackendClient:
        return self._client

    def ws_token(self) -> str:
        """Short lived token for the notification websocket."""
        response = self._client.post("/api/notifications/ws-token")
        if response.status_code != 200:
            raise PairingLost(f"ws-token refused: {response.status_code}")
        return response.json()["token"]

    def refresh_access(self) -> None:
        """Exchange the refresh token for a fresh access token.

        On failure the local tokens are dropped: a device that was revoked in
        the web UI must stop retrying every few seconds against a backend
        that no longer knows it.
        """
        tokens = tray_config.load_tokens()
        if not tokens:
            raise PairingLost("no tokens stored")

        response = self._client.post(
            "/api/auth/refresh", json={"refresh_token": tokens.refresh}
        )
        if response.status_code != 200:
            self.forget()
            raise PairingLost(f"refresh refused: {response.status_code}")

        data = response.json()
        new_tokens = tray_config.Tokens(
            access=data["access_token"],
            refresh=data.get("refresh_token", tokens.refresh),
        )
        tray_config.save_tokens(new_tokens)
        self._client.set_token(new_tokens.access)

    def forget(self) -> None:
        tray_config.clear_tokens()
        self._client.clear_token()
```

**Prüfen vor dem Implementieren:** Pfad und Rumpf des Refresh-Endpunkts in
`backend/app/api/routes/auth.py` gegenlesen und hier angleichen —
`RefreshTokenRequest` wurde in der Audit-Remediation als Pydantic-Modell
eingeführt, der Feldname muss übereinstimmen.

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_session.py -v`
Expected: PASS (4 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray/session.py backend/tests/tray/test_session.py
git commit -m "feat(tray): Sitzung mit Token-Erneuerung und ws-Token

Das ws-Token ist 60 s gueltig und wird deshalb pro Verbindungsaufbau
frisch geholt statt zwischengespeichert. Scheitert die Erneuerung,
werden die lokalen Token verworfen: ein widerrufenes Geraet darf nicht
im Sekundentakt gegen ein Backend laufen, das es nicht mehr kennt.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: WebSocket-Beobachter mit Backoff und Snapshot-Reihenfolge

**Files:**
- Create: `backend/baluhost_tray/watch.py`
- Test: `backend/tests/tray/test_watch.py`

**Interfaces:**
- Consumes: `Session` (Task 10), `TrayState` (Task 6).
- Produces:
  - `def backoff_delays(attempts: int, base: float = 1.0, cap: float = 60.0) -> list[float]`
  - `class Watcher` mit
    `def __init__(self, session: Session, state: TrayState)`,
    `def load_snapshot(self) -> None`,
    `def handle_frame(self, frame: dict) -> list[PendingPopup]`,
    `def buffer_frame(self, frame: dict) -> None`,
    `def drain_buffer(self) -> list[PendingPopup]`

**Der Kern dieser Datei ist Reihenfolge.** Erst REST-Snapshot, dann gepufferte
WS-Frames. Andersherum meldet der Socket „gelesen" für eine Meldung, die der
Snapshot gleich darauf wieder als ungelesen bringt, und das Icon springt
zurück auf rot.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_watch.py`:

```python
"""Tests for the tray's websocket watcher — ordering and backoff."""

from unittest.mock import MagicMock

import pytest

from baluhost_tray.state import IconState, TrayState
from baluhost_tray.watch import Watcher, backoff_delays


def test_backoff_grows_and_caps():
    delays = backoff_delays(8, base=1.0, cap=60.0)
    assert delays[0] >= 1.0
    assert all(b >= a for a, b in zip(delays, delays[1:]))
    assert max(delays) <= 60.0


def test_backoff_has_jitter():
    """Zwei Laeufe duerfen nicht identisch sein, sonst schlagen alle Clients
    nach einem Neustart gleichzeitig auf."""
    assert backoff_delays(8) != backoff_delays(8)


def _watcher(unread: list[dict]) -> tuple[Watcher, TrayState]:
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"notifications": unread, "unread_count": len(unread)}
    session.client.return_value.get.return_value = response
    state = TrayState()
    state.set_connected(True)
    return Watcher(session, state), state


def test_snapshot_fills_state():
    watcher, state = _watcher([
        {"id": 1, "notification_type": "critical", "is_read": False,
         "title": "RAID", "message": "degradiert"},
    ])
    watcher.load_snapshot()
    assert state.icon_state() == IconState.CRITICAL


def test_buffered_frames_apply_after_snapshot_not_before():
    """Die eigentliche Rennbedingung: 'gelesen' vor dem Snapshot darf nicht
    vom Snapshot wieder ueberschrieben werden."""
    watcher, state = _watcher([
        {"id": 1, "notification_type": "critical", "is_read": False,
         "title": "RAID", "message": "degradiert"},
    ])
    watcher.buffer_frame({
        "type": "notification_state",
        "payload": {"ids": [1], "action": "read"},
    })
    watcher.load_snapshot()
    watcher.drain_buffer()
    assert state.icon_state() == IconState.OK


def test_new_critical_frame_yields_popup():
    watcher, state = _watcher([])
    popups = watcher.handle_frame({
        "type": "notification",
        "payload": {"id": 5, "notification_type": "critical",
                    "title": "SMART", "message": "Platte meldet Fehler"},
    })
    assert [p.notification_id for p in popups] == [5]
    assert state.icon_state() == IconState.CRITICAL


def test_warning_frame_colours_without_popup():
    watcher, state = _watcher([])
    popups = watcher.handle_frame({
        "type": "notification",
        "payload": {"id": 6, "notification_type": "warning",
                    "title": "Backup", "message": "uebersprungen"},
    })
    assert popups == []
    assert state.icon_state() == IconState.WARNING


def test_unknown_frame_type_ignored():
    watcher, _ = _watcher([])
    assert watcher.handle_frame({"type": "pong", "payload": {}}) == []
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_watch.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray.watch'`

- [ ] **Step 3: Minimal implementieren**

`backend/baluhost_tray/watch.py`:

```python
"""Websocket watcher: keeps TrayState in step with the backend.

Ordering matters more than anything else in here. After an offline phase the
REST snapshot is the truth and frames that arrived meanwhile are applied on
top of it — never the other way round, or the socket's "read" gets undone by
a snapshot that still lists the notification as unread and the icon jumps
back to red.
"""

from __future__ import annotations

import random

from baluhost_tray.state import PendingPopup, TrayState

POPUP_TYPES = frozenset({"critical"})
COLOURING_TYPES = frozenset({"critical", "warning"})


def backoff_delays(attempts: int, base: float = 1.0, cap: float = 60.0) -> list[float]:
    """Exponential backoff with jitter, capped.

    The jitter is not decoration: without it every client that dropped when
    the backend restarted comes back at the same instant.
    """
    delays = []
    for attempt in range(attempts):
        raw = min(cap, base * (2 ** attempt))
        delays.append(round(raw * random.uniform(0.5, 1.0), 3))
    return delays


class Watcher:
    def __init__(self, session, state: TrayState) -> None:
        self._session = session
        self._state = state
        self._buffer: list[dict] = []

    def load_snapshot(self) -> None:
        """Replace state from REST. Called on start and after every reconnect."""
        response = self._session.client().get(
            "/api/notifications", params={"page_size": 100}
        )
        if response.status_code != 200:
            return
        items = []
        for raw in response.json().get("notifications", []):
            if raw.get("is_read"):
                continue
            items.append((int(raw["id"]), str(raw.get("notification_type", ""))))
        self._state.apply_snapshot(items)

    def buffer_frame(self, frame: dict) -> None:
        """Hold a frame that arrived before the snapshot was in place."""
        self._buffer.append(frame)

    def drain_buffer(self) -> list[PendingPopup]:
        """Apply buffered frames on top of the snapshot, oldest first."""
        popups: list[PendingPopup] = []
        buffered, self._buffer = self._buffer, []
        for frame in buffered:
            popups.extend(self.handle_frame(frame))
        return popups

    def handle_frame(self, frame: dict) -> list[PendingPopup]:
        """Apply one frame. Returns popups that should be shown."""
        kind = frame.get("type")
        payload = frame.get("payload") or {}

        if kind == "notification":
            ntype = str(payload.get("notification_type", ""))
            nid = int(payload.get("id", 0))
            if ntype in COLOURING_TYPES:
                self._state.add(nid, ntype)
            if ntype in POPUP_TYPES:
                return [PendingPopup(
                    notification_id=nid,
                    title=str(payload.get("title", "BaluHost")),
                    message=str(payload.get("message", "")),
                )]
            return []

        if kind == "notification_state":
            action = payload.get("action")
            ids = [int(i) for i in payload.get("ids", [])]
            if action in ("read_all", "dismissed_all"):
                self._state.apply_snapshot([])
            else:
                self._state.remove(ids)
            return []

        return []
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_watch.py -v`
Expected: PASS (8 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray/watch.py backend/tests/tray/test_watch.py
git commit -m "feat(tray): WebSocket-Beobachter mit Backoff und Snapshot-Reihenfolge

Nach einer Offline-Phase ist der REST-Snapshot die Wahrheit; zwischen-
zeitlich eingetroffene Frames werden darauf angewendet, nicht umgekehrt.
Sonst macht der Snapshot ein 'gelesen' vom Socket wieder rueckgaengig
und das Icon springt zurueck auf rot.

Der Jitter im Backoff ist keine Zierde: ohne ihn kommen nach einem
Backend-Neustart alle Clients im selben Moment zurueck.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 12: Desktop-Meldungen über D-Bus

**Files:**
- Create: `backend/baluhost_tray/notify.py`
- Test: `backend/tests/tray/test_notify.py`

**Interfaces:**
- Consumes: `dbus-next` (bereits deklarierte Abhängigkeit), `PendingPopup` (Task 8).
- Produces:
  - `class Notifier` mit `async def connect(self) -> None`,
    `async def show(self, popup: PendingPopup) -> int`,
    `async def show_summary(self, title: str, message: str) -> int`
  - `class NotifierUnavailable(Exception)`

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
    assert "RAID" in args
    assert "degradiert" in args


@pytest.mark.asyncio
async def test_show_without_connection_raises():
    with pytest.raises(NotifierUnavailable):
        await Notifier().show(
            PendingPopup(notification_id=1, title="x", message="y")
        )


@pytest.mark.asyncio
async def test_summary_is_sent_as_one_message():
    notifier = Notifier()
    notifier._iface = _stub_interface()
    await notifier.show_summary("BaluHost", "4 neue kritische Meldungen")
    assert notifier._iface.call_notify.await_count == 1
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

    async def connect(self) -> None:
        """Attach to the session bus. Raises NotifierUnavailable if there is none."""
        try:
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
        """Show the collapsed form used after a gaming session."""
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
Expected: PASS (3 Tests)

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

### Task 13: Icon-Material

**Files:**
- Create: `backend/baluhost_tray/icons/baluhost-tray-{ok,warning,critical,offline}-{22,24,32,48}.png`
- Create: `backend/baluhost_tray/icons/README.md`
- Test: `backend/tests/tray/test_icons.py`

**Interfaces:**
- Consumes: `client/src-tauri/icons/icon.png` (1024²) als Quelle.
- Produces: `def icon_path(state: IconState, size: int = 22) -> Path` in
  `backend/baluhost_tray/icons/__init__.py`

**Handarbeit, kein Konvertierungsschritt.** Das 1,2-MB-SVG ist ein
nachgezeichnetes Bitmap; die PNGs tragen das dunkle Hintergrundquadrat. Zu tun:
Quadrat entfernen, Katze freistellen, in vier Größen rendern, für `warning` und
`critical` einen Punkt unten rechts einsetzen (Durchmesser etwa ein Drittel der
Kantenlänge), für `offline` entsättigen.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_icons.py`:

```python
"""The icon set must be complete — a missing file means an invisible tray."""

import pytest

from baluhost_tray.icons import icon_path
from baluhost_tray.state import IconState

SIZES = (22, 24, 32, 48)


@pytest.mark.parametrize("state", list(IconState))
@pytest.mark.parametrize("size", SIZES)
def test_icon_exists_for_every_state_and_size(state: IconState, size: int):
    path = icon_path(state, size)
    assert path.exists(), f"fehlt: {path}"
    assert path.stat().st_size > 0


def test_unknown_size_falls_back_to_22():
    assert icon_path(IconState.OK, 17) == icon_path(IconState.OK, 22)
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_icons.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray.icons'`

- [ ] **Step 3: Icons erzeugen**

Die freigestellte Basis einmalig herstellen (ImageMagick ist auf der Box
vorhanden; andernfalls von Hand in einem Bildeditor):

```bash
cd backend/baluhost_tray/icons
# Hintergrundquadrat entfernen: die Eckfarbe als transparent ausschneiden
magick ../../../client/src-tauri/icons/icon.png \
  -fuzz 12% -fill none -draw "alpha 0,0 floodfill" base-1024.png

for s in 22 24 32 48; do
  magick base-1024.png -resize ${s}x${s} baluhost-tray-ok-${s}.png
  magick baluhost-tray-ok-${s}.png -colorspace Gray -alpha on \
    baluhost-tray-offline-${s}.png
  # Badge: Punkt unten rechts, Durchmesser etwa ein Drittel der Kantenlaenge
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
```

- [ ] **Step 4: Nachschlagefunktion implementieren**

`backend/baluhost_tray/icons/__init__.py`:

```python
"""Icon lookup for the tray."""

from __future__ import annotations

from pathlib import Path

from baluhost_tray.state import IconState

_DIR = Path(__file__).parent
_SIZES = (22, 24, 32, 48)
_DEFAULT_SIZE = 22


def icon_path(state: IconState, size: int = _DEFAULT_SIZE) -> Path:
    """Path to the icon file for this state, falling back to 22 px."""
    if size not in _SIZES:
        size = _DEFAULT_SIZE
    return _DIR / f"baluhost-tray-{state.value}-{size}.png"
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_icons.py -v`
Expected: PASS (17 Tests)

- [ ] **Step 6: Committen**

```bash
git add backend/baluhost_tray/icons backend/tests/tray/test_icons.py
git commit -m "feat(tray): Icon-Material in vier Zustaenden und vier Groessen

Aus dem 1024er-PNG abgeleitet und freigestellt; das 1,2-MB-SVG ist ein
nachgezeichnetes Bitmap und als Quelle unbrauchbar. Der Zustand steckt
im Badge unten rechts, nicht in der Faerbung der Katze -- eine rote
Katze liest sich als anderes Logo, nicht als Alarm.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 14: Einzelinstanz-Sperre

**Files:**
- Create: `backend/baluhost_tray/single_instance.py`
- Test: `backend/tests/tray/test_single_instance.py`

**Interfaces:**
- Consumes: nichts.
- Produces: `class AlreadyRunning(Exception)`,
  `def acquire(name: str = "baluhost-tray") -> object` (gibt das offene
  File-Objekt zurück, das gehalten werden muss)

**Warum `$XDG_RUNTIME_DIR` und nicht `/tmp`:** sitzungsgebunden und beim
Abmelden weg. Die Lock-Datei wird **nicht** vor dem Öffnen gelöscht — genau das
erzeugt das Rennen, in dem zwei Prozesse je eine eigene Inode sperren und beide
sich für den einzigen halten.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_single_instance.py`:

```python
"""One tray per session."""

import pytest

from baluhost_tray import single_instance


@pytest.fixture(autouse=True)
def runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return tmp_path


def test_first_acquire_succeeds():
    handle = single_instance.acquire("test-tray")
    assert handle is not None


def test_second_acquire_refused():
    single_instance.acquire("test-tray")
    with pytest.raises(single_instance.AlreadyRunning):
        single_instance.acquire("test-tray")


def test_lock_file_lands_in_runtime_dir(runtime_dir):
    single_instance.acquire("test-tray")
    assert (runtime_dir / "test-tray.lock").exists()


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
    """Another tray already holds the lock in this session."""


_handles: list = []


def _lock_dir() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime)
    return Path.home() / ".baluhost"


def acquire(name: str = "baluhost-tray") -> object:
    """Take the session lock. Keep the returned handle alive for the process."""
    directory = _lock_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.lock"

    handle = open(path, "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise AlreadyRunning(f"another tray holds {path}") from exc

    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    _handles.append(handle)  # keep the fd open for the process lifetime
    return handle
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_single_instance.py -v`
Expected: PASS (4 Tests)

- [ ] **Step 5: Committen**

```bash
git add backend/baluhost_tray/single_instance.py backend/tests/tray/test_single_instance.py
git commit -m "feat(tray): Einzelinstanz-Sperre in XDG_RUNTIME_DIR

Sitzungsgebunden statt /tmp. Die Datei wird vor dem Oeffnen nicht
geloescht: genau das erzeugt das Rennen, in dem zwei Prozesse je eine
eigene Inode sperren und beide sich fuer den einzigen halten.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 15: Qt-Oberfläche und Einstiegspunkt

**Files:**
- Create: `backend/baluhost_tray/tray.py`, `backend/baluhost_tray/main.py`, `backend/baluhost_tray/__main__.py`
- Modify: `backend/pyproject.toml` (`[project.optional-dependencies]`, `[project.scripts]`)
- Test: `backend/tests/tray/test_main_wiring.py`

**Interfaces:**
- Consumes: alle vorherigen Tasks.
- Produces: Konsolenskript `baluhost-tray`, Extra `tray`.

**`tray.py` bleibt bewusst dünn** — nur Darstellung, keine Entscheidungen. Alles
Prüfbare liegt in `state.py` und `watch.py`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_main_wiring.py`:

```python
"""The entry point must fail politely, never with a traceback."""

from unittest.mock import patch

import pytest

from baluhost_tray import main as tray_main
from baluhost_tray.single_instance import AlreadyRunning


def test_second_instance_exits_cleanly(capsys):
    with patch("baluhost_tray.main.single_instance.acquire",
               side_effect=AlreadyRunning("held")):
        code = tray_main.run(argv=[])
    assert code == 0
    assert "läuft bereits" in capsys.readouterr().out


def test_missing_pairing_points_at_pair_command(capsys):
    with patch("baluhost_tray.main.single_instance.acquire"), \
         patch("baluhost_tray.main.tray_config.load_tokens", return_value=None):
        code = tray_main.run(argv=[])
    assert code == 2
    assert "--pair" in capsys.readouterr().out


def test_no_session_bus_exits_with_hint(capsys):
    from baluhost_tray.notify import NotifierUnavailable

    with patch("baluhost_tray.main.single_instance.acquire"), \
         patch("baluhost_tray.main.tray_config.load_tokens",
               return_value=object()), \
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

Every failure here is a message, never a traceback: this runs from a systemd
user unit where a stack trace ends up in the journal and nowhere the user
looks.
"""

from __future__ import annotations

import argparse
import sys

from baluhost_tray import config as tray_config
from baluhost_tray import single_instance
from baluhost_tray.notify import NotifierUnavailable

DEFAULT_BASE_URL = "http://localhost:8000"


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

    try:
        single_instance.acquire()
    except single_instance.AlreadyRunning:
        print("BaluHost Tray läuft bereits in dieser Sitzung.")
        return 0

    if args.pair:
        return run_pairing(args.base_url)

    if tray_config.load_tokens() is None:
        print("Nicht gekoppelt. Einmalig ausführen: baluhost-tray --pair")
        return 2

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

`backend/baluhost_tray/tray.py` — dünn halten, keine Logik:

```python
"""Qt surface. Rendering only — every decision lives in state.py / watch.py."""

from __future__ import annotations

import asyncio
import threading

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from baluhost_tray.icons import icon_path
from baluhost_tray.state import IconState, PopupQueue, TrayState

MENU_OPEN = "BaluHost öffnen"
MENU_QUIET = "Eine Stunde stumm"
MENU_QUIT = "Beenden"


def run_tray(base_url: str) -> int:
    """Start the Qt loop with the asyncio work on a worker thread."""
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)

    state = TrayState()
    queue = PopupQueue()
    icon = QSystemTrayIcon(QIcon(str(icon_path(IconState.OFFLINE))))
    icon.setToolTip("BaluHost")

    menu = QMenu()
    menu.addAction(MENU_OPEN)
    menu.addAction(MENU_QUIET)
    menu.addSeparator()
    quit_action = menu.addAction(MENU_QUIT)
    quit_action.triggered.connect(app.quit)
    icon.setContextMenu(menu)
    icon.show()

    worker = threading.Thread(
        target=lambda: asyncio.run(_pump(base_url, state, queue, icon)),
        daemon=True,
    )
    worker.start()
    return app.exec()


async def _pump(base_url, state, queue, icon) -> None:
    """Placeholder loop wired in the follow-up task — see plan Task 16."""
    raise NotImplementedError


def run_pairing_flow(base_url: str) -> int:
    """Console pairing: print the code, poll until approved."""
    import time

    from baluhost_tray import pairing
    from baluhost_tray.config import save_tokens
    from baluhost_tui.client import BackendClient

    client = BackendClient(base_url=base_url)
    pending = pairing.start_pairing(client)
    print(f"Code: {pending.user_code}")
    print(f"Freigeben unter: {pending.verification_url}")

    deadline = time.monotonic() + pending.expires_in
    while time.monotonic() < deadline:
        tokens = pairing.poll_once(client, pending.device_code)
        if tokens:
            save_tokens(tokens)
            print("Gekoppelt.")
            return 0
        time.sleep(pending.interval)

    print("Code abgelaufen — bitte erneut versuchen.")
    return 4
```

- [ ] **Step 5: Paketierung eintragen**

In `backend/pyproject.toml` unter `[project.optional-dependencies]`:

```toml
tray = [
  "PyQt6>=6.6.0,<7.0.0",
  "websockets>=12.0,<16.0"
]
```

Unter `[project.scripts]` ergänzen:

```toml
baluhost-tray = "baluhost_tray.main:cli"
```

- [ ] **Step 6: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/ -v`
Expected: PASS (alle Tray-Tests; `test_main_wiring.py` läuft ohne PyQt6, weil
der Qt-Import in `start_qt_app` gekapselt ist)

- [ ] **Step 7: Committen**

```bash
git add backend/baluhost_tray/tray.py backend/baluhost_tray/main.py backend/baluhost_tray/__main__.py backend/pyproject.toml backend/tests/tray/test_main_wiring.py
git commit -m "feat(tray): Qt-Oberflaeche, Einstiegspunkt und Paketierung

tray.py bleibt duenn: nur Darstellung, jede Entscheidung liegt in
state.py und watch.py. Der Qt-Import ist in start_qt_app gekapselt,
damit --pair und die Tests ohne PyQt6 laufen.

Jeder Fehlerfall im Einstiegspunkt ist eine Meldung, kein Traceback --
das Ding laeuft aus einer systemd-user-Unit, wo ein Stacktrace im
Journal landet und nirgends, wo jemand hinschaut.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 16: Die Schleife — alles zusammenschalten

**Files:**
- Modify: `backend/baluhost_tray/tray.py` (`_pump`)
- Create: `backend/baluhost_tray/loop.py`
- Test: `backend/tests/tray/test_loop.py`

**Interfaces:**
- Consumes: `Session`, `Watcher`, `Notifier`, `TrayState`, `PopupQueue`.
- Produces: `async def deliver(popups, queue, notifier, gaming_active: bool) -> None`

**Hier sitzt das Gaming-Gate**, und es wird nur gefragt, wenn es darauf ankommt:
vor einem Popup, und danach alle 30 Sekunden, solange die Warteschlange nicht
leer ist. Im Normalbetrieb gar nicht.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_loop.py`:

```python
"""Tests for delivery and the gaming gate."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from baluhost_tray.loop import deliver, is_gaming_active
from baluhost_tray.state import PendingPopup, PopupQueue


def _popup(n: int) -> PendingPopup:
    return PendingPopup(notification_id=n, title=f"T{n}", message=f"M{n}")


@pytest.mark.asyncio
async def test_delivers_when_not_gaming():
    notifier = MagicMock()
    notifier.show = AsyncMock()
    queue = PopupQueue()

    await deliver([_popup(1)], queue, notifier, gaming_active=False)

    notifier.show.assert_awaited_once()
    assert queue.is_empty()


@pytest.mark.asyncio
async def test_holds_while_gaming():
    notifier = MagicMock()
    notifier.show = AsyncMock()
    queue = PopupQueue()

    await deliver([_popup(1)], queue, notifier, gaming_active=True)

    notifier.show.assert_not_awaited()
    assert not queue.is_empty()


@pytest.mark.asyncio
async def test_release_collapses_above_threshold():
    notifier = MagicMock()
    notifier.show = AsyncMock()
    notifier.show_summary = AsyncMock()
    queue = PopupQueue()

    await deliver([_popup(n) for n in (1, 2, 3, 4)], queue, notifier,
                  gaming_active=True)
    await deliver([], queue, notifier, gaming_active=False)

    notifier.show_summary.assert_awaited_once()
    notifier.show.assert_not_awaited()


@pytest.mark.asyncio
async def test_release_shows_each_below_threshold():
    notifier = MagicMock()
    notifier.show = AsyncMock()
    notifier.show_summary = AsyncMock()
    queue = PopupQueue()

    await deliver([_popup(1), _popup(2)], queue, notifier, gaming_active=True)
    await deliver([], queue, notifier, gaming_active=False)

    assert notifier.show.await_count == 2
    notifier.show_summary.assert_not_awaited()


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

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_loop.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray.loop'`

- [ ] **Step 3: Minimal implementieren**

`backend/baluhost_tray/loop.py`:

```python
"""Delivery and the gaming gate."""

from __future__ import annotations

import logging

from baluhost_tray.state import PendingPopup, PopupQueue

logger = logging.getLogger(__name__)

GAMING_PATH = "/api/plugins/steam_gaming/session-state"


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
    except Exception as e:
        logger.debug(f"gaming probe failed, treating as not gaming: {e}")
        return False


async def deliver(
    popups: list[PendingPopup],
    queue: PopupQueue,
    notifier,
    gaming_active: bool,
) -> None:
    """Show popups, or hold them while a game is on screen.

    Held, never dropped. When the session ends everything held goes out; a
    burst is collapsed into one line.
    """
    if gaming_active:
        for popup in popups:
            queue.hold(popup)
        return

    if not queue.is_empty():
        summary = queue.summary()
        released = queue.release()
        if summary:
            await notifier.show_summary(*summary)
        else:
            for popup in released:
                await notifier.show(popup)

    for popup in popups:
        await notifier.show(popup)
```

- [ ] **Step 4: `_pump` in `tray.py` ersetzen**

```python
async def _pump(base_url, state, queue, icon) -> None:
    """Connect, keep state current, deliver popups.

    Order after every (re)connect: REST snapshot first, then the frames that
    arrived meanwhile. The other way round the socket's "read" gets undone by
    a snapshot that still lists the notification as unread.
    """
    import asyncio

    from baluhost_tray.loop import deliver, is_gaming_active
    from baluhost_tray.notify import Notifier
    from baluhost_tray.session import PairingLost, Session
    from baluhost_tray.watch import Watcher, backoff_delays

    notifier = Notifier()
    await notifier.connect()

    session = Session(base_url)
    watcher = Watcher(session, state)
    attempt = 0

    while True:
        try:
            watcher.load_snapshot()
            state.set_connected(True)
            _refresh_icon(icon, state)
            attempt = 0

            for popup in watcher.drain_buffer():
                await deliver([popup], queue, notifier,
                              is_gaming_active(session.client()))

            await _consume_socket(session, watcher, state, queue, notifier, icon)
        except PairingLost:
            state.set_connected(False)
            _refresh_icon(icon, state)
            return
        except Exception as e:
            logger.warning(f"tray loop lost the backend: {e}")

        state.set_connected(False)
        _refresh_icon(icon, state)
        delays = backoff_delays(attempt + 1)
        await asyncio.sleep(delays[-1])
        attempt = min(attempt + 1, 7)


def _refresh_icon(icon, state) -> None:
    icon.setIcon(QIcon(str(icon_path(state.icon_state()))))
```

Dazu `_consume_socket` in derselben Datei:

```python
async def _consume_socket(session, watcher, state, queue, notifier, icon) -> None:
    """Read frames until the socket closes. Returning means: reconnect.

    The ws token is fetched here, per attempt, because it only lives 60
    seconds — caching it would just produce a stale one after every outage.
    """
    import json

    import websockets

    ws_url = session.ws_url() + f"?token={session.ws_token()}"
    async with websockets.connect(ws_url) as socket:
        async for raw in socket:
            try:
                frame = json.loads(raw)
            except ValueError:
                continue

            popups = watcher.handle_frame(frame)
            if popups:
                await deliver(
                    popups, queue, notifier, is_gaming_active(session.client())
                )
            elif not queue.is_empty():
                # Nur solange etwas wartet, wird weiter nachgefragt.
                await deliver([], queue, notifier, is_gaming_active(session.client()))
            _refresh_icon(icon, state)
```

Oben in `tray.py` ergänzen: `import logging` und `logger = logging.getLogger(__name__)`.

`Session` braucht dafür eine Methode `ws_url()` — in `backend/baluhost_tray/session.py`
ergänzen:

```python
    def ws_url(self) -> str:
        """Websocket URL derived from the base URL (http→ws, https→wss)."""
        scheme = "wss" if self._base_url.startswith("https") else "ws"
        host = self._base_url.split("://", 1)[-1].rstrip("/")
        return f"{scheme}://{host}/api/notifications/ws"
```

Und der zugehörige Test in `backend/tests/tray/test_session.py`:

```python
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
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/ -v`
Expected: PASS (alle Tray-Tests)

Run: `cd backend && .venv/bin/ruff check baluhost_tray/`
Expected: keine Befunde

- [ ] **Step 6: Committen**

```bash
git add backend/baluhost_tray/loop.py backend/baluhost_tray/tray.py backend/tests/tray/test_loop.py
git commit -m "feat(tray): Zustellung, Gaming-Gate und die Hauptschleife

Das Gate wird nur gefragt, wenn es darauf ankommt: vor einem Popup und
danach periodisch, solange die Warteschlange nicht leer ist. Im
Normalbetrieb gar nicht.

Alles ausser einem klaren Ja gilt als 'nicht im Gaming-Modus' -- das
Plugin ist abschaltbar, dann fehlt die Route schlicht.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 17: Verbindungsmeldungen und Menü-Aktionen

**Files:**
- Create: `backend/baluhost_tray/announce.py`
- Modify: `backend/baluhost_tray/tray.py` (Menü-Handler), `backend/baluhost_tray/loop.py` (Aufruf)
- Test: `backend/tests/tray/test_announce.py`

**Interfaces:**
- Consumes: `Notifier` (Task 12), `PopupQueue` (Task 8).
- Produces:
  - `class ConnectionAnnouncer` mit
    `def went_offline(self, now: float) -> tuple[str, str] | None`,
    `def came_online(self, now: float) -> tuple[str, str] | None`
  - `class QuietMode` mit `def mute_for(self, seconds: float, now: float) -> None`,
    `def is_muted(self, now: float) -> bool`
  - Konstante `RECONNECT_ANNOUNCE_AFTER = 120.0`

**Warum eigene Klassen:** Die Spec verlangt „**eine** Meldung, danach Stille"
und eine Rückmeldung nur nach längerer Unterbrechung. Beides ist Zustand über
die Zeit, also genau das, was in eine testbare Einheit gehört statt verstreut
in die Schleife.

**Stummschaltung nutzt denselben Weg wie das Gaming-Gate.** `deliver()` bekommt
keinen neuen Parameter; die Schleife übergibt
`gaming_active or quiet.is_muted(now)`. Der Parameter bedeutet fachlich
„jetzt zurückhalten" — dass es zwei Gründe dafür gibt, muss `deliver` nicht
wissen, und zurückgehaltene Meldungen kommen in beiden Fällen später an.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/tray/test_announce.py`:

```python
"""Connection announcements and quiet mode."""

from baluhost_tray.announce import RECONNECT_ANNOUNCE_AFTER, ConnectionAnnouncer, QuietMode


def test_offline_announced_once():
    announcer = ConnectionAnnouncer()
    first = announcer.went_offline(now=100.0)
    second = announcer.went_offline(now=160.0)
    assert first is not None
    assert second is None, "kein Piepen im Minutentakt"


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
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_announce.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'baluhost_tray.announce'`

- [ ] **Step 3: Minimal implementieren**

`backend/baluhost_tray/announce.py`:

```python
"""When to speak about the connection, and when to stay quiet.

Both are state over time, which is why they live here as small testable
units rather than as flags scattered through the main loop.
"""

from __future__ import annotations

RECONNECT_ANNOUNCE_AFTER = 120.0


class ConnectionAnnouncer:
    """Says "gone" once, and "back" only after a real outage.

    A backend that flaps must not produce a stream of popups: the outage is
    announced on the first detection and then never again until the
    connection actually returned.
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
        if since is None:
            return None
        if now - since < self._reconnect_after:
            return None
        return ("BaluHost", "Verbindung wiederhergestellt")


class QuietMode:
    """Hold popups until a deadline, set from the tray menu."""

    def __init__(self) -> None:
        self._until = 0.0

    def mute_for(self, seconds: float, now: float) -> None:
        self._until = now + seconds

    def is_muted(self, now: float) -> bool:
        return now < self._until
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_announce.py -v`
Expected: PASS (7 Tests)

- [ ] **Step 5: In die Schleife einhängen**

In `backend/baluhost_tray/tray.py` in `_pump` einen `ConnectionAnnouncer` und
eine `QuietMode` anlegen und an den Stellen benutzen, an denen bisher nur das
Icon gewechselt wurde:

```python
    from baluhost_tray.announce import ConnectionAnnouncer, QuietMode

    announcer = ConnectionAnnouncer()
    quiet = QuietMode()
```

Nach einem erfolgreichen `load_snapshot()`:

```python
            back = announcer.came_online(time.monotonic())
            if back:
                await notifier.show_summary(*back)
```

Im Fehlerzweig, bevor der Backoff greift:

```python
        gone = announcer.went_offline(time.monotonic())
        if gone:
            try:
                await notifier.show_summary(*gone)
            except NotifierUnavailable:
                pass
```

Und überall dort, wo `is_gaming_active(...)` an `deliver` übergeben wird,
stattdessen:

```python
                hold = is_gaming_active(session.client()) or quiet.is_muted(
                    time.monotonic()
                )
```

`import time` und `from baluhost_tray.notify import NotifierUnavailable` oben
ergänzen. `quiet` muss von den Menü-Handlern erreichbar sein — dazu wird es in
`run_tray` erzeugt und an `_pump` übergeben statt darin angelegt.

- [ ] **Step 6: Menü-Aktionen verdrahten**

In `run_tray` die beiden bisher wirkungslosen Einträge anschließen:

```python
    quiet_action = menu.addAction(MENU_QUIET)
    quiet_action.triggered.connect(
        lambda: quiet.mute_for(3600.0, time.monotonic())
    )

    open_action = menu.addAction(MENU_OPEN)
    open_action.triggered.connect(
        lambda: QDesktopServices.openUrl(QUrl(base_url))
    )
```

Importe ergänzen: `from PyQt6.QtCore import QUrl` und
`from PyQt6.QtGui import QDesktopServices`. Die Reihenfolge der `addAction`-Aufrufe
so anpassen, dass „BaluHost öffnen" oben steht.

Der Menüpunkt „letzte Meldungen" aus der Spec entfällt in v1 bewusst: Ein Klick
darauf müsste eine Liste rendern, was `tray.py` von reiner Darstellung zu einer
kleinen Anwendung machen würde. Ein Klick auf das Icon öffnet stattdessen die
Web-UI, die diese Liste bereits hat. Das ist im Spec-Abschnitt „Nicht-Ziele"
nachzutragen.

- [ ] **Step 7: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/ -v`
Expected: PASS

- [ ] **Step 8: Committen**

```bash
git add backend/baluhost_tray/announce.py backend/baluhost_tray/tray.py backend/tests/tray/test_announce.py
git commit -m "feat(tray): Verbindungsmeldungen und Menue-Aktionen

Eine Meldung beim Verbindungsverlust, danach Ruhe; eine Rueckmeldung nur
nach mehr als zwei Minuten Unterbrechung. Ein flatterndes Backend darf
keinen Popup-Strom erzeugen.

Die Stummschaltung nutzt denselben Weg wie das Gaming-Gate: deliver()
bekommt keinen zweiten Parameter, die Schleife uebergibt 'jetzt
zurueckhalten'. Zurueckgehaltenes kommt in beiden Faellen spaeter an.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 18: Autostart und Installation

**Files:**
- Create: `deploy/install/templates/baluhost-tray.service`
- Modify: `deploy/install/modules/10-systemd-services.sh`
- Create: `docs/features/desktop-tray.md`
- Test: manuelle Abnahme (unten), plus `backend/tests/tray/test_unit_template.py`

**Interfaces:**
- Consumes: Konsolenskript `baluhost-tray` (Task 15).
- Produces: `baluhost-tray.service` als systemd-`--user`-Unit.

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

[Service]
Type=simple
ExecStart=__INSTALL_DIR__/backend/.venv/bin/baluhost-tray
Restart=on-failure
RestartSec=10s
# Kein root, keine Rechteerweiterung: das Tray liest nur.
NoNewPrivileges=yes

[Install]
WantedBy=graphical-session.target
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/tray/test_unit_template.py -v`
Expected: PASS (4 Tests)

- [ ] **Step 5: Installationsschritt ergänzen**

In `deploy/install/modules/10-systemd-services.sh` ans Ende anfügen. Anders als
die übrigen Units geht diese nach `~/.config/systemd/user/`, nicht nach
`/etc/systemd/system/` — und ohne `sudo`:

```bash
install_tray_user_unit() {
    local target_user="${SERVICE_USER:-$SUDO_USER}"
    if [ -z "$target_user" ]; then
        log_warn "Kein Zielbenutzer bekannt — Tray-Unit uebersprungen"
        return 0
    fi

    local user_home
    user_home="$(getent passwd "$target_user" | cut -d: -f6)"
    local unit_dir="$user_home/.config/systemd/user"

    install -d -o "$target_user" -g "$target_user" "$unit_dir"
    sed "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
        "$TEMPLATE_DIR/baluhost-tray.service" \
        > "$unit_dir/baluhost-tray.service"
    chown "$target_user:$target_user" "$unit_dir/baluhost-tray.service"

    # Ohne laufende Sitzung greift systemctl --user nicht; das ist kein Fehler.
    if sudo -u "$target_user" XDG_RUNTIME_DIR="/run/user/$(id -u "$target_user")" \
        systemctl --user daemon-reload 2>/dev/null; then
        sudo -u "$target_user" XDG_RUNTIME_DIR="/run/user/$(id -u "$target_user")" \
            systemctl --user enable baluhost-tray.service
        log_info "Tray-Unit installiert und aktiviert"
    else
        log_info "Tray-Unit abgelegt — beim naechsten Login aktiv"
    fi
}
```

Den Aufruf `install_tray_user_unit` an der Stelle einhängen, an der das Modul
die übrigen Units abschließt. **Namen gegenlesen:** `SERVICE_USER`,
`INSTALL_DIR`, `TEMPLATE_DIR`, `log_info` und `log_warn` müssen zu den im Modul
tatsächlich verwendeten passen — vor dem Schreiben die vorhandenen Funktionen
in `10-systemd-services.sh` ansehen und angleichen.

- [ ] **Step 6: Dokumentation schreiben**

`docs/features/desktop-tray.md` mit: Was das Tray zeigt (vier Zustände),
Kopplung über `baluhost-tray --pair`, Verhalten beim Spielen, wo die Token
liegen (`~/.baluhost/tray-tokens.json`, `0600`), und wie man die Kopplung in
der Web-UI widerruft.

- [ ] **Step 7: Manuelle Abnahme auf dem Zielrechner**

Kein CI-Ersatz — diese Schritte muss ein Mensch sehen:

1. `systemctl --user start baluhost-tray` → Icon erscheint im Panel.
2. Backend stoppen → Icon wird grau, **eine** Meldung, danach Ruhe.
3. Backend starten → Icon wird grün, Meldung nur bei längerer Unterbrechung.
4. Kritische Testmeldung erzeugen → rotes Icon plus Popup.
5. Dieselbe Meldung **auf dem Handy** wegwischen → Icon wird ohne Zutun grün.
6. Spiel im Vollbild starten, Testmeldung erzeugen → kein Popup, Icon rot.
7. Spiel beenden → zurückgehaltene Meldung wird zugestellt.
8. Zweites `baluhost-tray` starten → beendet sich mit Hinweis.

- [ ] **Step 8: Committen**

```bash
git add deploy/install/templates/baluhost-tray.service deploy/install/modules/10-systemd-services.sh docs/features/desktop-tray.md backend/tests/tray/test_unit_template.py
git commit -m "feat(tray): Autostart als systemd-user-Unit und Installationsschritt

Bewusst eine User-Unit an graphical-session.target: das Tray gehoert zur
Desktop-Sitzung, nicht zum Systemstart, und braucht kein root.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Abschluss

- [ ] **Volle Testrunde**

Run: `cd backend && .venv/bin/pytest tests/tray tests/api/test_notification_fanout.py tests/services/test_websocket_manager.py tests/plugins/steam_gaming -v`
Run: `cd backend && .venv/bin/ruff check baluhost_tray/ app/api/routes/_notification_fanout.py`
Run: `cd client && npm test -- useNotificationSocket && npm run build`

- [ ] **Branch abschließen**

REQUIRED SUB-SKILL: `superpowers:finishing-a-development-branch`
