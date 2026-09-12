"""Die vier Meldungen des geplanten Systemneustarts."""
from unittest.mock import MagicMock, patch

from app.services.notifications.events import (
    EVENT_CONFIGS,
    EventType,
    emit_reboot_completed_sync,
    emit_reboot_scheduled_sync,
    emit_reboot_skipped_sync,
    emit_reboot_started_sync,
)


def test_all_four_event_types_are_configured():
    for event in (
        EventType.REBOOT_SCHEDULED,
        EventType.REBOOT_STARTED,
        EventType.REBOOT_COMPLETED,
        EventType.REBOOT_SKIPPED,
    ):
        config = EVENT_CONFIGS[event]
        assert config.category == "lifecycle"
        assert config.title_template
        assert config.message_template


def test_no_cooldown_configured():
    """Ein geplanter Neustart muss immer melden — wie shutdown/startup."""
    from app.services.notifications.events import _COOLDOWN_SECONDS

    for event in (
        EventType.REBOOT_SCHEDULED,
        EventType.REBOOT_STARTED,
        EventType.REBOOT_COMPLETED,
        EventType.REBOOT_SKIPPED,
    ):
        assert event.value not in _COOLDOWN_SECONDS


def test_emitters_pass_their_placeholders():
    emitter = MagicMock()
    with patch("app.services.notifications.events.get_event_emitter", return_value=emitter):
        emit_reboot_scheduled_sync("Sonntag, 04:00")
        emit_reboot_started_sync()
        emit_reboot_completed_sync(downtime_seconds=132.0)
        emit_reboot_skipped_sync("Displays aktiv")

    calls = emitter.emit_for_admins_sync.call_args_list
    assert len(calls) == 4
    assert calls[0].kwargs["due_at_human"] == "Sonntag, 04:00"
    assert calls[2].kwargs["downtime_human"] == "2min 12s"
    assert calls[3].kwargs["reason_label"] == "Displays aktiv"


def test_templates_render_with_the_supplied_placeholders():
    """Fängt einen Platzhalter, den kein Emitter liefert."""
    cases = {
        EventType.REBOOT_SCHEDULED: {"due_at_human": "Sonntag, 04:00"},
        EventType.REBOOT_STARTED: {},
        EventType.REBOOT_COMPLETED: {"downtime_human": "2min"},
        EventType.REBOOT_SKIPPED: {"reason_label": "Displays aktiv"},
    }
    for event, placeholders in cases.items():
        config = EVENT_CONFIGS[event]
        config.title_template.format(**placeholders)
        config.message_template.format(**placeholders)


def test_trigger_label_exists():
    from app.services.notifications.lifecycle_helpers import german_trigger_label

    assert german_trigger_label("scheduled_reboot") == "geplanter Neustart"
