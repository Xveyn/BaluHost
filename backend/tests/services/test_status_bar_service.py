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


def test_catalog_has_twelve_pills_with_unique_ids():
    from app.services.status_bar.catalog import CATALOG
    ids = [p.id for p in CATALOG]
    assert len(ids) == 12
    assert len(set(ids)) == 12


def test_desktop_pill_in_catalog_unlocked_admin_default():
    from app.services.status_bar.catalog import CATALOG_BY_ID
    d = CATALOG_BY_ID["desktop"]
    assert d.default_visibility == "admin"
    assert d.visibility_locked is False
    assert d.display_mode_configurable is True
    assert d.href == "/admin/system-control?tab=sleep"


def test_only_desktop_is_display_mode_configurable():
    from app.services.status_bar.catalog import CATALOG
    configurable = {p.id for p in CATALOG if p.display_mode_configurable}
    assert configurable == {"desktop"}


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
    assert len(config.pills) == 12
    raid = next(p for p in config.pills if p.pill_id == "raid")
    assert raid.enabled is False
    assert raid.visibility_locked is True
    assert config.show_bottom_upload is True


def test_get_config_is_idempotent(db_session):
    svc = StatusBarService(db_session)
    svc.get_config()
    svc.get_config()
    from app.models.status_bar import StatusBarPillConfig
    assert db_session.query(StatusBarPillConfig).count() == 12


# ── Task 10: config update (locked guard + diff) ────────────────────────
def test_update_config_persists_enabled_and_order(db_session):
    from app.schemas.status_bar import StatusBarConfigUpdate, PillConfigItem
    svc = StatusBarService(db_session)
    svc.get_config()  # seed
    update = StatusBarConfigUpdate(
        pills=[PillConfigItem(pill_id="power", enabled=True, visibility="all", sort_order=5)],
        show_bottom_upload=False,
    )
    svc.update_config(update)
    config = svc.get_config()
    power = next(p for p in config.pills if p.pill_id == "power")
    assert power.enabled is True
    assert power.visibility == "all"
    assert power.sort_order == 5
    assert config.show_bottom_upload is False


def test_update_config_rejects_all_visibility_for_locked_pill(db_session):
    from app.schemas.status_bar import StatusBarConfigUpdate, PillConfigItem
    svc = StatusBarService(db_session)
    svc.get_config()
    update = StatusBarConfigUpdate(
        pills=[PillConfigItem(pill_id="raid", enabled=True, visibility="all", sort_order=0)],
        show_bottom_upload=True,
    )
    with pytest.raises(ValueError, match="visibility_locked"):
        svc.update_config(update)


# ── Task 11: collect_state (role filter + sort) ─────────────────────────
@pytest.mark.asyncio
async def test_collect_state_only_includes_enabled_pills(db_session, monkeypatch):
    from app.schemas.status_bar import StatusBarConfigUpdate, PillConfigItem
    import app.services.status_bar.service as service_mod

    async def fake_power(db, role):
        return {"kind": "state", "tone": "info", "label": "Performance"}

    monkeypatch.setitem(service_mod.COLLECTORS, "power", fake_power)

    svc = StatusBarService(db_session)
    svc.get_config()
    svc.update_config(StatusBarConfigUpdate(
        pills=[PillConfigItem(pill_id="power", enabled=True, visibility="all", sort_order=0)],
        show_bottom_upload=True,
    ))
    state = await svc.collect_state(role="admin")
    ids = [p.id for p in state.pills]
    assert ids == ["power"]
    assert state.pills[0].href == "/admin/system-control?tab=energy"


@pytest.mark.asyncio
async def test_collect_state_filters_admin_pills_for_user(db_session, monkeypatch):
    from app.schemas.status_bar import StatusBarConfigUpdate, PillConfigItem
    import app.services.status_bar.service as service_mod

    async def fake(db, role):
        return {"kind": "state", "tone": "info", "label": "X"}

    monkeypatch.setitem(service_mod.COLLECTORS, "power", fake)
    monkeypatch.setitem(service_mod.COLLECTORS, "uploads", fake)

    svc = StatusBarService(db_session)
    svc.get_config()
    svc.update_config(StatusBarConfigUpdate(
        pills=[
            PillConfigItem(pill_id="power", enabled=True, visibility="admin", sort_order=0),
            PillConfigItem(pill_id="uploads", enabled=True, visibility="all", sort_order=1),
        ],
        show_bottom_upload=True,
    ))
    user_state = await svc.collect_state(role="user")
    assert [p.id for p in user_state.pills] == ["uploads"]


@pytest.mark.asyncio
async def test_collect_state_respects_sort_order(db_session, monkeypatch):
    from app.schemas.status_bar import StatusBarConfigUpdate, PillConfigItem
    import app.services.status_bar.service as service_mod

    async def fake(db, role):
        return {"kind": "state", "tone": "info", "label": "X"}

    for pid in ("power", "pihole"):
        monkeypatch.setitem(service_mod.COLLECTORS, pid, fake)

    svc = StatusBarService(db_session)
    svc.get_config()
    svc.update_config(StatusBarConfigUpdate(
        pills=[
            PillConfigItem(pill_id="power", enabled=True, visibility="all", sort_order=9),
            PillConfigItem(pill_id="pihole", enabled=True, visibility="all", sort_order=1),
        ],
        show_bottom_upload=True,
    ))
    state = await svc.collect_state(role="admin")
    assert [p.id for p in state.pills] == ["pihole", "power"]


@pytest.mark.asyncio
async def test_collect_state_skips_collector_with_malformed_output(db_session, monkeypatch):
    """A collector returning an invalid partial dict must be skipped, not 500 the endpoint."""
    from app.schemas.status_bar import StatusBarConfigUpdate, PillConfigItem
    import app.services.status_bar.service as service_mod

    async def bad(db, role):
        return {"tone": "info"}  # missing required kind/label -> PillState ValidationError

    async def good(db, role):
        return {"kind": "state", "tone": "info", "label": "OK"}

    monkeypatch.setitem(service_mod.COLLECTORS, "power", bad)
    monkeypatch.setitem(service_mod.COLLECTORS, "pihole", good)

    svc = StatusBarService(db_session)
    svc.get_config()
    svc.update_config(StatusBarConfigUpdate(
        pills=[
            PillConfigItem(pill_id="power", enabled=True, visibility="all", sort_order=0),
            PillConfigItem(pill_id="pihole", enabled=True, visibility="all", sort_order=1),
        ],
        show_bottom_upload=True,
    ))
    state = await svc.collect_state(role="admin")
    # The malformed "power" pill is skipped; the good "pihole" pill still renders.
    assert [p.id for p in state.pills] == ["pihole"]
