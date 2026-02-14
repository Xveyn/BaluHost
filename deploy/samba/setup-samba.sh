#!/bin/bash
# BaluHost Samba Setup Script
# Run once on the production server to install and configure Samba.
#
# Usage: sudo bash setup-samba.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_USER="${SERVICE_USER:-sven}"
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
chown "$SERVICE_USER:$SERVICE_USER" "$SHARES_CONF"
chmod 644 "$SHARES_CONF"

# 4. Install sudoers
echo "[4/5] Installing sudoers rules..."
cp "$SCRIPT_DIR/baluhost-samba-sudoers" /etc/sudoers.d/baluhost-samba
chmod 440 /etc/sudoers.d/baluhost-samba
visudo -c

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
