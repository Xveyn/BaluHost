"""Deep-idle event hooks for plugins (e.g., Ollama unload before deep idle)."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, List

logger = logging.getLogger(__name__)

_DeepIdleCallback = Callable[[], Awaitable[None]]

_deep_idle_entering_callbacks: List[_DeepIdleCallback] = []
_deep_idle_exiting_callbacks: List[_DeepIdleCallback] = []


def register_deep_idle_entering(callback: _DeepIdleCallback) -> None:
    """Plugin opt-in: called just before the GPU transitions ACTIVE/STANDBY -> DEEP_IDLE.

    Plugins should release VRAM/state here. The manager waits up to
    `deep_idle_grace_seconds` (configurable) for callbacks to finish before
    applying the deep-idle state.
    """
    _deep_idle_entering_callbacks.append(callback)


def register_deep_idle_exiting(callback: _DeepIdleCallback) -> None:
    """Plugin opt-in: called when the GPU leaves DEEP_IDLE."""
    _deep_idle_exiting_callbacks.append(callback)


async def emit_deep_idle_entering() -> None:
    """Run all 'entering' callbacks in parallel; exceptions logged, never raised."""
    if not _deep_idle_entering_callbacks:
        return
    results = await asyncio.gather(
        *(_safe_call(cb) for cb in _deep_idle_entering_callbacks),
        return_exceptions=False,
    )
    del results  # gathered for completion; errors already logged


async def emit_deep_idle_exiting() -> None:
    if not _deep_idle_exiting_callbacks:
        return
    await asyncio.gather(
        *(_safe_call(cb) for cb in _deep_idle_exiting_callbacks),
        return_exceptions=False,
    )


async def _safe_call(cb: _DeepIdleCallback) -> None:
    try:
        await cb()
    except Exception as exc:
        logger.warning("Deep-idle callback %r raised: %s", cb, exc)
