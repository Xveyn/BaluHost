"""Steam session ledger: persisted play sessions (Teilprojekt 4/4)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.models.steam_session import SteamSession

T0 = datetime(2026, 7, 24, 20, 0, 0, tzinfo=timezone.utc)


class TestModel:
    def test_open_session_round_trips(self, db_session):
        db_session.add(SteamSession(
            app_id="1449560",
            game_name="Metro Exodus Enhanced Edition",
            started_at=T0,
            last_seen_at=T0,
        ))
        db_session.commit()

        row = db_session.query(SteamSession).one()
        assert row.app_id == "1449560"
        assert row.game_name == "Metro Exodus Enhanced Edition"
        assert row.ended_at is None

    def test_game_name_is_optional(self, db_session):
        db_session.add(SteamSession(
            app_id="999", game_name=None, started_at=T0, last_seen_at=T0,
        ))
        db_session.commit()

        assert db_session.query(SteamSession).one().game_name is None

    def test_ended_session_stores_its_end(self, db_session):
        end = T0 + timedelta(hours=1)
        db_session.add(SteamSession(
            app_id="1", started_at=T0, last_seen_at=end, ended_at=end,
        ))
        db_session.commit()

        assert db_session.query(SteamSession).one().ended_at is not None


from app.plugins.installed.steam_gaming import ledger


def _names(app_id: str):
    """Stand-in for names.resolve_name()."""
    return {"111": "Metro", "222": "Cyberpunk"}.get(app_id)


def _record(db, app_id, now):
    return ledger.record(db, app_id, now=now, resolve_name=_names)


class TestLiveEdges:
    def test_nothing_open_and_nothing_running_books_nothing(self, db_session):
        events = _record(db_session, None, T0)

        assert events == []
        assert db_session.query(SteamSession).count() == 0

    def test_game_appears_opens_a_session_and_announces_it(self, db_session):
        events = _record(db_session, "111", T0)

        row = db_session.query(SteamSession).one()
        assert row.app_id == "111"
        assert row.game_name == "Metro"
        assert row.started_at is not None
        assert row.ended_at is None
        assert [(e.event_id, e.app_id, e.game) for e in events] == [
            (ledger.EVENT_STARTED, "111", "Metro")
        ]

    def test_same_game_next_tick_only_moves_the_heartbeat(self, db_session):
        _record(db_session, "111", T0)
        events = _record(db_session, "111", T0 + timedelta(seconds=30))

        row = db_session.query(SteamSession).one()
        assert events == []
        assert ledger.as_utc(row.last_seen_at) == T0 + timedelta(seconds=30)
        assert row.ended_at is None

    def test_game_disappears_closes_at_now_and_announces_the_end(self, db_session):
        _record(db_session, "111", T0)
        end = T0 + timedelta(seconds=30)
        events = _record(db_session, None, end)

        row = db_session.query(SteamSession).one()
        assert ledger.as_utc(row.ended_at) == end
        assert [(e.event_id, e.app_id, e.game) for e in events] == [
            (ledger.EVENT_ENDED, "111", "Metro")
        ]

    def test_direct_switch_closes_x_opens_y_and_announces_both(self, db_session):
        """#462: X->Y without a pause was swallowed in TP3."""
        _record(db_session, "111", T0)
        switch = T0 + timedelta(seconds=30)
        events = _record(db_session, "222", switch)

        rows = db_session.query(SteamSession).order_by(SteamSession.started_at).all()
        assert len(rows) == 2
        assert ledger.as_utc(rows[0].ended_at) == switch
        assert rows[1].app_id == "222" and rows[1].ended_at is None
        assert [(e.event_id, e.app_id, e.game) for e in events] == [
            (ledger.EVENT_ENDED, "111", "Metro"),
            (ledger.EVENT_STARTED, "222", "Cyberpunk"),
        ]

    def test_unresolved_name_falls_back_to_the_app_id_in_the_event(self, db_session):
        events = _record(db_session, "999", T0)

        assert db_session.query(SteamSession).one().game_name is None
        assert events[0].game == "999"


