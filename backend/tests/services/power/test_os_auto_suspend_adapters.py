"""Tests for os_auto_suspend adapters and shared types."""
from app.services.power import os_auto_suspend as oas


class TestAutoSuspendValue:
    def test_construct_and_compare(self):
        v1 = oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
        v2 = oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
        assert v1 == v2
        assert v1.timeout_minutes == 15

    def test_frozen(self):
        import dataclasses
        v = oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
        try:
            v.timeout_minutes = 30  # type: ignore[misc]
        except dataclasses.FrozenInstanceError:
            return
        raise AssertionError("expected FrozenInstanceError")
