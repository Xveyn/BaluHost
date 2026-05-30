"""Tests for boost-rule process matching (filled in across Tasks 6-8)."""
from app.models.power_boost_rule import PowerBoostRule
from app.services.power.process_watcher import ProcInfo, match_boost_rules


def test_power_boost_rule_model_importable():
    assert PowerBoostRule.__tablename__ == "power_boost_rules"


WRAPPER = ProcInfo(name="pressure-vessel", cmdline="pressure-vessel-wrap -- game")
REAPER = ProcInfo(name="reaper", cmdline="reaper SteamLaunch AppId=1245620 -- game")
STEAM_IDLE = ProcInfo(name="steam", cmdline="/home/sven/.steam/steam")
FIREFOX = ProcInfo(name="firefox", cmdline="/usr/lib/firefox/firefox")


def _rule(kind, pattern=None, target=None, enabled=True, label="x"):
    return {"kind": kind, "pattern": pattern, "target_max_mhz": target,
            "enabled": enabled, "label": label}


def test_steam_in_tray_does_not_match_game_session():
    hit, target = match_boost_rules([STEAM_IDLE, FIREFOX], [_rule("game_session")])
    assert hit is False
    assert target is None


def test_pressure_vessel_matches_game_session():
    hit, target = match_boost_rules([STEAM_IDLE, WRAPPER], [_rule("game_session")])
    assert hit is True
    assert target is None


def test_reaper_steamlaunch_matches_game_session():
    hit, _ = match_boost_rules([REAPER], [_rule("game_session")])
    assert hit is True


def test_process_glob_matches_and_carries_target():
    procs = [ProcInfo(name="lutris-wrapper", cmdline="lutris ...")]
    hit, target = match_boost_rules(procs, [_rule("process_glob", pattern="lutris*", target=3000)])
    assert hit is True
    assert target == 3000


def test_highest_target_wins_none_beats_all():
    rules = [_rule("process_glob", pattern="lutris*", target=3000), _rule("game_session")]
    procs = [ProcInfo(name="lutris", cmdline="lutris"), WRAPPER]
    hit, target = match_boost_rules(procs, rules)
    assert hit is True
    assert target is None


def test_disabled_rule_ignored():
    hit, _ = match_boost_rules([WRAPPER], [_rule("game_session", enabled=False)])
    assert hit is False


import pytest
from app.schemas.power import PowerProfile
from app.services.power.manager import PowerManagerService
from app.services.power import process_watcher as pw


@pytest.mark.asyncio
async def test_watcher_registers_then_releases_after_two_absent_ticks(monkeypatch):
    mgr = PowerManagerService()
    mgr._primary = True
    mgr._watcher_absent_ticks = 0
    mgr._game_demand_active = False
    mgr._boost_max_override = None
    events = []

    async def fake_register(source, level, **kw):
        events.append(("register", kw.get("max_freq_override")))
        return source

    async def fake_unregister(source):
        events.append(("unregister", source))
        return True

    monkeypatch.setattr(mgr, "register_demand", fake_register)
    monkeypatch.setattr(mgr, "unregister_demand", fake_unregister)
    monkeypatch.setattr(mgr, "_active_boost_rules",
                        lambda: [{"kind": "game_session", "enabled": True, "pattern": None, "target_max_mhz": None}])

    # Tick 1: game present -> register
    monkeypatch.setattr(pw, "snapshot_processes", lambda: [pw.ProcInfo(name="pressure-vessel")])
    await mgr._watch_tick()
    assert ("register", None) in events
    assert mgr._game_demand_active is True

    # Tick 2: game gone (1 absent) -> still active (hysteresis)
    monkeypatch.setattr(pw, "snapshot_processes", lambda: [])
    await mgr._watch_tick()
    assert mgr._game_demand_active is True

    # Tick 3: (2 absent) -> release
    await mgr._watch_tick()
    assert ("unregister", "game-session") in events
    assert mgr._game_demand_active is False
