#!/bin/bash
# BaluHost: write logind idle-action settings via systemd drop-in.
#
# Usage: baluhost-write-logind-idle --timeout <seconds> --action <suspend|hibernate|ignore>
#
# Run as root via sudo NOPASSWD. Validates all inputs strictly. Writes
# /etc/systemd/logind.conf.d/baluhost-idle.conf atomically and reloads
# systemd-logind. On failure, restores the previous file (if any).

set -euo pipefail

CONF_PATH="/etc/systemd/logind.conf.d/baluhost-idle.conf"
CONF_DIR="$(dirname "$CONF_PATH")"
MIN_TIMEOUT=60
MAX_TIMEOUT=86400

usage() {
    echo "Usage: $0 --timeout <seconds> --action <suspend|hibernate|ignore>" >&2
    exit 2
}

TIMEOUT=""
ACTION=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --timeout)
            shift
            [[ $# -eq 0 ]] && usage
            TIMEOUT="$1"
            ;;
        --action)
            shift
            [[ $# -eq 0 ]] && usage
            ACTION="$1"
            ;;
        *)
            echo "ERROR: unexpected argument: $1" >&2
            usage
            ;;
    esac
    shift
done

# Validate timeout
if ! [[ "$TIMEOUT" =~ ^[0-9]+$ ]]; then
    echo "ERROR: --timeout must be a positive integer (seconds)" >&2
    exit 2
fi
if (( TIMEOUT < MIN_TIMEOUT || TIMEOUT > MAX_TIMEOUT )); then
    echo "ERROR: --timeout must be between $MIN_TIMEOUT and $MAX_TIMEOUT seconds" >&2
    exit 2
fi

# Validate action
case "$ACTION" in
    suspend|hibernate|ignore) ;;
    *)
        echo "ERROR: --action must be one of: suspend, hibernate, ignore" >&2
        exit 2
        ;;
esac

# Ensure target dir exists
mkdir -p "$CONF_DIR"

# Back up current config if it exists (for rollback)
BACKUP=""
if [[ -f "$CONF_PATH" ]]; then
    BACKUP="$(mktemp --tmpdir baluhost-idle-backup.XXXXXX)"
    cp "$CONF_PATH" "$BACKUP"
fi

# Atomic write via temp file in same FS
TMP="$(mktemp "${CONF_DIR}/.baluhost-idle.XXXXXX")"
cat > "$TMP" <<EOF
# Managed by BaluHost — do not edit by hand.
# Written by /usr/local/lib/baluhost/baluhost-write-logind-idle
[Login]
IdleAction=$ACTION
IdleActionSec=${TIMEOUT}s
EOF
chmod 644 "$TMP"
mv "$TMP" "$CONF_PATH"

# Reload logind
if ! systemctl reload systemd-logind 2>/dev/null; then
    # Rollback if reload fails
    if [[ -n "$BACKUP" ]]; then
        mv "$BACKUP" "$CONF_PATH"
        systemctl reload systemd-logind || true
    else
        rm -f "$CONF_PATH"
    fi
    echo "ERROR: systemctl reload systemd-logind failed; rolled back" >&2
    exit 1
fi

# Success: discard backup
[[ -n "$BACKUP" ]] && rm -f "$BACKUP"
exit 0
