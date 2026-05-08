"""Shared fixtures for TUI tests."""
from __future__ import annotations

from typing import Any
import pytest


class FakeNotify:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, message: Any, severity: str = "information", **kwargs: Any) -> None:
        self.calls.append((str(message), severity))


class FakePushScreen:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def __call__(self, screen: Any) -> None:
        self.calls.append(screen)


@pytest.fixture
def fake_app_io():
    """Returns (notify, push_screen) recorder pair for patching app methods."""
    return FakeNotify(), FakePushScreen()
