"""Tests for the tray token store."""

import json
import os
import stat

import pytest

from baluhost_tray import config as tray_config


@pytest.fixture(autouse=True)
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setattr(tray_config, "TOKEN_DIR", tmp_path / ".baluhost")
    monkeypatch.setattr(
        tray_config, "TOKEN_FILE", tmp_path / ".baluhost" / "tray-tokens.json"
    )
    return tmp_path


def test_roundtrip():
    tray_config.save_tokens(tray_config.Tokens(access="a", refresh="r"))
    assert tray_config.load_tokens() == tray_config.Tokens(access="a", refresh="r")


def test_missing_file_is_none():
    assert tray_config.load_tokens() is None


def test_file_is_owner_only():
    tray_config.save_tokens(tray_config.Tokens(access="a", refresh="r"))
    assert stat.S_IMODE(tray_config.TOKEN_FILE.stat().st_mode) == 0o600


def test_directory_is_owner_only():
    tray_config.save_tokens(tray_config.Tokens(access="a", refresh="r"))
    assert stat.S_IMODE(tray_config.TOKEN_DIR.stat().st_mode) == 0o700


def test_file_is_never_world_readable_even_briefly(monkeypatch):
    """Die Rechte muessen beim Anlegen stimmen, nicht erst danach.

    Wir fangen den Modus im Moment des Oeffnens ab: ein write_text() mit
    spaeterem chmod wuerde hier 0o666 zeigen.
    """
    seen = {}
    real_open = os.open

    def _spy(path, flags, mode=0o777):
        seen["mode"] = mode
        return real_open(path, flags, mode)

    monkeypatch.setattr(tray_config.os, "open", _spy)
    tray_config.save_tokens(tray_config.Tokens(access="a", refresh="r"))
    assert seen["mode"] == 0o600


def test_corrupt_file_is_none_not_crash():
    tray_config.TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    tray_config.TOKEN_FILE.write_text("{not json")
    assert tray_config.load_tokens() is None


def test_incomplete_file_is_none():
    tray_config.TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    tray_config.TOKEN_FILE.write_text(json.dumps({"access": "a"}))
    assert tray_config.load_tokens() is None


def test_clear_removes_file_and_is_idempotent():
    tray_config.save_tokens(tray_config.Tokens(access="a", refresh="r"))
    tray_config.clear_tokens()
    assert not tray_config.TOKEN_FILE.exists()
    tray_config.clear_tokens()
