# VPN Server Fix: Clients can't reach backend through WireGuard tunnel

## Problem
Android VPN clients connect to WireGuard successfully (tunnel established, handshake works), but HTTP requests to `192.168.178.29:8000` (the backend API) timeout when routed through the VPN tunnel. This happens on mobile data where the VPN tunnel is the only path to the LAN.

## Root Cause
The WireGuard server needs IP forwarding and NAT (MASQUERADE) to route VPN client traffic (10.8.0.0/24) to the local LAN (192.168.178.0/24). These rules are defined in the server config's PostUp/PostDown but may not be active.

## Diagnosis Steps

Run these commands on the server (SSH or local terminal):

```bash
# 1. Check if WireGuard interface is up
sudo wg show wg0

# 2. Check IP forwarding
sysctl net.ipv4.ip_forward
# Expected: net.ipv4.ip_forward = 1

# 3. Check iptables FORWARD and NAT rules
sudo iptables -L FORWARD -v -n | grep wg0
sudo iptables -t nat -L POSTROUTING -v -n | grep MASQUERADE

# 4. Check the current WireGuard config
sudo cat /etc/wireguard/wg0.conf

# 5. Check if the LAN interface is correct
ip route show default
# Note the "dev XXX" — this is the LAN interface (e.g., eth0, enp3s0, br0)

# 6. Test connectivity from server to itself via VPN IP
ping -c 1 10.8.0.1
curl -s http://127.0.0.1:8000/api/health
```

## Fix Steps

### If IP forwarding is disabled:
```bash
sudo sysctl -w net.ipv4.ip_forward=1
# Make persistent:
echo "net.ipv4.ip_forward = 1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### If iptables rules are missing:
```bash
# Find LAN interface name
LAN_IFACE=$(ip route show default | awk '/default/ {print $5}')
echo "LAN interface: $LAN_IFACE"

# Add rules manually
sudo iptables -A FORWARD -i wg0 -j ACCEPT
sudo iptables -A FORWARD -o wg0 -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo iptables -t nat -A POSTROUTING -o $LAN_IFACE -s 10.8.0.0/24 -j MASQUERADE
```

### If WireGuard config is missing PostUp/PostDown:
Check `app/core/config.py` — ensure `vpn_include_lan = True` (or the env var `VPN_INCLUDE_LAN=true`).

Then regenerate and apply the server config:
```bash
# Via the backend API (if accessible):
curl -X POST http://localhost:8000/api/vpn/apply-config -H "Authorization: Bearer <token>"

# Or restart WireGuard:
sudo wg-quick down wg0
sudo wg-quick up wg0
```

### If wg0 is completely down:
```bash
sudo wg-quick up wg0
```

## Backend Code Reference
- Server config generation: `app/services/vpn/service.py` — `generate_server_config()` (lines 105-147)
- PostUp rules are added when `settings.vpn_include_lan == True` (line 124)
- LAN interface auto-detection: `get_lan_interface()` (lines 77-102)
- Config application: `apply_server_config()` (lines 150-235)

## Verification
After applying fixes:
```bash
# From the server, simulate a VPN client reaching the backend:
# (This tests if traffic from 10.8.0.x can reach port 8000)
sudo ip netns exec ... # or just check from the Android app

# On Android: connect VPN on mobile data, open Dashboard — should show server online
```
