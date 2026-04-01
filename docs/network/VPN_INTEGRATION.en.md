# VPN (WireGuard) Setup

BaluHost integrates WireGuard VPN for secure remote access to your NAS — even on the go.

## Prerequisites

- WireGuard must be installed on the server (production)
- Admin access to BaluHost
- WireGuard app on the client device (Windows, macOS, Linux, Android, iOS)

## Creating a VPN Client

1. Log in as admin
2. Navigate to **VPN** in the sidebar
3. Click **"Add client"**
4. Enter a name for the client (e.g., "Work Laptop", "Phone")
5. The configuration is automatically generated

### Transferring the Configuration

**Via QR code (mobile):**
- The QR code is displayed directly
- Open WireGuard app → "Add tunnel" → "Scan QR code"

**Via file (desktop):**
- Click "Download configuration"
- Import the `.conf` file in the WireGuard app

## Network Configuration

| Setting | Default |
|---------|---------|
| **Subnet** | 10.8.0.0/24 |
| **DNS** | Inherited from server |
| **Endpoint** | Server IP or DynDNS address |
| **Keepalive** | 25 seconds |

Each client automatically receives its own IP address in the VPN subnet.

## Client Management

On the VPN page you can:

- **List clients** — All registered VPN clients with status
- **Edit client** — Change name and settings
- **Delete client** — Revoke access
- **Show QR code again** — For re-setup

## Mobile App Integration

When registering a device via QR code (BaluApp), the VPN configuration can be embedded directly:

1. Devices page → "Register new device"
2. Enable the **"Include VPN configuration"** option
3. Scan the QR code with BaluApp
4. VPN is automatically configured in the app

## Security

- All VPN keys are stored encrypted (Fernet/AES-128-CBC)
- Each client has its own key pair (private key + public key)
- Preshared keys for additional security
- Private keys are never exposed in API responses or logs
- Encryption requires the `VPN_ENCRYPTION_KEY` environment variable

## Fritz!Box as VPN Server

If your Fritz!Box serves as WireGuard server:

1. Fritz!Box interface → Internet → Permits → VPN (WireGuard)
2. Set up connection → "Connect single device"
3. Download configuration file
4. Import in BaluHost or directly in the WireGuard app

## Troubleshooting

### VPN won't connect

1. Check if the WireGuard service is running on the server
2. Firewall: endpoint port must be open (default: 51820/UDP)
3. Endpoint address correct? (DynDNS or public IP)
4. Time synchronized on client and server?

### Connected but no access

1. Check AllowedIPs in the client configuration
2. Test DNS resolution: `nslookup baluhost.local`
3. Check IP routing on the server (`ip forwarding` enabled?)

### Slow connection

1. Low keepalive can help with NAT traversal (default: 25s)
2. MTU issues: set MTU to 1280 in WireGuard config

---

**Version:** 1.23.0  
**Last updated:** April 2026
