"""Steam gaming dashboard panel: spec, formatting, empty state (TP 4/4)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.steam_session import SteamSession
from app.plugins.installed.steam_gaming import SteamGamingPlugin

T0 = datetime(2026, 7, 24, 20, 0, 0, tzinfo=timezone.utc)


class TestPanelSpec:
    def test_panel_is_an_admin_only_status_panel(self):
        spec = SteamGamingPlugin().get_dashboard_panel()

        assert spec is not None
        assert spec.panel_type == "status"
        assert spec.title == "Steam Gaming"
        assert spec.icon == "gamepad-2"
        assert spec.admin_only is True


class TestPanelData:
    async def test_no_sessions_means_no_panel(self, db_session):
        assert await SteamGamingPlugin().get_dashboard_data(db_session) is None

    async def test_running_session_shows_bare_duration_and_ok_tone(self, db_session):
        db_session.add(SteamSession(app_id="111", game_name="Metro", started_at=T0, last_seen_at=T0))
        db_session.commit()

        data = await SteamGamingPlugin().get_dashboard_data(db_session)

        item = data["items"][0]
        assert item["label"] == "Metro"
        assert item["tone"] == "ok"
        assert item["value"].endswith("m")
        assert "·" not in item["value"]

    async def test_finished_session_shows_date_and_duration(self, db_session):
        db_session.add(SteamSession(
            app_id="222",
            game_name="Cyberpunk",
            started_at=T0,
            last_seen_at=T0 + timedelta(hours=3, minutes=4),
            ended_at=T0 + timedelta(hours=3, minutes=4),
        ))
        db_session.commit()

        data = await SteamGamingPlugin().get_dashboard_data(db_session)

        item = data["items"][0]
        assert item["tone"] == "neutral"
        assert item["value"] == "24.07. · 3h 04m"

    async def test_unresolved_name_falls_back_to_the_app_id(self, db_session):
        db_session.add(SteamSession(
            app_id="999", game_name=None, started_at=T0, last_seen_at=T0, ended_at=T0,
        ))
        db_session.commit()

        data = await SteamGamingPlugin().get_dashboard_data(db_session)

        assert data["items"][0]["label"] == "AppID 999"

    async def test_at_most_five_rows_newest_first(self, db_session):
        for index in range(7):
            start = T0 + timedelta(hours=index)
            db_session.add(SteamSession(
                app_id=str(index), game_name=f"Game {index}",
                started_at=start, last_seen_at=start, ended_at=start,
            ))
        db_session.commit()

        data = await SteamGamingPlugin().get_dashboard_data(db_session)

        labels = [item["label"] for item in data["items"]]
        assert labels == ["Game 6", "Game 5", "Game 4", "Game 3", "Game 2"]

    async def test_sub_hour_duration_has_no_hour_part(self, db_session):
        db_session.add(SteamSession(
            app_id="111", game_name="Metro", started_at=T0,
            last_seen_at=T0 + timedelta(minutes=12), ended_at=T0 + timedelta(minutes=12),
        ))
        db_session.commit()

        data = await SteamGamingPlugin().get_dashboard_data(db_session)

        assert data["items"][0]["value"] == "24.07. · 12m"

    async def test_running_session_duration_counts_up_to_now(self, db_session, monkeypatch):
        """The only now-dependent formatting in the panel - without a fixed
        clock the assertion could only check that the string ends in 'm'."""
        import app.plugins.installed.steam_gaming as plugin_module

        db_session.add(SteamSession(app_id="111", game_name="Metro", started_at=T0, last_seen_at=T0))
        db_session.commit()
        monkeypatch.setattr(plugin_module, "_utc_now", lambda: T0 + timedelta(hours=2, minutes=5))

        data = await SteamGamingPlugin().get_dashboard_data(db_session)

        assert data["items"][0]["value"] == "2h 05m"

    async def test_a_running_session_sorts_above_the_finished_ones(self, db_session):
        finished = T0 - timedelta(hours=5)
        db_session.add_all([
            SteamSession(
                app_id="222", game_name="Cyberpunk", started_at=finished,
                last_seen_at=finished + timedelta(hours=1),
                ended_at=finished + timedelta(hours=1),
            ),
            SteamSession(app_id="111", game_name="Metro", started_at=T0, last_seen_at=T0),
        ])
        db_session.commit()

        data = await SteamGamingPlugin().get_dashboard_data(db_session)

        assert [(i["label"], i["tone"]) for i in data["items"]] == [
            ("Metro", "ok"),
            ("Cyberpunk", "neutral"),
        ]


class TestDurationFormat:
    def test_the_boundaries_that_the_panel_relies_on(self):
        from app.plugins.installed.steam_gaming import _format_duration

        assert _format_duration(0) == "0m"
        assert _format_duration(59) == "0m"
        assert _format_duration(720) == "12m"
        assert _format_duration(3600) == "1h 00m"
        assert _format_duration(3659) == "1h 00m"
        assert _format_duration(3660) == "1h 01m"
