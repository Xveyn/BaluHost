"""log_event() must never raise on its details (#477).

The contract of AuditLoggerDB.log_event(): a failing audit write never takes the
caller down - many callers log right after an action that already happened
(e.g. the power routes after a hardware change). json.dumps(details) sat
outside that guard, so the first datetime in `details` would have turned a
completed action into a 500.
"""
import enum
import json
from datetime import datetime, timezone
from pathlib import PurePosixPath

from app.models.audit_log import AuditLog
from app.services.audit.logger_db import AuditLoggerDB


class _Mode(enum.Enum):
    TURBO = "turbo"


def test_datetime_in_details_does_not_raise_and_is_kept(db_session):
    when = datetime(2026, 9, 25, 14, 30, tzinfo=timezone.utc)

    entry = AuditLoggerDB().log_event(
        event_type="SYSTEM", user="admin", action="power_profile_changed",
        details={"at": when, "path": PurePosixPath("/srv/x"), "mode": _Mode.TURBO},
        db=db_session,
    )

    assert entry is not None
    stored = json.loads(db_session.get(AuditLog, entry.id).details)
    assert stored["at"] == str(when)
    assert stored["path"] == "/srv/x"
    assert stored["mode"] == str(_Mode.TURBO)


def test_unserializable_details_still_write_the_entry(db_session):
    # Tuple keys fail even with default=str. The action itself must still be
    # on record - an audit entry without details beats no audit entry.
    entry = AuditLoggerDB().log_event(
        event_type="SYSTEM", user="admin", action="odd_details",
        details={("a", "b"): 1},
        db=db_session,
    )

    assert entry is not None
    assert db_session.get(AuditLog, entry.id).action == "odd_details"
