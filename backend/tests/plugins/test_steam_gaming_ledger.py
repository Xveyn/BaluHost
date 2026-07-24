"""Steam session ledger: persisted play sessions (Teilprojekt 4/4)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
