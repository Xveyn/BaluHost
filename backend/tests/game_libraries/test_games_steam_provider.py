"""Tests for the Steam game library provider."""

import pytest
from pathlib import Path

from app.services.game_libraries import steam


def _make_library(root: Path, apps: dict[str, tuple[int, str | None]]) -> None:
    """Create a fake Steam root at *root* with the given apps.

    apps maps appid -> (size_bytes, name_or_None). When name is None, no .acf is
    written (simulates a missing manifest -> fallback name).
    """
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    apps_lines = "\n".join(f'            "{aid}" "{size}"' for aid, (size, _n) in apps.items())
    vdf_text = (
        '"libraryfolders"\n{\n    "0"\n    {\n'
        f'        "path"  "{root.as_posix()}"\n'
        '        "apps"\n        {\n'
        f'{apps_lines}\n'
        '        }\n    }\n}\n'
    )
    (steamapps / "libraryfolders.vdf").write_text(vdf_text, encoding="utf-8")
    for aid, (size, name) in apps.items():
        if name is not None:
            (steamapps / f"appmanifest_{aid}.acf").write_text(
                f'"AppState"\n{{\n    "appid" "{aid}"\n    "name" "{name}"\n    "SizeOnDisk" "{size}"\n}}\n',
                encoding="utf-8",
            )


def test_is_available_false_when_no_steam(tmp_path, monkeypatch):
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(tmp_path / "nope")])
    assert steam.SteamProvider().is_available() is False


def test_get_libraries_reads_sizes_names_sorted(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    _make_library(root, {
        "111": (5000, "Game A"),
        "222": (3000, "Game B"),
        "333": (1000, None),  # no .acf -> fallback name
    })
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root)])

    provider = steam.SteamProvider()
    assert provider.is_available() is True

    libs = provider.get_libraries()
    assert len(libs) == 1
    lib = libs[0]
    assert lib.provider == "steam"
    assert lib.provider_name == "Steam"
    assert lib.total_bytes == 9000
    assert lib.game_count == 3
    assert [g.size_bytes for g in lib.games] == [5000, 3000, 1000]  # desc
    assert lib.games[0].name == "Game A"
    assert lib.games[2].name == "App 333"  # fallback for missing .acf
    assert lib.device_id is not None


def test_get_libraries_dedupes_roots_pointing_to_same_lib(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    _make_library(root, {"111": (5000, "Game A")})
    # Two candidate roots that resolve to the same vdf must yield one library.
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root), str(root)])
    libs = steam.SteamProvider().get_libraries()
    assert len(libs) == 1


@pytest.mark.parametrize("name", [
    "Proton 8.0",
    "Proton Experimental",
    "Proton EasyAntiCheat Runtime",
    "Steam Linux Runtime 3.0 (sniper)",
    "Steamworks Common Redistributables",
    "STEAMWORKS COMMON REDISTRIBUTABLES",  # case-insensitive
])
def test_is_tool_app_true(name):
    assert steam._is_tool_app(name) is True


@pytest.mark.parametrize("name", [
    "Counter-Strike 2",
    "Cyberpunk 2077",
    "App 12345",  # fallback name for missing .acf
])
def test_is_tool_app_false(name):
    assert steam._is_tool_app(name) is False


def test_get_libraries_filters_tool_apps(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    _make_library(root, {
        "111": (5000, "Counter-Strike 2"),
        "222": (3000, "Cyberpunk 2077"),
        "900": (1500, "Proton 8.0"),
        "901": (700, "Steam Linux Runtime 3.0 (sniper)"),
        "902": (462, "Steamworks Common Redistributables"),
    })
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root)])

    libs = steam.SteamProvider().get_libraries()
    assert len(libs) == 1
    lib = libs[0]
    assert [g.name for g in lib.games] == ["Counter-Strike 2", "Cyberpunk 2077"]
    assert lib.game_count == 2
    assert lib.total_bytes == 8000  # tool bytes excluded


def test_get_libraries_drops_tools_only_library(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    _make_library(root, {
        "900": (1500, "Proton 8.0"),
        "902": (462, "Steamworks Common Redistributables"),
    })
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root)])
    assert steam.SteamProvider().get_libraries() == []
