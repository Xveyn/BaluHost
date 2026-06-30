"""Mobile model timestamp columns must be timezone-aware (#241).

models/CLAUDE.md convention: "Timestamps: DateTime(timezone=True)". mobile.py
predates this convention; columns were plain DateTime (naive), which was the
root cause of #241's TypeError-on-comparison bugs against aware datetime.now().
"""
from app.models.mobile import (
    CameraBackup,
    ExpirationNotification,
    MobileDevice,
    MobileRegistrationToken,
    SyncFolder,
    UploadQueue,
)

EXPECTED_AWARE_COLUMNS = {
    MobileDevice: ["last_seen", "last_sync", "expires_at", "created_at", "updated_at"],
    MobileRegistrationToken: ["expires_at", "created_at"],
    CameraBackup: ["last_backup", "created_at", "updated_at"],
    SyncFolder: ["last_sync", "created_at", "updated_at"],
    UploadQueue: ["created_at", "started_at", "completed_at"],
    ExpirationNotification: ["sent_at", "device_expires_at"],
}


def test_mobile_timestamp_columns_are_timezone_aware():
    for model, columns in EXPECTED_AWARE_COLUMNS.items():
        for col_name in columns:
            column = model.__table__.columns[col_name]
            assert column.type.timezone is True, (
                f"{model.__name__}.{col_name} must use DateTime(timezone=True) "
                f"per models/CLAUDE.md convention"
            )
