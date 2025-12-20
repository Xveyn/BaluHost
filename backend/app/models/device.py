"""Compatibility shim for older tests expecting `app.models.device.Device`.

This module exposes `Device` as an alias for the current `SyncState` model
so legacy imports keep working during tests.
"""
from app.models.sync_state import SyncState as Device

__all__ = ["Device"]
