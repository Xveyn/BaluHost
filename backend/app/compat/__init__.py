from __future__ import annotations

import asyncio
import inspect
import sys
import warnings
from typing import Callable, TypeVar, cast

__all__ = ["apply_asyncio_patches"]

T = TypeVar("T")


def _patch_is_coroutine_function() -> None:
    module_name = getattr(asyncio.iscoroutinefunction, "__module__", "")
    if not module_name.startswith("asyncio"):
        return
    asyncio.iscoroutinefunction = cast(Callable[[T], bool], inspect.iscoroutinefunction)  # type: ignore[assignment]


def _patch_get_event_loop_policy() -> None:
    original = asyncio.get_event_loop_policy

    def _patched_get_event_loop_policy() -> asyncio.AbstractEventLoopPolicy:  # type: ignore[override]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return original()

    asyncio.get_event_loop_policy = _patched_get_event_loop_policy  # type: ignore[assignment]


def apply_asyncio_patches() -> None:
    if sys.version_info < (3, 14):
        return

    if not getattr(asyncio, "_baluhost_asyncio_patched", False):
        _patch_is_coroutine_function()
        _patch_get_event_loop_policy()
        asyncio._baluhost_asyncio_patched = True  # type: ignore[attr-defined]
