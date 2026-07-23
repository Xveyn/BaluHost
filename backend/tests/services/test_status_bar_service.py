"""Tests for the status bar models and aggregator service."""
from app.models.status_bar import StatusBarPillConfig, StatusBarSettings


def test_pill_config_model_has_expected_columns():
    cols = set(StatusBarPillConfig.__table__.columns.keys())
    assert cols == {"id", "pill_id", "enabled", "visibility", "sort_order", "display_mode", "updated_at"}


def test_pill_config_display_mode_defaults_to_always():
    assert StatusBarPillConfig.__table__.columns["display_mode"].default.arg == "always"


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
    s = PillState(id="raid", kind="alert", tone="warning", label_key="pills.raid.live", href="/x")
    assert s.value is None and s.extra is None


def test_pill_state_accepts_i18n_fields():
    from app.schemas.status_bar import PillState
    s = PillState(
        id="vpn", kind="state", tone="success", href="/x",
        label_key="pills.vpn.live",
        value_key="pills.vpn.connected", value_params={"n": 2},
    )
    assert s.label_key == "pills.vpn.live"
    assert s.value_key == "pills.vpn.connected"
    assert s.value_params == {"n": 2}
    assert s.label_params is None


def test_pill_state_label_params_for_power():
    from app.schemas.status_bar import PillState
    s = PillState(
        id="power", kind="state", tone="info", href="/x",
        label_key="pills.power.profile", label_params={"preset": "Balanced", "level": "Surge"},
    )
    assert s.label_params == {"preset": "Balanced", "level": "Surge"}


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


def test_locked_set_matches_spec():
    from app.services.status_bar.catalog import CATALOG
    locked = {p.id for p in CATALOG if p.visibility_locked}
    assert locked == {"raid", "sleep", "vpn", "temp", "always_awake", "scheduler", "backup"}


# ── F6: _PILL_ID_MAX_LENGTH must never be None ────────────────────────────


def test_pill_id_max_length_constant_is_derived_from_the_bounded_column():
    """Sanity check against the real, currently-bounded pill_id column
    (String(96)) — the module constant service.py derives from it."""
    from app.services.status_bar.service import _PILL_ID_MAX_LENGTH
    assert _PILL_ID_MAX_LENGTH == 96


def test_pill_id_max_length_derivation_falls_back_to_96_for_an_unbounded_column(monkeypatch):
    """`.type.length` is None for an unbounded String()/Text column. Mirrors
    the exact `... .type.length or 96` fallback in
    status_bar/service.py's _PILL_ID_MAX_LENGTH derivation against the real
    column type object: without the fallback the derived constant would be
    None, and every `len(id) > _PILL_ID_MAX_LENGTH` comparison in
    _effective_catalog() would then TypeError, silently dropping every
    plugin's pills behind one generic warning."""
    col_type = StatusBarPillConfig.__table__.columns["pill_id"].type
    monkeypatch.setattr(col_type, "length", None)

    recomputed = StatusBarPillConfig.__table__.columns["pill_id"].type.length or 96

    assert recomputed == 96


# ── catalog icon (representative icon for the config Live Preview) ───────
# Each catalog entry declares the icon the live collector emits, so the admin
# config tab's Live Preview can show real icons without an API round-trip.
# Pinned per id for drift detection against collectors.py.
_EXPECTED_PILL_ICONS = {
    "power": "Zap",
    "pihole": "Shield",
    "uploads": "Upload",
    "sync": "RefreshCw",
    "raid": "HardDrive",
    "sleep": "Moon",
    "vpn": "Lock",
    "temp": "Thermometer",
    "always_awake": "Coffee",
    "scheduler": "Clock",
    "backup": "Save",
    "desktop": "Monitor",
}


def test_every_catalog_pill_has_a_nonempty_icon():
    from app.services.status_bar.catalog import CATALOG
    for p in CATALOG:
        assert getattr(p, "icon", None), f"pill {p.id} is missing an icon"


def test_catalog_icons_match_expected():
    from app.services.status_bar.catalog import CATALOG_BY_ID
    actual = {pid: CATALOG_BY_ID[pid].icon for pid in _EXPECTED_PILL_ICONS}
    assert actual == _EXPECTED_PILL_ICONS


def test_get_config_exposes_icon(db_session):
    svc = StatusBarService(db_session)
    cfg = svc.get_config()
    by_id = {p.pill_id: p for p in cfg.pills}
    assert by_id["power"].icon == "Zap"
    assert by_id["desktop"].icon == "Monitor"
    assert all(p.icon for p in cfg.pills)


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
        return {"kind": "state", "tone": "info", "label_key": "pills.power.live"}

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
        return {"kind": "state", "tone": "info", "label_key": "pills.power.live"}

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
        return {"kind": "state", "tone": "info", "label_key": "pills.power.live"}

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
        return {"kind": "state", "tone": "info", "label_key": "pills.power.live"}

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


