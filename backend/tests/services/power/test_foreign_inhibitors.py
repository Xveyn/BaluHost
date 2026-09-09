"""Tests for respecting third-party logind block inhibitors (issue #602).

BaluHost suspends via `rtcwake -m mem`, which bypasses logind entirely — so
inhibitors other programs hold are not enforced against us by the OS. We have
to consult them ourselves. Proven on 2026-09-08: steam-bpm-inhibit held a
block on sleep:idle throughout a game session and BaluHost suspended anyway.
"""
import json

import pytest

from app.services.power import foreign_inhibitors as fi


@pytest.fixture(autouse=True)
def _clear_cache():
    fi.reset_cache()
    yield
    fi.reset_cache()


def _payload(*rows):
    """busctl --json=short shape: one output argument holding an array."""
    return json.dumps({"type": "a(ssssuu)", "data": [list(rows)]})


STEAM = ["sleep:idle", "steam-bpm-inhibit", "Steam BPM oder Spiel aktiv", "block", 1000, 102863]
BALU_BLOCK = ["sleep", "BaluHost", "always_awake_active", "block", 1000, 84655]
BALU_DELAY = ["sleep", "BaluHost", "Set RTC wake at next core uptime window start", "delay", 1000, 84593]
NM_DELAY = ["sleep", "NetworkManager", "NetworkManager needs to turn off networks", "delay", 0, 1195]
POWERDEVIL = ["handle-power-key:handle-suspend-key", "PowerDevil", "KDE handles power events", "block", 1000, 3506]


# Captured verbatim from BaluNode on 2026-09-09 while a game was running.
# Every filter this module implements is represented here: delay entries, a
# block that covers no sleep lock, both of BaluHost's own, and exactly one
# foreign block that must survive.
REAL_PAYLOAD = (
    '{"type":"a(ssssuu)","data":[[["sleep","Bildschirmsperre","Stellt sicher, dass der '
    'Bildschirm vor dem Herunterfahren gesperrt wird","delay",1000,2903],'
    '["sleep","UPower","Pause device polling","delay",0,3451],'
    '["sleep","BaluHost","Set RTC wake at next core uptime window start","delay",1000,3180],'
    '["sleep","NetworkManager","NetworkManager needs to turn off networks","delay",0,1196],'
    '["sleep","ModemManager","ModemManager needs to reset devices","delay",0,1227],'
    '["handle-power-key:handle-suspend-key:handle-hibernate-key:handle-lid-switch",'
    '"PowerDevil","KDE handles power events","block",1000,3526],'
    '["sleep:idle","steam-bpm-inhibit","Steam BPM oder Spiel aktiv","block",1000,9364],'
    '["sleep","BaluHost","core_uptime_and_user_present_active","block",1000,3211]]]}'
)


class TestRealProductionPayload:
    """Guards the parser against the actual shape busctl emits.

    The synthesised fixtures below could all agree with each other and still be
    the wrong shape; this one cannot.
    """

    def test_all_eight_entries_are_parsed(self):
        assert len(fi.parse_inhibitors(REAL_PAYLOAD)) == 8

    def test_exactly_the_steam_inhibitor_survives_filtering(self):
        found = fi.first_blocking("sleep", runner=lambda: REAL_PAYLOAD)
        assert found is not None
        assert found.who == "steam-bpm-inhibit"
        assert found.pid == 9364

    def test_powerdevils_block_is_not_mistaken_for_a_sleep_lock(self):
        """Its `what` contains "handle-suspend-key" but no `sleep` segment."""
        blocks = fi.list_foreign_blocks(runner=lambda: REAL_PAYLOAD)
        powerdevil = next(i for i in blocks if i.who == "PowerDevil")
        assert powerdevil.covers("sleep") is False

    def test_baluhosts_own_block_is_excluded(self):
        blocks = fi.list_foreign_blocks(runner=lambda: REAL_PAYLOAD)
        assert all(i.who != "BaluHost" for i in blocks)


class TestParse:
    def test_reads_the_busctl_payload(self):
        rows = fi.parse_inhibitors(_payload(STEAM))
        assert len(rows) == 1
        assert rows[0].who == "steam-bpm-inhibit"
        assert rows[0].why == "Steam BPM oder Spiel aktiv"
        assert rows[0].mode == "block"
        assert rows[0].pid == 102863

    def test_empty_list(self):
        assert fi.parse_inhibitors(_payload()) == []

    def test_malformed_payload_yields_nothing(self):
        """Fail toward energy saving, like the other suppressors."""
        assert fi.parse_inhibitors("not json at all") == []
        assert fi.parse_inhibitors(json.dumps({"unexpected": True})) == []

    def test_short_row_is_skipped_not_fatal(self):
        payload = json.dumps({"type": "a(ssssuu)", "data": [[["sleep", "x"], STEAM]]})
        rows = fi.parse_inhibitors(payload)
        assert [r.who for r in rows] == ["steam-bpm-inhibit"]


class TestCovers:
    def test_matches_a_segment_of_the_colon_list(self):
        steam = fi.parse_inhibitors(_payload(STEAM))[0]
        assert steam.covers("sleep") is True
        assert steam.covers("idle") is True

    def test_does_not_match_a_substring_of_another_segment(self):
        """`handle-suspend-key` must not count as `sleep`, nor as a prefix match."""
        pd = fi.parse_inhibitors(_payload(POWERDEVIL))[0]
        assert pd.covers("sleep") is False
        assert pd.covers("handle-power-key") is True


class TestBlockingLookup:
    def test_finds_a_foreign_block_inhibitor_on_sleep(self):
        runner = lambda: _payload(STEAM, NM_DELAY, POWERDEVIL)
        found = fi.first_blocking("sleep", runner=runner)
        assert found is not None and found.who == "steam-bpm-inhibit"

    def test_ignores_delay_mode(self):
        """delay only postpones suspend; it is not a refusal."""
        assert fi.first_blocking("sleep", runner=lambda: _payload(NM_DELAY, BALU_DELAY)) is None

    def test_ignores_baluhosts_own_block(self):
        """Our own inhibitor must not make us refuse our own suspend."""
        assert fi.first_blocking("sleep", runner=lambda: _payload(BALU_BLOCK)) is None

    def test_ignores_a_block_that_does_not_cover_the_kind(self):
        assert fi.first_blocking("sleep", runner=lambda: _payload(POWERDEVIL)) is None

    def test_idle_kind_is_matched_separately(self):
        runner = lambda: _payload(STEAM)
        assert fi.first_blocking("idle", runner=runner) is not None

    def test_runner_failure_allows_suspend(self):
        def boom():
            raise OSError("busctl not found")
        assert fi.first_blocking("sleep", runner=boom) is None


class TestCache:
    def test_repeated_lookups_do_not_respawn_the_subprocess(self):
        calls = []

        def runner():
            calls.append(1)
            return _payload(STEAM)

        fi.first_blocking("sleep", runner=runner)
        fi.first_blocking("idle", runner=runner)
        fi.first_blocking("sleep", runner=runner)
        assert len(calls) == 1

    def test_cache_expires(self):
        calls = []

        def runner():
            calls.append(1)
            return _payload(STEAM)

        fi.first_blocking("sleep", runner=runner, now=lambda: 100.0)
        # Far beyond the TTL, so the second lookup must go out again.
        fi.first_blocking("sleep", runner=runner, now=lambda: 999.0)
        assert len(calls) == 2
