"""Tests for the Steam game library provider."""

import pytest
from pathlib import Path

from app.services.game_libraries import steam


def _make_library(root: Path, apps: dict) -> None:
    """Create a fake Steam root at *root* with the given apps.

    apps maps appid -> (vdf_size, name_or_None) or
    (vdf_size, name_or_None, acf_size_override). The vdf ``apps`` block uses
    vdf_size; the .acf ``SizeOnDisk`` defaults to vdf_size unless a 3rd element
    overrides it. No .acf is written when name is None (simulates a missing
    manifest -> fallback name + vdf size).
    """
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    apps_lines = "\n".join(f'            "{aid}" "{spec[0]}"' for aid, spec in apps.items())
    vdf_text = (
        '"libraryfolders"\n{\n    "0"\n    {\n'
        f'        "path"  "{root.as_posix()}"\n'
        '        "apps"\n        {\n'
        f'{apps_lines}\n'
        '        }\n    }\n}\n'
    )
    (steamapps / "libraryfolders.vdf").write_text(vdf_text, encoding="utf-8")
    for aid, spec in apps.items():
        vdf_size, name = spec[0], spec[1]
        acf_size = spec[2] if len(spec) > 2 else vdf_size
        if name is not None:
            (steamapps / f"appmanifest_{aid}.acf").write_text(
                f'"AppState"\n{{\n    "appid" "{aid}"\n    "name" "{name}"\n    "SizeOnDisk" "{acf_size}"\n}}\n',
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
    "  Proton 8.0  ",  # leading/trailing whitespace is stripped
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


def test_size_prefers_acf_size_on_disk_over_vdf(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    # vdf apps size is 0 (stale tally); real size lives in .acf SizeOnDisk.
    _make_library(root, {"1091500": (0, "Cyberpunk 2077", 99_000_000_000)})
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root)])

    libs = steam.SteamProvider().get_libraries()
    assert len(libs) == 1
    assert libs[0].games[0].size_bytes == 99_000_000_000
    assert libs[0].total_bytes == 99_000_000_000


def test_size_falls_back_to_vdf_when_no_acf(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    _make_library(root, {"333": (1234, None)})  # no .acf written
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root)])

    libs = steam.SteamProvider().get_libraries()
    assert len(libs) == 1
    assert libs[0].games[0].size_bytes == 1234
    assert libs[0].games[0].name == "App 333"


def _write_libraryfolders_vdf(root: Path, extra: dict) -> None:
    """Write ``root/steamapps/libraryfolders.vdf`` declaring extra library paths.

    Entry "0" always points at *root* itself, mirroring real Steam behavior
    (the install root also lists itself as a library folder). *extra* maps
    additional entry ids to path strings — e.g. a library on a different
    mount than the Steam install, which is the scenario
    ``find_steamapps_dirs()`` exists to handle.
    """
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True, exist_ok=True)
    entries = {"0": root.as_posix()}
    entries.update(extra)
    body = "".join(
        f'    "{eid}"\n    {{\n        "path"  "{path}"\n        "apps"\n        {{\n        }}\n    }}\n'
        for eid, path in entries.items()
    )
    vdf_text = '"libraryfolders"\n{\n' + body + '}\n'
    (steamapps / "libraryfolders.vdf").write_text(vdf_text, encoding="utf-8")


def test_find_steamapps_dirs_returns_root_steamapps(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    _write_libraryfolders_vdf(root, {})
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root)])

    dirs = steam.find_steamapps_dirs()
    assert dirs == [root / "steamapps"]


def test_find_steamapps_dirs_includes_library_on_different_mount(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    # Simulates e.g. /mnt/cache-vcl/SteamLibrary declared in libraryfolders.vdf
    # while the Steam install itself lives elsewhere.
    extra = tmp_path / "SteamLibrary"
    (extra / "steamapps").mkdir(parents=True)
    _write_libraryfolders_vdf(root, {"1": extra.as_posix()})
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root)])

    dirs = steam.find_steamapps_dirs()
    assert set(dirs) == {root / "steamapps", extra / "steamapps"}


def test_find_steamapps_dirs_dedupes_dir_reachable_twice(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    extra = tmp_path / "SteamLibrary"
    (extra / "steamapps").mkdir(parents=True)
    # Same library path declared under two different entry ids.
    _write_libraryfolders_vdf(root, {"1": extra.as_posix(), "2": extra.as_posix()})
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root)])

    dirs = steam.find_steamapps_dirs()
    assert len(dirs) == 2  # root + extra, not three
    assert dirs.count(extra / "steamapps") == 1


def test_find_steamapps_dirs_skips_declared_path_missing_on_disk(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    missing = tmp_path / "UnmountedLibrary"  # never created on disk
    _write_libraryfolders_vdf(root, {"1": missing.as_posix()})
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root)])

    dirs = steam.find_steamapps_dirs()  # must not raise
    assert dirs == [root / "steamapps"]
