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
    """Minimal stand-in — the service only needs these methods."""

    def __init__(self, result=None, hang: bool = False, boom: bool = False):
        self._result, self._hang, self._boom = result, hang, boom

    def get_status_pills(self):
        return [StatusPillSpec(
            id="session", icon="Gamepad2", href="/plugins",
            name_key="pill.name", name_text="Gaming Session",
        )]

    def get_translations(self):
        # A real PluginBase subclass would return this from a concrete,
        # always-present method — no try/except is needed around the call.
        return {"en": {"pill_name": "Gaming Session"}}

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
    # Finding I-5: a real plugin's get_translations() must reach the config entry.
    assert entry.translations == {"en": {"pill_name": "Gaming Session"}}


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
    # Finding I-5: a real plugin's get_translations() must reach the pill state.
    assert pill.translations == {"en": {"pill_name": "Gaming Session"}}


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
    """Finding I-3: the double must return a *valid* pill so a missing timeout
    would actually produce a pill (and fail this test) instead of accidentally
    passing because `result` was None either way."""
    import time

    from app.services.status_bar import service as svc
    monkeypatch.setattr(svc, "PLUGIN_COLLECTOR_TIMEOUT_SECONDS", 0.05)
    with_plugin(_FakePlugin(hang=True, result={
        "kind": "state", "tone": "info",
        "label_key": "pill.session", "label_text": "Gaming Session",
        "value": "should never appear", "icon": "Gamepad2",
    }))

    start = time.monotonic()
    state = await svc.StatusBarService(db_session).collect_state("admin")
    elapsed = time.monotonic() - start

    assert all(not p.id.startswith("plugin:") for p in state.pills)
    assert elapsed < 1.0, "the 0.05s timeout must cut the hang off well before the 30s sleep completes"


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


# ── C-1: composed ids that would overflow the pill_id column are dropped ──


def test_a_composed_pill_id_that_exceeds_the_column_width_is_skipped(db_session, monkeypatch, caplog):
    """`plugin:<name>:<suffix>` for a very long plugin name must not reach
    _ensure_rows()'s INSERT — on PostgreSQL that would raise DataError and
    500 both get_config() and collect_state()."""
    from app.services.status_bar import service as svc

    # "plugin:" (7) + 200 + ":" (1) + "session" (7) = 215 chars, over any
    # sane column width regardless of the exact number chosen for the fix.
    long_name = "n" * 200
    monkeypatch.setattr(svc, "iter_enabled_plugins", lambda: [(long_name, _FakePlugin())])

    with caplog.at_level("WARNING"):
        entries = svc.StatusBarService(db_session).get_config().pills

    assert all(not e.pill_id.startswith("plugin:") for e in entries)
    assert any(long_name in r.message for r in caplog.records)


async def test_a_composed_pill_id_that_exceeds_the_column_width_does_not_break_collect_state(
    db_session, monkeypatch,
):
    """The long name still matches the plugin:<name>:<suffix> *shape* — only
    the length is the problem — so give the collector a real payload. A
    plugin with the default (None) result would pass this assertion
    trivially even without the guard, the same flaw fixed in I-3."""
    from app.services.status_bar import service as svc

    long_name = "n" * 200
    plugin = _FakePlugin(result={
        "kind": "state", "tone": "info",
        "label_key": "pill.session", "label_text": "Gaming Session",
        "value": "should never appear", "icon": "Gamepad2",
    })
    monkeypatch.setattr(svc, "iter_enabled_plugins", lambda: [(long_name, plugin)])

    state = await svc.StatusBarService(db_session).collect_state("admin")

    assert all(not p.id.startswith("plugin:") for p in state.pills)


# ── I-1: a plugin name outside [a-z0-9_]+ must not 500 the config endpoint ──


def test_a_non_conforming_plugin_name_is_skipped_not_raised(db_session, monkeypatch, caplog):
    """PluginMetadata.name is not pattern-validated anywhere; a plugin
    directory named "my-plugin" must be skipped with a warning rather than
    raising a ValidationError out of PillCatalogEntry(...)."""
    from app.services.status_bar import service as svc

    monkeypatch.setattr(svc, "iter_enabled_plugins", lambda: [("my-plugin", _FakePlugin())])

    with caplog.at_level("WARNING"):
        entries = svc.StatusBarService(db_session).get_config().pills

    assert all(not e.pill_id.startswith("plugin:") for e in entries)
    assert any("my-plugin" in r.message for r in caplog.records)


async def test_a_non_conforming_plugin_name_does_not_break_collect_state(db_session, monkeypatch):
    from app.services.status_bar import service as svc

    monkeypatch.setattr(svc, "iter_enabled_plugins", lambda: [("my-plugin", _FakePlugin())])

    state = await svc.StatusBarService(db_session).collect_state("admin")

    assert all(not p.id.startswith("plugin:") for p in state.pills)


