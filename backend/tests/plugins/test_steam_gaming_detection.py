"""detection.py guards the column widths the ledger writes into (TP 4/4)."""
from __future__ import annotations

import pytest

from app.plugins.installed.steam_gaming import detection


@pytest.fixture
def prod_mode(monkeypatch):
    """The dev-mode stand-in would mask what these tests check."""
    monkeypatch.setattr(detection.settings, "is_dev_mode", False)


class TestAppIdGuard:
    def test_a_normal_app_id_passes_through(self, monkeypatch, prod_mode):
        monkeypatch.setattr(detection, "detect_running_app_id", lambda: "1449560")

        assert detection.current_app_id() == "1449560"

    def test_an_over_long_app_id_is_treated_as_no_game(self, monkeypatch, prod_mode):
        """SQLite ignores VARCHAR(32), PostgreSQL raises DataError on every
        tick - a booking that can never succeed is worse than no booking."""
        monkeypatch.setattr(detection, "detect_running_app_id", lambda: "9" * 40)

        assert detection.current_app_id() is None


class TestGameNameGuard:
    def test_a_normal_name_passes_through(self, monkeypatch, prod_mode):
        monkeypatch.setattr(detection, "resolve_name", lambda _app_id: "Metro Exodus")

        assert detection.resolve_game_name("1449560") == "Metro Exodus"

    def test_an_over_long_name_is_truncated_to_the_column_width(self, monkeypatch, prod_mode):
        monkeypatch.setattr(detection, "resolve_name", lambda _app_id: "A" * 500)

        resolved = detection.resolve_game_name("1449560")

        assert len(resolved) == detection._MAX_GAME_NAME_LENGTH
        assert resolved == "A" * detection._MAX_GAME_NAME_LENGTH

    def test_an_unresolvable_name_stays_none(self, monkeypatch, prod_mode):
        monkeypatch.setattr(detection, "resolve_name", lambda _app_id: None)

        assert detection.resolve_game_name("999") is None


class TestDevStandIn:
    def test_the_stand_in_is_the_default_in_dev_mode(self, monkeypatch):
        monkeypatch.setattr(detection.settings, "is_dev_mode", True)
        monkeypatch.setattr(detection, "detect_running_app_id", lambda: None)

        assert detection.current_app_id() == detection.DEV_APP_ID

    def test_it_can_be_switched_off(self, monkeypatch):
        """The launch routes must not see a permanently running dev game -
        every launch would be a 409 on the Windows dev box."""
        monkeypatch.setattr(detection.settings, "is_dev_mode", True)
        monkeypatch.setattr(detection, "detect_running_app_id", lambda: None)

        assert detection.current_app_id(dev_stand_in=False) is None

    def test_a_real_game_still_wins_without_the_stand_in(self, monkeypatch):
        monkeypatch.setattr(detection.settings, "is_dev_mode", True)
        monkeypatch.setattr(detection, "detect_running_app_id", lambda: "1449560")

        assert detection.current_app_id(dev_stand_in=False) == "1449560"

    def test_the_length_guard_applies_without_the_stand_in(self, monkeypatch, prod_mode):
        monkeypatch.setattr(detection, "detect_running_app_id", lambda: "9" * 40)

        assert detection.current_app_id(dev_stand_in=False) is None
