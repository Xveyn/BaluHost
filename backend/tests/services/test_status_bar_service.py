"""Tests for the status bar models and aggregator service."""
from app.models.status_bar import StatusBarPillConfig, StatusBarSettings


def test_pill_config_model_has_expected_columns():
    cols = set(StatusBarPillConfig.__table__.columns.keys())
    assert cols == {"id", "pill_id", "enabled", "visibility", "sort_order", "updated_at"}


def test_settings_model_has_expected_columns():
    cols = set(StatusBarSettings.__table__.columns.keys())
    assert cols == {"id", "show_bottom_upload"}
