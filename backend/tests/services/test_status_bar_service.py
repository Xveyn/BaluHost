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


def test_catalog_has_eleven_pills_with_unique_ids():
    from app.services.status_bar.catalog import CATALOG
    ids = [p.id for p in CATALOG]
    assert len(ids) == 11
    assert len(set(ids)) == 11


def test_locked_pills_default_to_admin_visibility():
    from app.services.status_bar.catalog import CATALOG
    for p in CATALOG:
        if p.visibility_locked:
            assert p.default_visibility == "admin"


def test_pill_id_literal_matches_catalog():
    """Drift detection: PILL_IDS Literal must equal the catalog ids exactly."""
    from typing import get_args
    from app.schemas.status_bar import PILL_IDS
    from app.services.status_bar.catalog import CATALOG
    assert set(get_args(PILL_IDS)) == {p.id for p in CATALOG}


def test_locked_set_matches_spec():
    from app.services.status_bar.catalog import CATALOG
    locked = {p.id for p in CATALOG if p.visibility_locked}
    assert locked == {"raid", "sleep", "vpn", "temp", "always_awake", "scheduler", "backup"}


# ── Task 9: config read (seed-on-read) ──────────────────────────────────
from app.services.status_bar.service import StatusBarService


def test_get_config_seeds_all_catalog_pills(db_session):
    svc = StatusBarService(db_session)
    config = svc.get_config()
    assert len(config.pills) == 11
    raid = next(p for p in config.pills if p.pill_id == "raid")
    assert raid.enabled is False
    assert raid.visibility_locked is True
    assert config.show_bottom_upload is True


def test_get_config_is_idempotent(db_session):
    svc = StatusBarService(db_session)
    svc.get_config()
    svc.get_config()
    from app.models.status_bar import StatusBarPillConfig
    assert db_session.query(StatusBarPillConfig).count() == 11
