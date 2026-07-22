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
