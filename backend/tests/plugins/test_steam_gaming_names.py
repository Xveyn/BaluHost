"""Resolving a Steam AppID to its display name."""

from pathlib import Path

import pytest

from app.plugins.installed.steam_gaming import names


@pytest.fixture(autouse=True)
def _clean_caches():
    names.reset_caches()
    yield
    names.reset_caches()


def _library(tmp_path: Path, app_id: str, game_name: str) -> Path:
    steamapps = tmp_path / "SteamLibrary" / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / f"appmanifest_{app_id}.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"%s"\n\t"name"\t\t"%s"\n\t"SizeOnDisk"\t"123"\n}\n'
        % (app_id, game_name),
        encoding="utf-8",
    )
    return steamapps


def test_resolves_the_name_from_the_app_manifest(tmp_path, monkeypatch):
    steamapps = _library(tmp_path, "1449560", "Metro Exodus Enhanced Edition")
    monkeypatch.setattr(names, "find_steamapps_dirs", lambda: [steamapps])

    assert names.resolve_name("1449560") == "Metro Exodus Enhanced Edition"


def test_unknown_app_id_resolves_to_none(tmp_path, monkeypatch):
    """Non-Steam shortcuts have a synthetic AppID and no manifest."""
    steamapps = _library(tmp_path, "1449560", "Metro Exodus Enhanced Edition")
    monkeypatch.setattr(names, "find_steamapps_dirs", lambda: [steamapps])

    assert names.resolve_name("3000000000") is None


def test_corrupt_manifest_resolves_to_none(tmp_path, monkeypatch):
    steamapps = tmp_path / "steamapps"
    steamapps.mkdir()
    (steamapps / "appmanifest_55.acf").write_text("{{{ not vdf", encoding="utf-8")
    monkeypatch.setattr(names, "find_steamapps_dirs", lambda: [steamapps])

    assert names.resolve_name("55") is None


def test_a_resolved_name_is_cached(tmp_path, monkeypatch):
    steamapps = _library(tmp_path, "1449560", "Metro Exodus Enhanced Edition")
    calls = []

    def _counting():
        calls.append(1)
        return [steamapps]

    monkeypatch.setattr(names, "find_steamapps_dirs", _counting)

    assert names.resolve_name("1449560") == "Metro Exodus Enhanced Edition"
    assert names.resolve_name("1449560") == "Metro Exodus Enhanced Edition"
    assert len(calls) == 1, "a game name never changes — resolve it once"


def test_a_miss_is_retried_after_the_ttl(tmp_path, monkeypatch):
    """A manifest can appear while a game is still installing."""
    steamapps = tmp_path / "steamapps"
    steamapps.mkdir()
    monkeypatch.setattr(names, "find_steamapps_dirs", lambda: [steamapps])

    clock = {"now": 1000.0}
    monkeypatch.setattr(names, "_monotonic", lambda: clock["now"])

    assert names.resolve_name("77") is None

    (steamapps / "appmanifest_77.acf").write_text(
        '"AppState"\n{\n\t"name"\t\t"Later Installed"\n}\n', encoding="utf-8"
    )
    assert names.resolve_name("77") is None, "still inside the negative TTL"

    clock["now"] += names._MISS_TTL_SECONDS + 1
    assert names.resolve_name("77") == "Later Installed"
