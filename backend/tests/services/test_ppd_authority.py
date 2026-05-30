"""Tests for PPD authority service + authority config."""
import pytest

from app.services.power import config_store, ppd_authority


def test_authority_config_roundtrip():
    config_store.save_authority_config({"external_authority_enabled": True, "boost_rules_enabled": False})
    cfg = config_store.load_authority_config()
    assert cfg["external_authority_enabled"] is True
    assert cfg["boost_rules_enabled"] is False
    config_store.save_authority_config({"external_authority_enabled": False, "boost_rules_enabled": True})


@pytest.mark.asyncio
async def test_acquire_stops_and_masks_ppd(monkeypatch):
    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        class R:
            returncode = 0
            stdout = b"active\n" if args[:2] == ["systemctl", "is-active"] else b""
        return R()
    monkeypatch.setattr(ppd_authority.subprocess, "run", fake_run)
    await ppd_authority.acquire()
    assert ["sudo", "-n", "systemctl", "stop", "power-profiles-daemon"] in calls
    assert ["sudo", "-n", "systemctl", "mask", "power-profiles-daemon"] in calls


@pytest.mark.asyncio
async def test_release_unmasks_ppd(monkeypatch):
    calls = []
    monkeypatch.setattr(ppd_authority.subprocess, "run",
                        lambda args, **kw: calls.append(args) or type("R", (), {"returncode": 0, "stdout": b""})())
    await ppd_authority.release()
    assert ["sudo", "-n", "systemctl", "unmask", "power-profiles-daemon"] in calls
