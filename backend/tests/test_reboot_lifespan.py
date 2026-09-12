"""Boot-Übergabe des geplanten Neustarts.

Die Tests laufen DIREKT gegen die Lifespan-Funktionen, nicht über den
TestClient: `conftest` setzt SKIP_APP_INIT=1, `_startup()` läuft in Tests nie,
und ein TestClient-Test wäre grün, ohne dass die Verdrahtung existiert.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core import lifespan as lifespan_mod
from app.services.power.reboot_state import (
    PHASE_EXECUTING, PHASE_IDLE, get_state, to_utc,
)

SUNDAY_0400 = datetime(2026, 9, 13, 4, 0)


@pytest.fixture(autouse=True)
def _patch_session_local(db_session, monkeypatch):
    """Bridge ``SessionLocal`` to the test DB for lifespan's own DB access.

    `_emit_lifecycle_startup()`/`_emit_lifecycle_shutdown()` run outside any
    request — there is no dependency injection to override, so they open
    their own `SessionLocal()`. Left unpatched, that would talk to the
    production engine while `_mark_executing()` below writes into
    `db_session`'s private in-memory engine, and the lifespan code would
    never see the `executing` phase. Same bridge as
    `tests/api/test_power_routes.py::_patch_session_local`.
    """
    from sqlalchemy.orm import sessionmaker
    test_engine = db_session.get_bind()
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr("app.core.database.SessionLocal", TestSessionLocal)


def _mark_executing(db, *, entered_minutes_ago=1, woke=False):
    state = get_state(db)
    state.phase = PHASE_EXECUTING
    state.due_at = to_utc(SUNDAY_0400)
    state.woke_for_reboot = woke
    state.phase_entered_at = datetime.now(timezone.utc) - timedelta(
        minutes=entered_minutes_ago
    )
    db.commit()


@pytest.mark.asyncio
async def test_startup_sends_reboot_completed_instead_of_generic(db_session, monkeypatch):
    _mark_executing(db_session)
    monkeypatch.setattr(lifespan_mod, "IS_PRIMARY_WORKER", True, raising=False)

    generic = AsyncMock()
    specific = AsyncMock()
    with patch("app.services.notifications.events.emit_system_startup", new=generic), \
         patch("app.services.notifications.events.emit_reboot_completed", new=specific):
        await lifespan_mod._emit_lifecycle_startup()

    generic.assert_not_awaited()
    specific.assert_awaited_once()


@pytest.mark.asyncio
async def test_startup_sends_the_generic_message_without_a_planned_reboot(
    db_session, monkeypatch
):
    monkeypatch.setattr(lifespan_mod, "IS_PRIMARY_WORKER", True, raising=False)
    generic = AsyncMock()
    specific = AsyncMock()
    with patch("app.services.notifications.events.emit_system_startup", new=generic), \
         patch("app.services.notifications.events.emit_reboot_completed", new=specific):
        await lifespan_mod._emit_lifecycle_startup()

    generic.assert_awaited_once()
    specific.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_executing_sends_skipped_and_leaves_the_box_awake(
    db_session, monkeypatch
):
    _mark_executing(db_session, entered_minutes_ago=300, woke=True)
    monkeypatch.setattr(lifespan_mod, "IS_PRIMARY_WORKER", True, raising=False)

    skipped = AsyncMock()
    with patch("app.services.notifications.events.emit_system_startup", new=AsyncMock()), \
         patch("app.services.notifications.events.emit_reboot_completed", new=AsyncMock()), \
         patch("app.services.notifications.events.emit_reboot_skipped", new=skipped):
        await lifespan_mod._emit_lifecycle_startup()

    skipped.assert_awaited_once()
    assert get_state(db_session).phase == PHASE_IDLE


@pytest.mark.asyncio
async def test_shutdown_push_is_suppressed_during_a_planned_reboot(
    db_session, monkeypatch
):
    """Der Automat hat `reboot_started` schon gesendet — zwei Meldungen wären
    genau die Verwirrung, die das Feature vermeiden soll."""
    _mark_executing(db_session)
    monkeypatch.setattr(lifespan_mod, "IS_PRIMARY_WORKER", True, raising=False)

    generic = AsyncMock()
    with patch("app.services.notifications.events.emit_system_shutdown", new=generic):
        await lifespan_mod._emit_lifecycle_shutdown(trigger="signal")

    generic.assert_not_awaited()


@pytest.mark.asyncio
async def test_shutdown_still_writes_its_lifecycle_row(db_session, monkeypatch):
    """Die Zeile bleibt — aus ihr berechnet der nächste Start die Downtime."""
    from app.models.system_lifecycle import SystemLifecycleEvent

    _mark_executing(db_session)
    monkeypatch.setattr(lifespan_mod, "IS_PRIMARY_WORKER", True, raising=False)

    with patch("app.services.notifications.events.emit_system_shutdown", new=AsyncMock()):
        await lifespan_mod._emit_lifecycle_shutdown(trigger="signal")

    rows = db_session.query(SystemLifecycleEvent).filter(
        SystemLifecycleEvent.event_type == "shutdown"
    ).all()
    assert len(rows) == 1