class TestGapRules:
    def test_stale_end_is_booked_at_the_last_heartbeat(self, db_session):
        """The process was away: `now` would book the outage as playtime."""
        _record(db_session, "111", T0)
        _record(db_session, "111", T0 + timedelta(seconds=30))  # last heartbeat

        _record(db_session, None, T0 + timedelta(hours=2))

        row = db_session.query(SteamSession).one()
        assert ledger.as_utc(row.ended_at) == T0 + timedelta(seconds=30)

    def test_stale_end_is_not_announced(self, db_session):
        """A deploy must not push 'session ended' for a game that ended hours ago."""
        _record(db_session, "111", T0)

        events = _record(db_session, None, T0 + timedelta(hours=2))

        assert events == []

    def test_stale_switch_books_both_but_announces_nothing(self, db_session):
        _record(db_session, "111", T0)

        events = _record(db_session, "222", T0 + timedelta(hours=2))

        rows = db_session.query(SteamSession).order_by(SteamSession.started_at).all()
        assert len(rows) == 2
        assert ledger.as_utc(rows[0].ended_at) == T0
        assert rows[1].app_id == "222" and rows[1].ended_at is None
        assert events == []

    def test_same_game_across_a_short_gap_continues_the_session(self, db_session):
        """A deploy mid-game is the normal case on this box."""
        _record(db_session, "111", T0)
        resumed = T0 + timedelta(minutes=5)

        events = _record(db_session, "111", resumed)

        row = db_session.query(SteamSession).one()
        assert ledger.as_utc(row.started_at) == T0
        assert ledger.as_utc(row.last_seen_at) == resumed
        assert row.ended_at is None
        assert events == []

    def test_same_game_across_a_long_gap_splits_into_two_sessions(self, db_session):
        """Off overnight and restarted in the morning is not a 14h session."""
        _record(db_session, "111", T0)
        next_day = T0 + timedelta(hours=14)

        events = _record(db_session, "111", next_day)

        rows = db_session.query(SteamSession).order_by(SteamSession.started_at).all()
        assert len(rows) == 2
        assert ledger.as_utc(rows[0].ended_at) == T0
        assert ledger.as_utc(rows[1].started_at) == next_day
        assert rows[1].ended_at is None
        assert events == []

    def test_the_adopt_window_boundary_still_continues(self, db_session):
        _record(db_session, "111", T0)

        _record(db_session, "111", T0 + timedelta(seconds=ledger.ADOPT_WINDOW_SECONDS))

        assert db_session.query(SteamSession).count() == 1

    def test_after_a_split_the_newest_open_session_is_the_one_that_continues(self, db_session):
        """Third tick after a split: the query must pick the NEW session, not
        the closed one and not the older row."""
        _record(db_session, "111", T0)
        split = T0 + timedelta(hours=14)
        _record(db_session, "111", split)          # splits: old closed, new opened

        _record(db_session, "111", split + timedelta(seconds=30))

        rows = db_session.query(SteamSession).order_by(SteamSession.started_at).all()
        assert len(rows) == 2
        assert ledger.as_utc(rows[0].ended_at) == T0
        assert rows[1].ended_at is None
        assert ledger.as_utc(rows[1].last_seen_at) == split + timedelta(seconds=30)


class TestStaleBoundary:
    def test_a_gap_of_exactly_the_stale_window_still_counts_as_live(self, db_session):
        _record(db_session, "111", T0)
        end = T0 + timedelta(seconds=ledger.STALE_AFTER_SECONDS)

        events = _record(db_session, None, end)

        row = db_session.query(SteamSession).one()
        assert ledger.as_utc(row.ended_at) == end
        assert [e.event_id for e in events] == [ledger.EVENT_ENDED]

    def test_one_second_past_the_stale_window_books_silently(self, db_session):
        """The two-minute deploy during which the game ended - the common case."""
        _record(db_session, "111", T0)

        events = _record(db_session, None, T0 + timedelta(seconds=ledger.STALE_AFTER_SECONDS + 1))

        row = db_session.query(SteamSession).one()
        assert ledger.as_utc(row.ended_at) == T0
        assert events == []


class TestConstants:
    def test_the_windows_are_the_values_the_design_fixed(self):
        """Two poll intervals, and ten minutes - changing either changes
        behaviour that the rest of this file only pins relative to itself."""
        assert (ledger.STALE_AFTER_SECONDS, ledger.ADOPT_WINDOW_SECONDS) == (60.0, 600.0)

    def test_the_event_ids_are_the_wire_format_they_must_stay(self):
        """These strings are persisted as plugin:steam_gaming:<id> in
        notifications and routing preferences - renaming the constant is free,
        renaming the value orphans existing rows."""
        assert (ledger.EVENT_STARTED, ledger.EVENT_ENDED) == (
            "session_started",
            "session_ended",
        )


