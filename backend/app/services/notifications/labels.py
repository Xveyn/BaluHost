"""Readable labels for identifiers that end up in notification texts.

Templates in ``events.py`` are German prose; dropping a scheduler job id
(``sync_check``) or a backup enum value (``database_only``) into them shows
the admin an internal name. Unknown values fall back to the raw string, so a
plugin-registered job still produces a notification - just an unpolished one.

``tests/services/test_notification_labels.py`` fails when a scheduler in
``SCHEDULER_REGISTRY`` or a backup type allowed by ``BackupBase`` has no label.
"""
from __future__ import annotations

SCHEDULER_LABELS: dict[str, str] = {
    "raid_scrub": "RAID-Scrub",
    "smart_scan": "SMART-Prüfung",
    "backup": "Automatisches Backup",
    "sync_check": "Sync-Prüfung",
    "notification_check": "Benachrichtigungsprüfung",
    "upload_cleanup": "Upload-Bereinigung",
    "auto_update": "Update-Prüfung",
    "cloud_sync": "Cloud-Synchronisation",
    "file_activity_cleanup": "Aktivitätsbereinigung",
    "plugin_update_check": "Plugin-Update-Prüfung",
    "system_reboot": "Geplanter Neustart",
}

BACKUP_TYPE_LABELS: dict[str, str] = {
    "full": "Vollständig",
    "incremental": "Inkrementell",
    "database_only": "Nur Datenbank",
    "files_only": "Nur Dateien",
}


def scheduler_label(name: str) -> str:
    """German display name for a scheduler job id, or *name* if unknown."""
    return SCHEDULER_LABELS.get(name, name)


def backup_type_label(backup_type: str) -> str:
    """German display name for a backup type, or *backup_type* if unknown."""
    return BACKUP_TYPE_LABELS.get(backup_type, backup_type)
