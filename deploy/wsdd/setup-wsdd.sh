#!/bin/bash
# BaluHost WS-Discovery Setup Script
# Installs wsdd2 (or wsdd fallback) so Windows Explorer discovers BaluHost
# in "Network" via WS-Discovery (UDP 3702).
#
# Usage: sudo bash setup-wsdd.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKGROUP="WORKGROUP"  # Must match deploy/samba/smb.conf [global] workgroup

echo "=== BaluHost WS-Discovery Setup ==="

# 1. Install wsdd2 (preferred) or wsdd fallback
echo "[1/4] Installing WS-Discovery daemon..."
if apt-get install -y -qq wsdd2 2>/dev/null; then
    DAEMON="wsdd2"
    echo "  Installed wsdd2 (C implementation)"
elif apt-get install -y -qq wsdd 2>/dev/null; then
    DAEMON="wsdd"
    echo "  Installed wsdd (Python fallback)"
else
    echo "ERROR: Neither wsdd2 nor wsdd available in package repos."
    echo "  Try: apt-get update && apt-get install wsdd2"
    exit 1
fi

# 2. Configure workgroup via systemd drop-in override (only if non-default)
echo "[2/4] Configuring workgroup=${WORKGROUP}..."
if [ "$WORKGROUP" != "WORKGROUP" ]; then
    mkdir -p "/etc/systemd/system/${DAEMON}.service.d"
    cat > "/etc/systemd/system/${DAEMON}.service.d/override.conf" <<DROPIN
[Service]
ExecStart=
ExecStart=/usr/sbin/${DAEMON} -G ${WORKGROUP}
DROPIN
    systemctl daemon-reload
    echo "  Set workgroup to ${WORKGROUP} via systemd override"
else
    # Remove any stale override from previous runs
    rm -f "/etc/systemd/system/${DAEMON}.service.d/override.conf"
    rmdir --ignore-fail-on-non-empty "/etc/systemd/system/${DAEMON}.service.d" 2>/dev/null || true
    systemctl daemon-reload
    echo "  Using default workgroup (WORKGROUP)"
fi

# 3. Open firewall for WS-Discovery (UDP 3702)
echo "[3/4] Configuring firewall..."
if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
    ufw allow 3702/udp comment "WS-Discovery (wsdd)" >/dev/null
    echo "  UFW: allowed UDP 3702"
elif command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port=3702/udp >/dev/null
    firewall-cmd --reload >/dev/null
    echo "  firewalld: allowed UDP 3702"
else
    echo "  No active firewall detected, skipping"
fi

# 4. Enable and start service
echo "[4/4] Starting ${DAEMON}..."
systemctl enable "${DAEMON}"
systemctl restart "${DAEMON}"

echo ""
echo "=== WS-Discovery Setup Complete ==="
echo "${DAEMON} status: $(systemctl is-active "${DAEMON}")"
echo ""
echo "Windows Explorer should discover BaluHost in 'Network' within 1-2 minutes."
echo "Verify: systemctl status ${DAEMON}"
