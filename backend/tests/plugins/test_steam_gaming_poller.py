"""Steam session poller: detect -> book -> announce (Teilprojekt 3+4/4)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.steam_session import SteamSession
from app.plugins.installed.steam_gaming import ledger
from app.plugins.installed.steam_gaming.poller import SteamSessionPoller

T0 = datetime(2026, 7, 24, 20, 0, 0, tzinfo=timezone.utc)


def _poller(db_session, app_ids, times):
    """A poller whose detector and clock walk the given sequences."""
    detected = iter(app_ids)
    clock_values = iter(times)
    emit = AsyncMock()
    poller = SteamSessionPoller(
        detect=MagicMock(side_effect=lambda *a, **k: next(detected)),
        resolve=MagicMock(side_effect=lambda app_id: f"Game {app_id}"),
        emit=emit,
        session_factory=lambda: db_session,
        clock=lambda: next(clock_values),
    )
    return poller, emit


class TestTick:
    async def test_start_is_booked_and_announced(self, db_session):
        poller, emit = _poller(db_session, ["111"], [T0])

        await poller.tick()

        assert db_session.query(SteamSession).count() == 1
        emit.assert_awaited_once()
        args, kwargs = emit.await_args
        assert args[:2] == ("steam_gaming", ledger.EVENT_STARTED)
        assert kwargs["entity_id"] == "111"
        assert kwargs["game"] == "Game 111"

    async def test_end_is_announced_on_the_game_that_ended(self, db_session):
        poller, emit = _poller(
            db_session, ["111", None], [T0, T0 + timedelta(seconds=30)]
        )
        await poller.tick()
        emit.reset_mock()

        await poller.tick()

        emit.assert_awaited_once()
        args, kwargs = emit.await_args
        assert args[:2] == ("steam_gaming", ledger.EVENT_ENDED)
        assert kwargs["entity_id"] == "111"

    async def test_direct_switch_announces_both_edges(self, db_session):
        """#462 - TP3 swallowed this."""
        poller, emit = _poller(
            db_session, ["111", "222"], [T0, T0 + timedelta(seconds=30)]
        )
        await poller.tick()
        emit.reset_mock()

        await poller.tick()

        assert emit.await_count == 2
        first, second = emit.await_args_list
        assert first.args[:2] == ("steam_gaming", ledger.EVENT_ENDED)
        assert first.kwargs["entity_id"] == "111"
        assert second.args[:2] == ("steam_gaming", ledger.EVENT_STARTED)
        assert second.kwargs["entity_id"] == "222"

    async def test_same_game_announces_nothing(self, db_session):
        poller, emit = _poller(
            db_session, ["111", "111"], [T0, T0 + timedelta(seconds=30)]
        )
        await poller.tick()
        emit.reset_mock()

        await poller.tick()

        emit.assert_not_awaited()

    async def test_a_restart_mid_session_announces_nothing(self, db_session):
        """The DB holds the state, so a fresh poller object just picks it up."""
        first, _ = _poller(db_session, ["111"], [T0])
        await first.tick()

        second, emit = _poller(db_session, ["111"], [T0 + timedelta(minutes=5)])
        await second.tick()

        emit.assert_not_awaited()
        assert db_session.query(SteamSession).count() == 1


class TestRetentionSchedule:
    async def test_cleanup_runs_on_the_first_tick(self, db_session, monkeypatch):
        calls = []
        monkeypatch.setattr(
            ledger, "cleanup_old_sessions", lambda db, *, now: calls.append(now) or 0
        )
        poller, _ = _poller(db_session, [None], [T0])

        await poller.tick()

        assert calls == [T0]

    async def test_cleanup_does_not_run_again_the_next_tick(self, db_session, monkeypatch):
        calls = []
        monkeypatch.setattr(
            ledger, "cleanup_old_sessions", lambda db, *, now: calls.append(now) or 0
        )
        poller, _ = _poller(db_session, [None, None], [T0, T0 + timedelta(hours=1)])

        await poller.tick()
        await poller.tick()

        assert calls == [T0]

    async def test_cleanup_runs_again_after_a_day(self, db_session, monkeypatch):
        calls = []
        monkeypatch.setattr(
            ledger, "cleanup_old_sessions", lambda db, *, now: calls.append(now) or 0
        )
        later = T0 + timedelta(hours=25)
        poller, _ = _poller(db_session, [None, None], [T0, later])

        await poller.tick()
        await poller.tick()

        assert calls == [T0, later]


class TestSessionLifetime:
    """The DB session belongs to ONE tick. Hoisting it into __init__ would keep
    a transaction open for hours and hand PostgreSQL a stale connection after
    pool_recycle - and every other test in this file would stay green."""

    async def test_each_tick_opens_and_closes_its_own_session(self, db_session):
        opened: list[MagicMock] = []

        def _factory():
            handle = MagicMock(wraps=db_session)
            handle.close = MagicMock()
            opened.append(handle)
            return handle

        clock_values = iter([T0, T0 + timedelta(seconds=30)])
        poller = SteamSessionPoller(
            detect=MagicMock(return_value=None),
            resolve=MagicMock(return_value=None),
            emit=AsyncMock(),
            session_factory=_factory,
            clock=lambda: next(clock_values),
        )

        await poller.tick()
        await poller.tick()

        assert len(opened) == 2, "each tick must open its own session"
        for handle in opened:
            handle.close.assert_called_once()