class TestFailureContract:
    """record() must never raise at its caller - the poller has to survive."""

    def test_database_failure_rolls_back_and_returns_no_events(self, db_session):
        from sqlalchemy.exc import OperationalError

        broken = MagicMock(wraps=db_session)
        broken.commit.side_effect = OperationalError("stmt", {}, Exception("gone"))

        events = ledger.record(broken, "111", now=T0, resolve_name=_names)

        assert events == []
        broken.rollback.assert_called_once()

    def test_unexpected_failure_also_rolls_back_and_returns_no_events(self, db_session):
        """A throwing resolve_name() must not take the poller down either."""
        broken = MagicMock(wraps=db_session)
        broken.commit.side_effect = RuntimeError("boom")

        events = ledger.record(broken, "111", now=T0, resolve_name=_names)

        assert events == []
        broken.rollback.assert_called_once()


class TestHousekeeping:
    def test_orphaned_open_sessions_are_closed_silently(self, db_session):
        """The invariant says one open session; a crash can still leave more."""
        db_session.add_all([
            SteamSession(app_id="111", started_at=T0, last_seen_at=T0),
            SteamSession(
                app_id="222",
                started_at=T0 + timedelta(hours=1),
                last_seen_at=T0 + timedelta(hours=1),
            ),
        ])
        db_session.commit()

        events = _record(db_session, "222", T0 + timedelta(hours=1, seconds=30))

        older = db_session.query(SteamSession).filter_by(app_id="111").one()
        newer = db_session.query(SteamSession).filter_by(app_id="222").one()
        assert ledger.as_utc(older.ended_at) == T0
        assert newer.ended_at is None
        assert events == []

    def test_missing_game_name_is_resolved_on_a_later_heartbeat(self, db_session):
        """A game started during its own install has no appmanifest yet."""
        ledger.record(db_session, "111", now=T0, resolve_name=lambda _app_id: None)
        assert db_session.query(SteamSession).one().game_name is None

        _record(db_session, "111", T0 + timedelta(seconds=30))

        assert db_session.query(SteamSession).one().game_name == "Metro"

    def test_a_resolved_name_is_not_overwritten(self, db_session):
        _record(db_session, "111", T0)

        ledger.record(
            db_session, "111", now=T0 + timedelta(seconds=30), resolve_name=lambda _a: None
        )

        assert db_session.query(SteamSession).one().game_name == "Metro"


class TestDuration:
    def test_closed_session_duration(self, db_session):
        session = SteamSession(
            app_id="111",
            started_at=T0,
            last_seen_at=T0 + timedelta(minutes=90),
            ended_at=T0 + timedelta(minutes=90),
        )

        assert ledger.duration_seconds(session, T0 + timedelta(hours=5)) == 5400.0

    def test_open_session_counts_up_to_now(self, db_session):
        session = SteamSession(app_id="111", started_at=T0, last_seen_at=T0)

        assert ledger.duration_seconds(session, T0 + timedelta(minutes=12)) == 720.0

    def test_clock_stepping_backwards_clamps_at_zero(self, db_session):
        """An NTP step backwards must not produce a negative duration."""
        session = SteamSession(app_id="111", started_at=T0, last_seen_at=T0)

        assert ledger.duration_seconds(session, T0 - timedelta(minutes=5)) == 0.0


class TestRetention:
    def test_deletes_sessions_older_than_the_retention_window(self, db_session):
        old_start = T0 - timedelta(days=400)
        db_session.add(SteamSession(
            app_id="111",
            started_at=old_start,
            last_seen_at=old_start + timedelta(hours=1),
            ended_at=old_start + timedelta(hours=1),
        ))
        db_session.commit()

        deleted = ledger.cleanup_old_sessions(db_session, now=T0)

        assert deleted == 1
        assert db_session.query(SteamSession).count() == 0

    def test_keeps_sessions_inside_the_window(self, db_session):
        recent = T0 - timedelta(days=364)
        db_session.add(SteamSession(
            app_id="111", started_at=recent, last_seen_at=recent, ended_at=recent,
        ))
        db_session.commit()

        deleted = ledger.cleanup_old_sessions(db_session, now=T0)

        assert deleted == 0
        assert db_session.query(SteamSession).count() == 1

    def test_never_deletes_an_open_session(self, db_session):
        """An open session has no ended_at - however old, it is the current one."""
        ancient = T0 - timedelta(days=500)
        db_session.add(SteamSession(app_id="111", started_at=ancient, last_seen_at=ancient))
        db_session.commit()

        deleted = ledger.cleanup_old_sessions(db_session, now=T0)

        assert deleted == 0
        assert db_session.query(SteamSession).count() == 1
