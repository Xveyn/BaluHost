#!/bin/bash
# BaluHost WireGuard Server Setup
# One-time setup script — prerequisites: wg + wg-quick installed, backend running with server keys in DB.
#
# Usage: sudo bash deploy/scripts/setup-wireguard.sh [BALUHOST_USER]
#   BALUHOST_USER defaults to the current user ($SUDO_USER or $USER).

set -euo pipefail

BALUHOST_USER="${1:-${SUDO_USER:-$USER}}"
echo "==> BaluHost WireGuard setup (user: $BALUHOST_USER)"

# 1. Create /etc/wireguard/ with restrictive permissions
echo "[1/5] Creating /etc/wireguard/ ..."
mkdir -p /etc/wireguard
chmod 700 /etc/wireguard

# 2. Enable IP forwarding persistently
echo "[2/5] Enabling IP forwarding ..."
cat > /etc/sysctl.d/99-wireguard.conf <<'EOF'
net.ipv4.ip_forward = 1
EOF
sysctl -p /etc/sysctl.d/99-wireguard.conf

# 3. Install sudoers rules so the backend can manage WireGuard without full root
echo "[3/5] Installing sudoers rules ..."
cat > /etc/sudoers.d/baluhost-wireguard <<SUDOERS
# Allow BaluHost backend to manage WireGuard
${BALUHOST_USER} ALL=(root) NOPASSWD: /usr/bin/wg syncconf wg0 *
${BALUHOST_USER} ALL=(root) NOPASSWD: /usr/bin/wg-quick up wg0
${BALUHOST_USER} ALL=(root) NOPASSWD: /usr/bin/wg-quick down wg0
${BALUHOST_USER} ALL=(root) NOPASSWD: /usr/bin/wg-quick strip wg0
${BALUHOST_USER} ALL=(root) NOPASSWD: /usr/bin/wg show *
${BALUHOST_USER} ALL=(root) NOPASSWD: /usr/bin/tee /etc/wireguard/wg0.conf
${BALUHOST_USER} ALL=(root) NOPASSWD: /usr/bin/chmod 600 /etc/wireguard/wg0.conf
SUDOERS
chmod 440 /etc/sudoers.d/baluhost-wireguard
visudo -cf /etc/sudoers.d/baluhost-wireguard
echo "   Sudoers installed and validated."

# 4. Enable wg-quick@wg0 systemd service (does not start yet — config may not exist)
echo "[4/5] Enabling wg-quick@wg0 service ..."
systemctl enable wg-quick@wg0 || true

# 5. Pi-hole DNS entry (optional)
echo "[5/5] Checking for Pi-hole ..."
if command -v pihole &>/dev/null; then
    if ! grep -q "baluhost.local" /etc/pihole/custom.list 2>/dev/null; then
        echo "10.8.0.1 baluhost.local" >> /etc/pihole/custom.list
        pihole restartdns
        echo "   Pi-hole DNS entry added: baluhost.local -> 10.8.0.1"
    else
        echo "   Pi-hole DNS entry already exists."
    fi
else
    echo "   Pi-hole not found — skipping DNS entry."
fi

echo ""
echo "==> WireGuard setup complete."
echo "    Next steps:"
echo "    1. Generate a VPN client in the BaluHost UI (creates server keys in DB)"
echo "    2. Trigger server config sync: POST /api/vpn/sync-server"
echo "       Or restart the backend — it will apply on next client change."
echo "    3. Verify: sudo wg show"
