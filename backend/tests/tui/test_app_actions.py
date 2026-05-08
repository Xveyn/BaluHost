"""Tests for BaluHostApp action methods (auth guards)."""
from __future__ import annotations

import inspect

import pytest


def test_action_logs_defined_only_once():
    """Regression: app.py had a duplicate action_logs that bypassed the auth check."""
    from baluhost_tui import app as app_module

    src = inspect.getsource(app_module.BaluHostApp)
    assert src.count("def action_logs(") == 1, (
        "BaluHostApp has more than one action_logs definition — the second one "
        "overrides the auth check (regression of TUI_FEATURE_AUDIT issue #1)."
    )


def test_action_logs_blocks_unauthenticated(fake_app_io):
    """Unauthenticated users must not be able to open the audit log viewer."""
    from baluhost_tui.app import BaluHostApp

    notify, push_screen = fake_app_io
    app = BaluHostApp.__new__(BaluHostApp)  # bypass __init__ (Textual side-effects)
    app.current_user = None
    app.notify = notify  # type: ignore[assignment]
    app.push_screen = push_screen  # type: ignore[assignment]

    app.action_logs()

    assert push_screen.calls == [], "push_screen must NOT be called without login"
    assert notify.calls, "notify must be called with an auth-error message"
    assert notify.calls[0][1] == "error"


def test_action_power_blocks_unauthenticated(fake_app_io):
    from baluhost_tui.app import BaluHostApp

    notify, push_screen = fake_app_io
    app = BaluHostApp.__new__(BaluHostApp)
    app.current_user = None
    app.notify = notify  # type: ignore[assignment]
    app.push_screen = push_screen  # type: ignore[assignment]

    app.action_power()

    assert push_screen.calls == []
    assert notify.calls and notify.calls[0][1] == "error"


def test_action_power_blocks_non_admin(fake_app_io):
    from baluhost_tui.app import BaluHostApp

    notify, push_screen = fake_app_io
    app = BaluHostApp.__new__(BaluHostApp)
    app.current_user = {"id": 1, "username": "u", "role": "user", "email": ""}
    app.mode = "remote"
    app.server = "http://localhost:8000"
    app.token = "t"
    app.notify = notify  # type: ignore[assignment]
    app.push_screen = push_screen  # type: ignore[assignment]

    app.action_power()

    assert push_screen.calls == []
    assert notify.calls and "admin" in notify.calls[0][0].lower()
