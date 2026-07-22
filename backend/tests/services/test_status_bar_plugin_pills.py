"""Plugin-contributed status-strip pills (spec 2026-07-22)."""

import pytest
from pydantic import ValidationError

from app.schemas.status_bar import CORE_PILL_IDS, PillState


def test_core_pill_ids_are_still_accepted():
    pill = PillState(id="power", kind="state", tone="info", label_key="x", href="/y")
    assert pill.id == "power"


def test_namespaced_plugin_pill_ids_are_accepted():
    pill = PillState(
        id="plugin:steam_gaming:session", kind="state", tone="info",
        label_key="pill.session", label_text="Gaming Session", href="/plugins",
    )
    assert pill.label_text == "Gaming Session"


def test_unknown_pill_ids_are_still_rejected():
    with pytest.raises(ValidationError):
        PillState(id="not_a_pill", kind="state", tone="info", label_key="x", href="/y")


def test_a_plugin_cannot_squat_a_core_id_shape():
    """Only the plugin: namespace is open — bare new ids stay closed."""
    with pytest.raises(ValidationError):
        PillState(id="gaming", kind="state", tone="info", label_key="x", href="/y")


def test_core_pill_ids_match_the_catalog():
    """Drift detection, replaces the old Literal-vs-catalog assertion."""
    from app.services.status_bar.catalog import CATALOG

    assert CORE_PILL_IDS == {p.id for p in CATALOG}


def test_plugin_base_declares_no_pills_by_default():
    from app.plugins.base import PluginBase

    assert PluginBase.get_status_pills(object()) == []  # type: ignore[arg-type]


# ── Finding 1: trailing-newline hole (Python `$` matches before a trailing \n) ──


def test_pill_config_item_rejects_trailing_newline():
    """Empirical regression for the specific hole the reviewer found: `$` (not
    anchored with \\Z / fullmatch) accepts a trailing newline. Checked against
    PillConfigItem.pill_id too, since it's the admin request-body field the
    validator also guards."""
    from app.schemas.status_bar import PillConfigItem

    with pytest.raises(ValidationError):
        PillConfigItem(pill_id="plugin:a:b\n", enabled=True, visibility="admin", sort_order=0)


# ── Finding 2: the plugin: namespace shape must be exactly what it claims ──


@pytest.mark.parametrize("bad_id", [
    "plugin::b",       # empty plugin-name segment
    "plugin:a:",        # empty suffix segment
    "plugin:a:b:c",      # extra segment
    "plugin:A:b",        # uppercase not allowed
    "plugin:a-b:c",      # hyphen not allowed
    "xplugin:a:b",       # not actually namespaced under "plugin:"
    "plugin:a:b\n",      # trailing newline (Finding 1)
    "plugin:a:b ",       # trailing space
])
def test_plugin_pill_id_shape_is_strictly_enforced(bad_id):
    with pytest.raises(ValidationError):
        PillState(id=bad_id, kind="state", tone="info", label_key="x", href="/y")


def test_plugin_pill_id_shape_accepts_the_canonical_form():
    """Positive control: the parametrized rejections above must not pass merely
    because the pattern rejects everything."""
    pill = PillState(id="plugin:a:b", kind="state", tone="info", label_key="x", href="/y")
    assert pill.id == "plugin:a:b"


# ── Finding 3: StatusPillSpec.id must be constrained at plugin-load time ──


def test_status_pill_spec_rejects_invalid_id_pattern():
    """A plugin declaring a spec id with characters the public namespaced id
    (plugin:<name>:<id>) can't accept must fail at construction, not surface
    as a ValidationError deep inside the admin config endpoint."""
    from app.plugins.base import StatusPillSpec

    with pytest.raises(ValidationError):
        StatusPillSpec(
            id="a:b", icon="Gamepad2", href="/plugins",
            name_key="pill.session", name_text="Gaming Session",
        )


def test_status_pill_spec_accepts_valid_id_pattern():
    from app.plugins.base import StatusPillSpec

    spec = StatusPillSpec(
        id="session", icon="Gamepad2", href="/plugins",
        name_key="pill.session", name_text="Gaming Session",
    )
    assert spec.id == "session"


# ── Part 2: StatusBarService merges plugin pills into the catalog ──────────

import asyncio

from app.plugins.base import StatusPillSpec