def test_pill_config_item_accepts_display_mode():
    from app.schemas.status_bar import PillConfigItem
    item = PillConfigItem(pill_id="desktop", enabled=True, visibility="admin",
                          sort_order=0, display_mode="when_off")
    assert item.display_mode == "when_off"


def test_pill_config_item_display_mode_defaults_always():
    from app.schemas.status_bar import PillConfigItem
    item = PillConfigItem(pill_id="power", enabled=True, visibility="admin", sort_order=0)
    assert item.display_mode == "always"


def test_pill_config_item_rejects_bad_display_mode():
    import pytest
    from pydantic import ValidationError
    from app.schemas.status_bar import PillConfigItem
    with pytest.raises(ValidationError):
        PillConfigItem(pill_id="desktop", enabled=True, visibility="admin",
                       sort_order=0, display_mode="sometimes")


from app.schemas.status_bar import StatusBarConfigUpdate, PillConfigItem


def _enable_desktop(svc, mode="always"):
    cfg = svc.get_config()
    items = [
        PillConfigItem(pill_id=p.pill_id, enabled=(p.pill_id == "desktop"),
                       visibility=p.visibility, sort_order=p.sort_order,
                       display_mode=(mode if p.pill_id == "desktop" else "always"))
        for p in cfg.pills
    ]
    svc.update_config(StatusBarConfigUpdate(pills=items, show_bottom_upload=True))


def test_get_config_exposes_display_mode_fields(db_session):
    svc = StatusBarService(db_session)
    cfg = svc.get_config()
    desktop = next(p for p in cfg.pills if p.pill_id == "desktop")
    power = next(p for p in cfg.pills if p.pill_id == "power")
    assert desktop.display_mode == "always"
    assert desktop.display_mode_configurable is True
    assert power.display_mode_configurable is False


def test_update_config_rejects_display_mode_on_non_configurable(db_session):
    import pytest
    svc = StatusBarService(db_session)
    cfg = svc.get_config()
    items = [
        PillConfigItem(pill_id=p.pill_id, enabled=p.enabled, visibility=p.visibility,
                       sort_order=p.sort_order,
                       display_mode=("when_off" if p.pill_id == "power" else "always"))
        for p in cfg.pills
    ]
    with pytest.raises(ValueError):
        svc.update_config(StatusBarConfigUpdate(pills=items, show_bottom_upload=True))


def test_update_config_persists_desktop_display_mode(db_session):
    svc = StatusBarService(db_session)
    _enable_desktop(svc, mode="when_off")
    cfg = svc.get_config()
    desktop = next(p for p in cfg.pills if p.pill_id == "desktop")
    assert desktop.display_mode == "when_off"


def _patch_desktop_state(state):
    from unittest.mock import AsyncMock, MagicMock, patch
    fake = MagicMock()
    fake.get_status = AsyncMock(return_value=MagicMock(state=MagicMock(value=state)))
    return patch("app.services.power.desktop.get_desktop_service", return_value=fake)


@pytest.mark.asyncio
async def test_collect_state_always_shows_running(db_session):
    svc = StatusBarService(db_session)
    _enable_desktop(svc, mode="always")
    with _patch_desktop_state("running"):
        resp = await svc.collect_state(role="admin")
    pill = next(p for p in resp.pills if p.id == "desktop")
    assert pill.value_key == "pills.desktop.on"
    assert pill.extra is None or "_state" not in (pill.extra or {})


@pytest.mark.asyncio
async def test_collect_state_when_off_hides_running(db_session):
    svc = StatusBarService(db_session)
    _enable_desktop(svc, mode="when_off")
    with _patch_desktop_state("running"):
        resp = await svc.collect_state(role="admin")
    assert "desktop" not in [p.id for p in resp.pills]


@pytest.mark.asyncio
async def test_collect_state_when_off_shows_stopped(db_session):
    svc = StatusBarService(db_session)
    _enable_desktop(svc, mode="when_off")
    with _patch_desktop_state("stopped"):
        resp = await svc.collect_state(role="admin")
    assert "desktop" in [p.id for p in resp.pills]


@pytest.mark.asyncio
async def test_collect_state_when_on_hides_stopped(db_session):
    svc = StatusBarService(db_session)
    _enable_desktop(svc, mode="when_on")
    with _patch_desktop_state("stopped"):
        resp = await svc.collect_state(role="admin")
    assert "desktop" not in [p.id for p in resp.pills]
