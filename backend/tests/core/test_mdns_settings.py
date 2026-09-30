"""MDNS_FORCE_ENABLED is read from the environment like MDNS_HOSTNAME (#678)."""
import pytest

from app.core.config import Settings


def test_force_flag_defaults_to_false(monkeypatch, tmp_path):
    # A developer's own .env (which .env.example invites to set the flag) must
    # not decide what the *default* is.
    (tmp_path / ".env").write_text("MDNS_FORCE_ENABLED=true\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MDNS_FORCE_ENABLED", raising=False)
    assert Settings(_env_file=None).mdns_force_enabled is False


@pytest.mark.parametrize("raw", ["true", "1", "True"])
def test_force_flag_reads_env(monkeypatch, raw):
    monkeypatch.setenv("MDNS_FORCE_ENABLED", raw)
    assert Settings().mdns_force_enabled is True
