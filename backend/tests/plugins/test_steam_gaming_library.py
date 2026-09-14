"""Installed, launchable games - one manifest per game, nothing else."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.plugins.installed.steam_gaming import library


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    library.reset_cache()
    monkeypatch.setattr(library.settings, "is_dev_mode", False)
    yield
    library.reset_cache()


def _steamapps(root: Path, games: dict[str, str | None]) -> Path:
    """games maps a manifest file id -> name (None writes no name field)."""
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    for app_id, name in games.items():
        body = f'"AppState"\n{{\n\t"appid"\t\t"{app_id}"\n'
        if name is not None:
            body += f'\t"name"\t\t"{name}"\n'
        body += "}\n"
        (steamapps / f"appmanifest_{app_id}.acf").write_text(body, encoding="utf-8")
    return steamapps


class TestIsValidAppId:
    @pytest.mark.parametrize("value", ["400", "1091500", "1234567890"])
    def test_digits_up_to_ten(self, value):
        assert library.is_valid_app_id(value) is True

    @pytest.mark.parametrize("value", ["", "abc", "400\n", "٤٠٠", "12345678901", "400/1", " 400", "-1"])
    def test_everything_else(self, value):
        assert library.is_valid_app_id(value) is False


class TestListInstalledGames:
    def test_a_manifest_with_a_name_is_a_game(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"400": "Portal"})
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])

        assert library.list_installed_games() == [library.InstalledGame("400", "Portal")]

    def test_tools_and_nameless_manifests_are_skipped(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {
            "400": "Portal", "3658110": "Proton 10.0", "55": None,
        })
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])

        assert [g.app_id for g in library.list_installed_games()] == ["400"]

    def test_a_game_in_two_libraries_is_listed_once(self, tmp_path, monkeypatch):
        a = _steamapps(tmp_path / "a", {"400": "Portal"})
        b = _steamapps(tmp_path / "b", {"400": "Portal", "620": "Portal 2"})
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [a, b])

        assert [g.app_id for g in library.list_installed_games()] == ["400", "620"]

    def test_sorted_by_name_case_insensitively(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"1": "valheim", "2": "Among Us", "3": "BeamNG"})
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])

        assert [g.name for g in library.list_installed_games()] == ["Among Us", "BeamNG", "valheim"]

    def test_long_names_are_truncated(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"400": "A" * 500})
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])

        assert len(library.list_installed_games()[0].name) == 200

    def test_a_file_with_a_non_numeric_id_is_ignored(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"400": "Portal"})
        (steamapps / "appmanifest_evil.acf").write_text('"AppState"\n{\n\t"name"\t"x"\n}\n', encoding="utf-8")
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])

        assert [g.app_id for g in library.list_installed_games()] == ["400"]

    def test_no_library_at_all_is_unavailable_in_prod(self, monkeypatch):
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [])

        with pytest.raises(library.LibraryUnavailable):
            library.list_installed_games()

    def test_no_library_in_dev_mode_is_the_mock(self, monkeypatch):
        monkeypatch.setattr(library.settings, "is_dev_mode", True)
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [])

        assert library.list_installed_games() == sorted(library.DEV_GAMES, key=lambda g: g.name.casefold())

    def test_the_list_is_cached_within_the_ttl(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"400": "Portal"})
        calls: list[int] = []

        def _counting():
            calls.append(1)
            return [steamapps]

        monkeypatch.setattr(library, "find_steamapps_dirs", _counting)
        clock = {"now": 100.0}
        monkeypatch.setattr(library, "_monotonic", lambda: clock["now"])

        library.list_installed_games()
        library.list_installed_games()
        assert len(calls) == 1

        clock["now"] += library._LIST_TTL_SECONDS + 1
        library.list_installed_games()
        assert len(calls) == 2


class TestFindInstalledGame:
    def test_finds_by_reading_one_manifest(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"400": "Portal"})
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])

        assert library.find_installed_game("400") == library.InstalledGame("400", "Portal")

    def test_unknown_tool_and_invalid_ids_are_none(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"3658110": "Proton 10.0"})
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])

        assert library.find_installed_game("400") is None
        assert library.find_installed_game("3658110") is None
        assert library.find_installed_game("../400") is None

    def test_it_is_never_served_from_the_list_cache(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"400": "Portal"})
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])
        library.list_installed_games()

        (steamapps / "appmanifest_400.acf").unlink()

        assert library.find_installed_game("400") is None

    def test_no_library_is_unavailable_in_prod(self, monkeypatch):
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [])

        with pytest.raises(library.LibraryUnavailable):
            library.find_installed_game("400")

    def test_dev_mode_finds_a_mock_game(self, monkeypatch):
        monkeypatch.setattr(library.settings, "is_dev_mode", True)
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [])

        assert library.find_installed_game("570") == library.InstalledGame("570", "Dota 2")