def test_get_config_skips_a_catalog_entry_that_fails_pydantic_construction(db_session, monkeypatch, caplog):
    """Belt-and-braces per I-1: even if an invalid PillDefinition reaches
    get_config() by some other path (bypassing the _effective_catalog guard
    entirely, simulated here), PillCatalogEntry(...) construction must be
    wrapped so one bad entry cannot take down the whole config response."""
    from app.services.status_bar import service as svc
    from app.services.status_bar.catalog import PillDefinition

    bad = PillDefinition(
        id="plugin:not a valid id",  # sidesteps the pill-id-shape guard entirely
        name_key="pill.name",
        default_visibility="admin",
        visibility_locked=False,
        silent_when_ok=True,
        href="/plugins",
        icon="Gamepad2",
        plugin_name="whatever",
        name_text="Bad Pill",
    )
    original = svc.StatusBarService._effective_catalog
    monkeypatch.setattr(
        svc.StatusBarService, "_effective_catalog",
        lambda self: original(self) + [bad],
    )

    with caplog.at_level("WARNING"):
        entries = svc.StatusBarService(db_session).get_config().pills

    assert all(e.pill_id != bad.id for e in entries)
    # Core pills must still be present — one bad entry must not 5xx the rest.
    assert any(e.pill_id == "power" for e in entries)
    # The warning is the only operator-facing signal that a pill silently
    # vanished from the config response — pin that it's actually logged.
    assert "produced an invalid catalog entry" in caplog.text


# ── I-2: get_status_pills() returning None must not TypeError the iteration ──


class _NonePillsPlugin:
    """A minimal/duck-typed plugin whose get_status_pills() forgot a `return`."""

    def get_status_pills(self):
        return None

    def get_translations(self):
        return None

    async def collect_status_pill(self, pill_id, db):
        return None


def test_a_plugin_returning_none_from_get_status_pills_does_not_break_get_config(db_session, monkeypatch):
    from app.services.status_bar import service as svc

    monkeypatch.setattr(svc, "iter_enabled_plugins", lambda: [("steam_gaming", _NonePillsPlugin())])

    entries = svc.StatusBarService(db_session).get_config().pills

    assert any(e.pill_id == "power" for e in entries)
    assert all(not e.pill_id.startswith("plugin:") for e in entries)


async def test_a_plugin_returning_none_from_get_status_pills_does_not_break_collect_state(db_session, monkeypatch):
    from app.services.status_bar import service as svc

    monkeypatch.setattr(svc, "iter_enabled_plugins", lambda: [("steam_gaming", _NonePillsPlugin())])

    state = await svc.StatusBarService(db_session).collect_state("admin")

    assert all(not p.id.startswith("plugin:") for p in state.pills)


# ── F2: update_config() must validate against the *effective* catalog ─────


class _LockedFakePlugin(_FakePlugin):
    """A plugin pill declared visibility_locked=True -- used to prove
    update_config() honours the lock for plugin pills, not just core ones."""

    def get_status_pills(self):
        return [StatusPillSpec(
            id="session", icon="Gamepad2", href="/plugins",
            name_key="pill.name", name_text="Gaming Session",
            default_visibility="admin", visibility_locked=True,
        )]


def test_update_config_enforces_visibility_locked_for_plugin_pills(db_session, with_plugin):
    """update_config() looked pills up in CATALOG_BY_ID (core-only), so a
    visibility_locked plugin pill's lock was silently skipped and could be
    flipped to visibility="all" through the admin API. Regression pin for
    that fix: it must now be validated against the effective catalog."""
    from app.schemas.status_bar import PillConfigItem, StatusBarConfigUpdate
    from app.services.status_bar.service import StatusBarService

    with_plugin(_LockedFakePlugin())
    svc = StatusBarService(db_session)
    svc.get_config()  # seed rows

    update = StatusBarConfigUpdate(
        pills=[PillConfigItem(
            pill_id="plugin:steam_gaming:session",
            enabled=True, visibility="all", sort_order=0,
        )],
        show_bottom_upload=True,
    )

    with pytest.raises(ValueError, match="visibility_locked"):
        svc.update_config(update)


# ── F3: _ensure_rows() must survive a concurrent-seed unique-constraint race ──


def test_ensure_rows_recovers_from_a_concurrent_seed_race(db_session, with_plugin, monkeypatch):
    """Simulates the multi-worker race: all four production workers can try
    to insert the same new plugin pill row concurrently, one wins and the
    others get IntegrityError out of commit(). The service must roll back,
    re-query, and return the config instead of 500ing the status poll /
    admin config page."""
    from sqlalchemy.exc import IntegrityError

    from app.models.status_bar import StatusBarPillConfig
    from app.services.status_bar.service import StatusBarService

    # Seed core pills first (no plugin yet), so the plugin pill is the only
    # *new* row when the plugin is enabled below -- isolates the race to the
    # single contested INSERT, matching the real production scenario.
    StatusBarService(db_session).get_config()
    with_plugin(_FakePlugin())

    original_commit = db_session.commit
    calls = {"n": 0}

    def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            # Our own half-applied insert never lands -- IntegrityError aborts
            # the whole transaction -- so simulate a sibling worker's
            # identical INSERT having already won the race and durably
            # committed, by committing it here ourselves.
            db_session.rollback()
            db_session.add(StatusBarPillConfig(
                pill_id="plugin:steam_gaming:session",
                enabled=True, visibility="admin", sort_order=99,
            ))
            original_commit()
            raise IntegrityError("insert", {}, Exception("UNIQUE constraint failed"))
        return original_commit()

    monkeypatch.setattr(db_session, "commit", flaky_commit)

    entries = StatusBarService(db_session).get_config().pills  # must not raise

    assert any(e.pill_id == "plugin:steam_gaming:session" for e in entries)
    # Core pills seeded before the race must still be present.
    assert any(e.pill_id == "power" for e in entries)
