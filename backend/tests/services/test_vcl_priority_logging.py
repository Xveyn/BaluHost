"""A blob that refuses to be deleted must not fail silently.

`cleanup_orphaned_blobs` swallows per-blob delete errors so one stuck blob
cannot abort the whole cleanup run. Reported via `print()` that was invisible
in the structured production log — and a silently failing blob delete means
storage that is never actually reclaimed. Follow-up to #308.
"""

import logging

from app.models.vcl import VersionBlob
from app.services.versioning import priority as priority_module
from app.services.versioning.priority import VCLPriorityMode


def test_failed_blob_delete_is_logged(db_session, monkeypatch, caplog):
    blob = VersionBlob(
        checksum="a" * 64,
        storage_path="/tmp/baluhost-test-blob",
        original_size=1024,
        compressed_size=512,
        reference_count=0,
    )
    db_session.add(blob)
    db_session.commit()

    mode = VCLPriorityMode(db_session)

    def _refuse_delete(_blob):
        raise RuntimeError("blob unlink failed")

    monkeypatch.setattr(mode.vcl_service, "delete_blob", _refuse_delete)

    with caplog.at_level(logging.WARNING, logger=priority_module.logger.name):
        result = mode.cleanup_orphaned_blobs(dry_run=False)

    # The run completes and honestly reports that nothing was freed.
    assert result["deleted_blobs"] == 0
    assert result["freed_bytes"] == 0

    messages = [
        r.getMessage() for r in caplog.records if r.name == priority_module.logger.name
    ]
    assert messages, "failed blob delete never reached the logger"
    assert any("blob unlink failed" in m for m in messages), messages
    assert any(str(blob.id) in m for m in messages), (
        f"log line does not identify which blob got stuck: {messages}"
    )
