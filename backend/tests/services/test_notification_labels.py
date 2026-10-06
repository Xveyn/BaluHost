"""Notification texts must show readable labels, not internal identifiers.

Production showed "Geplante Aufgabe abgeschlossen: sync_check" and
"Das database_only Backup ..." - the scheduler job id and the backup enum
value went straight into the German template.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.backup import BackupBase
from app.schemas.scheduler import SCHEDULER_REGISTRY
from app.services.notifications import events
from app.services.notifications.labels import backup_type_label, scheduler_label


class TestSchedulerLabel:
    @pytest.mark.parametrize("name", sorted(SCHEDULER_REGISTRY))
    def test_every_registered_scheduler_has_a_label(self, name):
        # A job added to the registry without a label would fall back to the
        # raw id in production - fail here instead.
        label = scheduler_label(name)
        assert label != name
        assert "_" not in label

    def test_unknown_scheduler_falls_back_to_raw_name(self):
        assert scheduler_label("some_plugin_job") == "some_plugin_job"


class TestBackupTypeLabel:
    def test_every_allowed_backup_type_has_a_label(self):
        pattern = BackupBase.model_fields["backup_type"].metadata[0].pattern
        allowed = pattern.strip("^$()").split("|")
        assert allowed, "could not derive allowed backup types"
        for backup_type in allowed:
            label = backup_type_label(backup_type)
            assert label != backup_type
            assert "_" not in label

    def test_unknown_type_falls_back_to_raw_value(self):
        assert backup_type_label("snapshot") == "snapshot"


class TestEmittersPassLabels:
    @pytest.fixture
    def emitter(self):
        mock = MagicMock()
        with patch.object(events, "get_event_emitter", return_value=mock):
            yield mock

    def test_scheduler_completed_sync(self, emitter):
        events.emit_scheduler_completed_sync("sync_check")
        kwargs = emitter.emit_for_admins_sync.call_args.kwargs
        assert kwargs["scheduler_name"] == scheduler_label("sync_check")

    def test_scheduler_failed_sync(self, emitter):
        events.emit_scheduler_failed_sync("auto_update", "boom")
        kwargs = emitter.emit_for_admins_sync.call_args.kwargs
        assert kwargs["scheduler_name"] == scheduler_label("auto_update")
        assert kwargs["error"] == "boom"

    def test_backup_completed_sync(self, emitter):
        events.emit_backup_completed_sync("database_only", "101.3 MB")
        kwargs = emitter.emit_for_admins_sync.call_args.kwargs
        assert kwargs["backup_type"] == backup_type_label("database_only")

    def test_backup_failed_sync(self, emitter):
        events.emit_backup_failed_sync("files_only", "disk full")
        kwargs = emitter.emit_for_admins_sync.call_args.kwargs
        assert kwargs["backup_type"] == backup_type_label("files_only")

    @pytest.mark.asyncio
    async def test_async_variants(self):
        mock = MagicMock()
        mock.emit_for_admins = MagicMock(side_effect=_awaitable)
        with patch.object(events, "get_event_emitter", return_value=mock):
            await events.emit_scheduler_failed("smart_scan", "x")
            assert mock.emit_for_admins.call_args.kwargs["scheduler_name"] == (
                scheduler_label("smart_scan")
            )
            await events.emit_backup_completed("full", "1 MB")
            assert mock.emit_for_admins.call_args.kwargs["backup_type"] == (
                backup_type_label("full")
            )
            await events.emit_backup_failed("incremental", "x")
            assert mock.emit_for_admins.call_args.kwargs["backup_type"] == (
                backup_type_label("incremental")
            )


class TestRenderedTexts:
    def test_backup_message_has_no_raw_enum(self):
        config = events.EVENT_CONFIGS[events.EventType.BACKUP_COMPLETED]
        text = config.message_template.format(
            backup_type=backup_type_label("database_only"), size="1 MB"
        )
        assert "database_only" not in text

    def test_scheduler_title_has_no_raw_id(self):
        config = events.EVENT_CONFIGS[events.EventType.SCHEDULER_COMPLETED]
        text = config.title_template.format(scheduler_name=scheduler_label("sync_check"))
        assert "sync_check" not in text


async def _awaitable(*args, **kwargs):
    return None
