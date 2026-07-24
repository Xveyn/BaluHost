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
