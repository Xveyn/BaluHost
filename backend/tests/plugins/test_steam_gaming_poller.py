"""Steam session poller: play/not-play edge detection (Teilprojekt 3/4)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.plugins.installed.steam_gaming.poller import SteamSessionPoller


def _poller(sequence):
    """A poller whose detector yields the given app_ids across ticks."""
    calls = iter(sequence)
    detect = MagicMock(side_effect=lambda *a, **k: next(calls))
    resolve = MagicMock(side_effect=lambda app_id: f"Game {app_id}")
    emit = AsyncMock()
    return SteamSessionPoller(detect=detect, resolve=resolve, emit=emit), emit


class TestEdgeDetection:
    async def test_first_tick_only_establishes_a_baseline(self):
        """A game already running at startup must NOT fire 'started' - that
        would false-alarm after every backend restart."""
        poller, emit = _poller(["1449560"])
        await poller.tick()
        emit.assert_not_awaited()

    async def test_none_to_game_is_a_start(self):
        poller, emit = _poller([None, "1449560"])
        await poller.tick()   # baseline: None
        await poller.tick()   # None -> game
        emit.assert_awaited_once()
        args, kwargs = emit.await_args
        assert args[:2] == ("steam_gaming", "session_started")
        assert kwargs["entity_id"] == "1449560"
        assert kwargs["game"] == "Game 1449560"

    async def test_game_to_none_is_an_end(self):
        poller, emit = _poller(["1449560", None])
        await poller.tick()   # baseline: game
        await poller.tick()   # game -> None
        emit.assert_awaited_once()
        args, kwargs = emit.await_args
        assert args[:2] == ("steam_gaming", "session_ended")
        assert kwargs["entity_id"] == "1449560"
        assert kwargs["game"] == "Game 1449560"

    async def test_same_game_across_ticks_is_no_event(self):
        poller, emit = _poller([None, "1449560", "1449560"])
        await poller.tick()
        await poller.tick()   # start
        emit.reset_mock()
        await poller.tick()   # same game
        emit.assert_not_awaited()

    async def test_direct_switch_fires_nothing_but_tracks_the_new_game(self):
        """X -> Y fires no event, but the state must follow to Y so a later
        Y -> None correctly ends on Y."""
        poller, emit = _poller([None, "111", "222", None])
        await poller.tick()   # baseline None
        await poller.tick()   # None -> 111 (start)
        emit.reset_mock()
        await poller.tick()   # 111 -> 222: no event
        emit.assert_not_awaited()
        await poller.tick()   # 222 -> None: end, on 222
        emit.assert_awaited_once()
        args, kwargs = emit.await_args
        assert args[:2] == ("steam_gaming", "session_ended")
        assert kwargs["entity_id"] == "222"

    async def test_unresolved_name_falls_back_to_the_app_id(self):
        poller, emit = _poller([None, "999"])
        poller._resolve = MagicMock(return_value=None)
        await poller.tick()
        await poller.tick()
        assert emit.await_args.kwargs["game"] == "999"
