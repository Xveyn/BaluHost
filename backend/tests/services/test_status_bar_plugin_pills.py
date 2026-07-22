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
