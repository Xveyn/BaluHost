# Client mDNS Setup Guide

This guide explains how to configure different client devices (Windows, Mac, Linux, Mobile) to access BaluHost via the hostname `baluhost.local` instead of using IP addresses.

## Table of Contents

- [Overview](#overview)
- [Server Requirements](#server-requirements)
- [Client Setup by Platform](#client-setup-by-platform)
  - [Mac/macOS](#macmacos)
  - [Linux](#linux)
  - [Windows](#windows)
  - [iOS (iPhone/iPad)](#ios-iphoneipad)
  - [Android](#android)
- [Troubleshooting](#troubleshooting)
- [Testing mDNS Resolution](#testing-mdns-resolution)

---

## Overview

**What is mDNS?**

mDNS (Multicast DNS) is a protocol that allows devices on a local network to discover each other using `.local` hostnames without requiring a DNS server. It's also known as:
- **Bonjour** (Apple's implementation)
- **Avahi** (Linux implementation)
- **Zeroconf** (Zero-configuration networking)

**Why use mDNS?**

Instead of accessing BaluHost via:
```
http://192.168.1.100:5173
```

You can use a friendly hostname:
```
http://baluhost.local
```

This makes access easier and eliminates the need to remember IP addresses, especially useful when:
- The server IP changes (DHCP)
- You have multiple devices accessing BaluHost
- You want bookmarks/shortcuts that always work

---

## Server Requirements

Before configuring clients, ensure the BaluHost server has mDNS enabled:

1. **Server OS**: Linux (recommended for production)
2. **Avahi installed**: Run `deploy/scripts/install-avahi.sh` or `deploy/scripts/setup-hostname.sh`
3. **Backend configured**: `MDNS_HOSTNAME=baluhost` in `.env` (default value)
4. **Network Discovery enabled**: Automatically starts with BaluHost backend

Verify server is broadcasting mDNS:
```bash
# On the server
avahi-browse -a -t | grep baluhost
```

---

## Client Setup by Platform

### Mac/macOS

**✅ Works automatically** - macOS has native Bonjour support built-in.

#### Verification

```bash
# Test hostname resolution
ping baluhost.local

# Browse available services
dns-sd -B _baluhost._tcp local.
```

#### Access BaluHost

Open your browser and navigate to:
```
http://baluhost.local
```

**Note**: If using Nginx reverse proxy on port 80, otherwise use:
```
http://baluhost.local:5173  (Frontend)
http://baluhost.local:8000  (Backend API)
```

---

### Linux

**✅ Works automatically** - Most modern Linux distributions include Avahi by default.

#### Check if Avahi is installed

```bash
# Check if avahi-daemon is running
systemctl status avahi-daemon

# If not installed:
sudo apt install avahi-daemon avahi-utils  # Debian/Ubuntu
sudo dnf install avahi avahi-tools         # Fedora/RHEL
sudo pacman -S avahi nss-mdns              # Arch
```

#### Enable NSS-mDNS (if needed)

Some distributions require NSS-mDNS for `.local` resolution:

```bash
# Edit /etc/nsswitch.conf
sudo nano /etc/nsswitch.conf

# Ensure the "hosts" line includes "mdns4_minimal":
hosts: files mdns4_minimal [NOTFOUND=return] dns mdns4

# Restart Avahi
sudo systemctl restart avahi-daemon
```

#### Verification

```bash
# Test hostname resolution
ping baluhost.local

# Browse services
avahi-browse -a -t | grep baluhost
```

#### Access BaluHost

```
http://baluhost.local
```

---

### Windows

**❌ Does not work by default** - Windows does not include native mDNS support.

You have **three options**:

---

#### Option 1: Install Bonjour Print Services (Recommended)

This is the official Apple mDNS client for Windows.

**Download**:
- [Bonjour Print Services for Windows](https://support.apple.com/kb/DL999)
- Official Apple download (free, ~2 MB)

**Installation**:
1. Download and run the installer
2. Follow the installation wizard
3. Restart your computer (recommended)
4. Test: `ping baluhost.local` in Command Prompt

**Pros**:
- ✅ Official Apple implementation
- ✅ Works system-wide for all apps
- ✅ Automatic, no manual configuration

**Cons**:
- ❌ Requires admin rights to install
- ❌ Additional software dependency

---

#### Option 2: Manual Hosts File Entry (Simple Alternative)

Add a static entry to Windows hosts file to resolve `baluhost.local`.

**Steps**:

1. **Get BaluHost server IP address**:
   - On server: `ip addr show | grep "inet "`
   - Or check router DHCP leases
   - Example: `192.168.1.100`

2. **Edit hosts file as Administrator**:
   ```powershell
   # Open Notepad as Administrator
   notepad C:\Windows\System32\drivers\etc\hosts
   ```

3. **Add entry**:
   ```
   # BaluHost mDNS hostname
   192.168.1.100  baluhost baluhost.local
   ```

4. **Save and close**

5. **Test**:
   ```powershell
   ping baluhost
   ping baluhost.local
   ```

**Pros**:
- ✅ No additional software needed
- ✅ Fast and simple
- ✅ Works immediately

**Cons**:
- ❌ Manual update needed if server IP changes
- ❌ Requires admin rights to edit
- ❌ Must be configured on each Windows PC

---

#### Option 3: Router DNS Configuration (Best for Multiple Devices)

Configure your router to assign a hostname to the BaluHost server.

**Steps** (varies by router model):

1. **Access router admin panel**:
   - Common addresses: `192.168.1.1`, `192.168.0.1`, `192.168.178.1`

2. **Find DHCP Settings** or **Static Leases**

3. **Create DHCP Reservation**:
   - MAC Address: (BaluHost server's network card MAC)
   - IP Address: `192.168.1.100` (choose a static IP)
   - Hostname: `baluhost`

4. **Save and restart router** (if required)

5. **Test from Windows**:
   ```powershell
   ping baluhost
   ```

**Pros**:
- ✅ Works for all devices on the network automatically
- ✅ No client-side configuration needed
- ✅ IP remains static

**Cons**:
- ❌ Router-specific configuration
- ❌ Requires router admin access
- ❌ May not support `.local` suffix (depends on router)

---

### iOS (iPhone/iPad)

**✅ Works automatically** - iOS has native Bonjour support.

#### Access BaluHost

1. Open Safari (or any browser)
2. Navigate to: `http://baluhost.local`
3. Bookmark for easy access

#### Verification

You can use network utility apps to verify mDNS services:
- [Discovery - DNS-SD Browser](https://apps.apple.com/app/discovery-dns-sd-browser/id1381004916) (Free)

**Note**: The BaluHost mobile app includes automatic server discovery and does not require manual hostname configuration.

---

### Android

**⚠️ Varies by version and manufacturer**

- **Android 5.0 (Lollipop) and later**: Generally supports mDNS
- **Older versions**: May not support `.local` resolution

#### Test Support

1. **Install network utilities app**:
   - [Network Tools](https://play.google.com/store/apps/details?id=net.he.networktools) (Free)
   - [Network Discovery](https://play.google.com/store/apps/details?id=info.lamatricexiste.network) (Free)

2. **Try ping test**:
   ```
   ping baluhost.local
   ```

3. **If it works**: Use `http://baluhost.local` in browser

4. **If it doesn't work**: Use IP address or configure via router DNS

#### Alternative: Use IP Address

BaluHost mobile app allows manual server entry via IP:
```
http://192.168.1.100:8000
```

---

## Troubleshooting

### Cannot resolve `baluhost.local`

**Symptoms**: `ping baluhost.local` fails with "Unknown host" or "Name not found"

**Solutions**:

1. **Verify server is broadcasting**:
   ```bash
   # On BaluHost server
   systemctl status avahi-daemon
   avahi-browse -a -t | grep baluhost
   ```

2. **Check network connectivity**:
   - Client and server on same network/VLAN?
   - Firewall blocking UDP port 5353?

3. **Restart Avahi on server**:
   ```bash
   sudo systemctl restart avahi-daemon
   ```

4. **Windows**: Install Bonjour or use hosts file (see above)

5. **Linux**: Ensure `mdns4_minimal` is in `/etc/nsswitch.conf`

6. **Check DNS suffix**:
   - Try without `.local`: `ping baluhost`
   - Try with explicit suffix: `ping baluhost.local.`

---

### Firewall Blocking mDNS

**Symptoms**: Server shows service published, but clients cannot discover

**Solution**:

**On server**:
```bash
# Allow mDNS traffic (UDP port 5353)
sudo ufw allow 5353/udp
# OR
sudo firewall-cmd --permanent --add-service=mdns
sudo firewall-cmd --reload
```

**On Windows client**:
```powershell
# Allow mDNS in Windows Firewall
New-NetFirewallRule -DisplayName "mDNS (UDP-In)" -Direction Inbound -Protocol UDP -LocalPort 5353 -Action Allow
```

---

### Multiple BaluHost Servers on Network

**Symptoms**: Confusion when multiple servers broadcast `baluhost.local`

**Solution**:

Configure unique hostnames per server:

1. **Edit `.env` on each server**:
   ```bash
   # Server 1
   MDNS_HOSTNAME=baluhost1

   # Server 2
   MDNS_HOSTNAME=baluhost2
   ```

2. **Restart backend**:
   ```bash
   systemctl restart baluhost-backend
   ```

3. **Access**:
   ```
   http://baluhost1.local
   http://baluhost2.local
   ```

---

### Slow Hostname Resolution

**Symptoms**: `ping baluhost.local` takes 5-10 seconds to resolve

**Cause**: DNS server timeout before falling back to mDNS

**Solution**:

**Linux**: Prioritize mDNS in `/etc/nsswitch.conf`:
```
# Before
hosts: files dns mdns4

# After (prioritize mDNS)
hosts: files mdns4_minimal [NOTFOUND=return] dns mdns4
```

**Windows**: Use hosts file for instant resolution (see Option 2 above)

---

## Testing mDNS Resolution

### Server-Side Tests

```bash
# 1. Check Avahi daemon status
systemctl status avahi-daemon

# 2. List published services
avahi-browse -a -t -r

# 3. Resolve own hostname
avahi-resolve -n baluhost.local

# 4. Check mDNS traffic (requires tcpdump)
sudo tcpdump -i any port 5353
```

### Client-Side Tests

**Mac/Linux**:
```bash
# Ping test
ping -c 4 baluhost.local

# DNS lookup
nslookup baluhost.local
dig baluhost.local

# Avahi browse (Linux only)
avahi-browse -r _baluhost._tcp
```

**Windows** (with Bonjour installed):
```powershell
# Ping test
ping baluhost.local

# DNS lookup
nslookup baluhost.local
```

---

## Advanced: Custom mDNS Configuration

### Change mDNS Hostname

Edit backend configuration:

**Option 1: Environment variable**:
```bash
export MDNS_HOSTNAME=mynas
```

**Option 2: `.env` file**:
```env
MDNS_HOSTNAME=mynas
```

**Option 3: Server-wide (via Avahi)**:
```bash
# Edit Avahi config
sudo nano /etc/avahi/avahi-daemon.conf

# Set hostname
[server]
host-name=mynas
```

Restart services:
```bash
sudo systemctl restart avahi-daemon
# Restart BaluHost backend
```

---

## Summary

| Platform | mDNS Support | Action Required |
|----------|-------------|-----------------|
| **macOS** | ✅ Native (Bonjour) | None - works automatically |
| **Linux** | ✅ Native (Avahi) | Ensure avahi-daemon is running |
| **Windows** | ❌ Not included | Install Bonjour or use hosts file |
| **iOS** | ✅ Native (Bonjour) | None - works automatically |
| **Android** | ⚠️ Varies | Test on your device, fallback to IP |

---

## Related Documentation

- [HEIMNETZ_SETUP.md](./HEIMNETZ_SETUP.md) - Complete home network setup guide
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Production deployment with Nginx
- [../deploy/scripts/install-avahi.sh](../deploy/scripts/install-avahi.sh) - Server-side Avahi installation
- [../deploy/scripts/setup-hostname.sh](../deploy/scripts/setup-hostname.sh) - Complete hostname setup script

---

## Support

If you encounter issues with mDNS discovery:

1. Check this troubleshooting guide first
2. Verify server-side mDNS is broadcasting (`avahi-browse -a -t`)
3. Test from a Mac/Linux device (known working mDNS support)
4. Open an issue on GitHub with:
   - Client OS and version
   - Output of `ping baluhost.local`
   - Server-side `avahi-browse` output

---

**Last Updated**: 2026-01-25
**BaluHost Version**: 1.3.0+
