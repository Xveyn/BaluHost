#!/bin/bash
# BaluHost Daily PostgreSQL Backup
#
# Run via cron: 0 3 * * * /opt/baluhost/deploy/scripts/db-backup-daily.sh >> /var/log/baluhost/db-backup.log 2>&1
#
# Retention: 14 days (configurable via RETENTION_DAYS)

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/baluhost/backups/daily}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DB_NAME="${DB_NAME:-baluhost}"
DB_USER="${DB_USER:-baluhost}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="$BACKUP_DIR/baluhost-${TIMESTAMP}.sql.gz"

echo "[$(date -Iseconds)] Starting daily backup..."

# Create backup
pg_dump -U "$DB_USER" -h localhost "$DB_NAME" | gzip > "$BACKUP_FILE"

# Verify integrity
if ! gzip -t "$BACKUP_FILE" 2>/dev/null; then
    echo "ERROR: Backup file corrupt: $BACKUP_FILE" >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

# Check not empty
BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null || echo "0")
if [[ "$BACKUP_SIZE" -eq 0 ]]; then
    echo "ERROR: Backup file empty: $BACKUP_FILE" >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

# Rotate: delete backups older than retention period
find "$BACKUP_DIR" -name "baluhost-*.sql.gz" -mtime +"$RETENTION_DAYS" -delete

echo "[$(date -Iseconds)] Backup OK: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