class _FakePlugin:
    """Minimal stand-in — the service only needs these two methods."""

    def __init__(self, result=None, hang: bool = False, boom: bool = False):
        self._result, self._hang, self._boom = result, hang, boom

    def get_status_pills(self):
        return [StatusPillSpec(
            id="session", icon="Gamepad2", href="/plugins",
            name_key="pill.name", name_text="Gaming Session",
        )]

    async def collect_status_pill(self, pill_id, db):
        if self._boom:
            raise RuntimeError("collector exploded")
        if self._hang:
            await asyncio.sleep(30)
        return self._result


@pytest.fixture
def with_plugin(monkeypatch):
    """Install a fake enabled plugin into the status bar service."""
    def _install(plugin):
        from app.services.status_bar import service as svc
        monkeypatch.setattr(svc, "iter_enabled_plugins",
                            lambda: [("steam_gaming", plugin)])
    return _install


def test_plugin_pill_appears_in_the_config(db_session, with_plugin):
    from app.services.status_bar.service import StatusBarService
    with_plugin(_FakePlugin())

    entries = StatusBarService(db_session).get_config().pills
    entry = next(e for e in entries if e.pill_id == "plugin:steam_gaming:session")

    assert entry.name_text == "Gaming Session"
    assert entry.icon == "Gamepad2"


def test_plugin_pills_start_enabled(db_session, with_plugin):
    """Deliberate deviation: core pills seed disabled, plugin pills do not."""
    from app.services.status_bar.service import StatusBarService
    with_plugin(_FakePlugin())

    entries = StatusBarService(db_session).get_config().pills
    plugin_entry = next(e for e in entries if e.pill_id.startswith("plugin:"))
    core_entry = next(e for e in entries if e.pill_id == "power")

    assert plugin_entry.enabled is True
    assert core_entry.enabled is False


async def test_plugin_pill_is_rendered_into_the_state(db_session, with_plugin):
    from app.services.status_bar.service import StatusBarService
    with_plugin(_FakePlugin(result={
        "kind": "state", "tone": "info",
        "label_key": "pill.session", "label_text": "Gaming Session",
        "value": "Metro Exodus", "icon": "Gamepad2",
    }))

    state = await StatusBarService(db_session).collect_state("admin")
    pill = next(p for p in state.pills if p.id == "plugin:steam_gaming:session")

    assert pill.value == "Metro Exodus"
    assert pill.label_text == "Gaming Session"


async def test_a_silent_plugin_collector_emits_no_pill(db_session, with_plugin):
    from app.services.status_bar.service import StatusBarService
    with_plugin(_FakePlugin(result=None))

    state = await StatusBarService(db_session).collect_state("admin")

    assert all(not p.id.startswith("plugin:") for p in state.pills)


async def test_a_throwing_plugin_collector_does_not_break_the_strip(db_session, with_plugin):
    from app.services.status_bar.service import StatusBarService
    with_plugin(_FakePlugin(boom=True))

    state = await StatusBarService(db_session).collect_state("admin")

    assert all(not p.id.startswith("plugin:") for p in state.pills)


async def test_a_hanging_plugin_collector_is_cut_off(db_session, with_plugin, monkeypatch):
    from app.services.status_bar import service as svc
    monkeypatch.setattr(svc, "PLUGIN_COLLECTOR_TIMEOUT_SECONDS", 0.05)
    with_plugin(_FakePlugin(hang=True))

    state = await svc.StatusBarService(db_session).collect_state("admin")

    assert all(not p.id.startswith("plugin:") for p in state.pills)


def test_a_disabled_plugin_drops_its_pill_but_keeps_the_settings(db_session, with_plugin, monkeypatch):
    from app.services.status_bar import service as svc
    with_plugin(_FakePlugin())
    svc.StatusBarService(db_session).get_config()  # seeds the row

    monkeypatch.setattr(svc, "iter_enabled_plugins", lambda: [])
    entries = svc.StatusBarService(db_session).get_config().pills
    assert all(not e.pill_id.startswith("plugin:") for e in entries)

    from app.models.status_bar import StatusBarPillConfig
    row = db_session.query(StatusBarPillConfig).filter(
        StatusBarPillConfig.pill_id == "plugin:steam_gaming:session"
    ).first()
    assert row is not None, "settings must survive a disabled plugin"
