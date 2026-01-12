#!/usr/bin/env python3
"""Fix remaining print statements in notification_scheduler.py"""

from pathlib import Path

file_path = Path(__file__).parent.parent / "app" / "services" / "notification_scheduler.py"

content = file_path.read_text(encoding='utf-8')

# Replace remaining print statements
replacements = [
    ('print(f"\\n[NotificationScheduler] Starting expiration check at {datetime.now(timezone.utc)}")',
     'logger.info(f"[NotificationScheduler] Starting expiration check at {datetime.now(timezone.utc)}")'),

    ('print(f"\\n{\'=\'*60}")',
     'logger.info("="*60)'),

    ('print(f"{\'=\'*60}")',
     'logger.info("="*60)'),

    ('print(f"\\n[NotificationScheduler] Summary:")',
     'logger.info("[NotificationScheduler] Summary:")'),

    ('print(f"  - Devices checked: {stats[\'checked\']}")',
     'logger.info(f"  - Devices checked: {stats[\'checked\']}")'),

    ('print(f"  - Notifications sent: {stats[\'sent\']}")',
     'logger.info(f"  - Notifications sent: {stats[\'sent\']}")'),

    ('print(f"  - Skipped: {stats[\'skipped\']}")',
     'logger.info(f"  - Skipped: {stats[\'skipped\']}")'),

    ('print(f"  - Failed: {stats[\'failed\']}")',
     'logger.info(f"  - Failed: {stats[\'failed\']}")'),

    ('print(f"\\n[NotificationScheduler] Errors:")',
     'logger.warning("[NotificationScheduler] Errors:")'),

    ('print(f"  - {error}")',
     'logger.warning(f"  - {error}")'),
]

for old, new in replacements:
    content = content.replace(old, new)

file_path.write_text(content, encoding='utf-8')
print(f"[OK] Fixed {len(replacements)} print statements in notification_scheduler.py")
