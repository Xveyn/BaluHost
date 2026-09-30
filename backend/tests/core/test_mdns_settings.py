"""MDNS_FORCE_ENABLED is read from the environment like MDNS_HOSTNAME (#678)."""
import pytest

from app.core.config import Settings


def test_force_flag_defaults_to_false(monkeypatch):
    monkeypatch.delenv("MDNS_FORCE_ENABLED", raising=False)
    assert Settings().mdns_force_enabled is False


@pytest.mark.parametrize("raw", ["true", "1", "True"])
def test_force_flag_reads_env(monkeypatch, raw):
    monkeypatch.setenv("MDNS_FORCE_ENABLED", raw)
    assert Settings().mdns_force_enabled is True
