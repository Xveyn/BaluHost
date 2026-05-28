"""Tests for the status bar models and aggregator service."""
from app.models.status_bar import StatusBarPillConfig, StatusBarSettings


def test_pill_config_model_has_expected_columns():
    cols = set(StatusBarPillConfig.__table__.columns.keys())
    assert cols == {"id", "pill_id", "enabled", "visibility", "sort_order", "updated_at"}


def test_settings_model_has_expected_columns():
    cols = set(StatusBarSettings.__table__.columns.keys())
    assert cols == {"id", "show_bottom_upload"}


import pytest
from pydantic import ValidationError


def test_pill_config_item_rejects_unknown_pill_id():
    from app.schemas.status_bar import PillConfigItem
    with pytest.raises(ValidationError):
        PillConfigItem(pill_id="not_a_pill", enabled=True, visibility="admin", sort_order=0)


def test_pill_config_item_rejects_bad_visibility():
    from app.schemas.status_bar import PillConfigItem
    with pytest.raises(ValidationError):
        PillConfigItem(pill_id="power", enabled=True, visibility="everyone", sort_order=0)


def test_pill_state_minimal_construction():
    from app.schemas.status_bar import PillState
    s = PillState(id="raid", kind="alert", tone="warning", label="RAID", href="/x")
    assert s.value is None and s.extra is None
