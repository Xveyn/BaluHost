#!/bin/bash
# BaluHost Samba Setup Script
# Run once on the production server to install and configure Samba.
#
# Usage: sudo bash setup-samba.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_USER="${SERVICE_USER:-sven}"
STORAGE_GROUP="${STORAGE_GROUP:-baluhost}"
SHARES_CONF="/etc/samba/baluhost-shares.conf"

echo "=== BaluHost Samba Setup ==="

# 1. Install Samba
echo "[1/5] Installing Samba..."
apt-get update -qq
apt-get install -y -qq samba samba-common-bin

# 2. Backup and install smb.conf
echo "[2/5] Configuring Samba..."
if [ -f /etc/samba/smb.conf ]; then
    cp /etc/samba/smb.conf /etc/samba/smb.conf.bak.$(date +%Y%m%d%H%M%S)
fi
cp "$SCRIPT_DIR/smb.conf" /etc/samba/smb.conf

# 3. Create empty shares config (owned by service user)
echo "[3/5] Creating shares config..."
touch "$SHARES_CONF"
chown "$SERVICE_USER:$STORAGE_GROUP" "$SHARES_CONF"
chmod 644 "$SHARES_CONF"

# 4. Install sudoers
echo "[4/5] Installing sudoers rules..."
# Substitute the @@BALUHOST_USER@@ placeholder, validate in isolation, then
# install — never write an unvalidated file into /etc/sudoers.d (a malformed
# drop-in can break sudo system-wide).
SUDOERS_TMP=$(mktemp)
trap 'rm -f "$SUDOERS_TMP"' EXIT
sed "s|@@BALUHOST_USER@@|$SERVICE_USER|g" "$SCRIPT_DIR/baluhost-samba-sudoers" > "$SUDOERS_TMP"
if ! visudo -cf "$SUDOERS_TMP" >/dev/null 2>&1; then
    echo "ERROR: generated sudoers file fails visudo syntax check." >&2
    visudo -cf "$SUDOERS_TMP" || true
    exit 1
fi
install -m 440 -o root -g root "$SUDOERS_TMP" /etc/sudoers.d/baluhost-samba

# 5. Enable and start smbd
echo "[5/5] Starting Samba..."
systemctl enable smbd
systemctl restart smbd

echo ""
echo "=== Samba Setup Complete ==="
echo "smbd status: $(systemctl is-active smbd)"
echo "Version: $(smbd --version)"
echo ""
echo "Next steps:"
echo "  1. Enable SMB for users in BaluHost UI (System Control -> SMB/CIFS)"
echo "  2. Windows: net use Z: \\\\$(hostname -I | awk '{print $1}')\\BaluHost /user:admin"
