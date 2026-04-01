# BaluHost User Guide

Welcome to BaluHost — your self-hosted NAS system. This guide will help you get started.

## Table of Contents

- [Access](#access)
- [Initial Setup (Setup Wizard)](#initial-setup-setup-wizard)
- [Dashboard](#dashboard)
- [File Management](#file-management)
- [File Sharing](#file-sharing)
- [User Management (Admin)](#user-management-admin)
- [RAID Management (Admin)](#raid-management-admin)
- [System Monitoring](#system-monitoring)
- [VPN (WireGuard)](#vpn-wireguard)
- [Network Access (Samba & WebDAV)](#network-access-samba--webdav)
- [Mobile App & Desktop Client](#mobile-app--desktop-client)
- [Notifications](#notifications)
- [Cloud Import](#cloud-import)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

---

## Access

BaluHost runs on your local server and is accessible via browser:

- **Local network:** `http://baluhost.local` (if mDNS configured) or `http://<server-ip>`
- **Remote:** Via WireGuard VPN (see [VPN](#vpn-wireguard))

Supported browsers: Chrome, Firefox, Edge, Safari (latest version recommended).

## Initial Setup (Setup Wizard)

On first launch, the Setup Wizard appears automatically and guides you through initial configuration:

**Required steps:**
1. **Administrator account** — Set username and password for the admin
2. **Users** — Create additional user accounts (optional, also possible later)
3. **RAID** — Configure disk arrays (can be skipped)
4. **File access** — Enable Samba (SMB) and/or WebDAV

**Optional steps:**
- File sharing, VPN, notifications, cloud import, Pi-hole, desktop sync, mobile app

You can skip optional steps and configure them later in Settings.

## Dashboard

The Dashboard provides a system overview:

- **Storage overview** — Total capacity, used/free space
- **RAID status** — Array health (Healthy, Degraded, Rebuilding)
- **System resources** — CPU, RAM, network in real-time
- **Recent activity** — Latest file operations and events

## File Management

### Navigation

- Click folders to navigate into them
- Breadcrumb navigation at the top for quick return
- Files show name, size, and modification date

### Uploading

- **Drag & Drop:** Drag files directly into the File Manager
- **Upload button:** Click "Upload" and select files
- **Folder upload:** Upload entire folders
- **Chunked upload:** Large files are automatically uploaded in chunks with progress indicator

### Other Operations

- **New folder** — Creates a subfolder
- **Preview** — Click a file to open preview (images, videos, audio, PDFs, text, code)
- **Download** — Download icon next to each file
- **Rename** — Via context menu (right-click)
- **Delete** — Via context menu or trash icon
- **Move/Copy** — Move or copy files between folders

### File Versioning

BaluHost maintains a version history for files. When files change, you can restore previous versions.

### Ownership

- Each file belongs to the user who uploaded it
- Only the owner or an admin can modify/delete files
- Admins have access to all files

## File Sharing

### Public Links

1. Right-click a file → "Create share"
2. Choose options: expiry date, password protection, download limit
3. Share the generated link

### User Shares

- Share files or folders with specific BaluHost users
- Shared files appear under "Shared with me"

## User Management (Admin)

Admins can manage accounts under **User Management**:

- **Create** — Username, email, password, role (Admin/User)
- **Edit** — Modify details, reset password
- **Delete** — Remove account (files are preserved)
- **Manage 2FA** — Enable/disable TOTP two-factor authentication per user

### Roles

| Role | Access |
|------|--------|
| **Admin** | Full access: all files, user management, RAID, system, VPN |
| **User** | Own files, shares, settings |

## RAID Management (Admin)

Under **RAID Management** you can see:

- Active RAID arrays with status (Healthy/Degraded/Rebuilding/Failed)
- Member disks and their condition
- SMART health data for each disk
- Resync progress during rebuilds

### RAID Status

| Status | Meaning | Action |
|--------|---------|--------|
| Healthy | All disks OK | None |
| Degraded | Disk failed, array still running | Replace disk & start rebuild |
| Rebuilding | Recovery in progress | Wait, performance reduced |
| Failed | Array not operational | Urgent action required |

## System Monitoring

**System Monitoring** shows real-time data:

- **CPU** — Utilization, frequency, temperature (per thread)
- **RAM** — Usage and availability
- **Network** — Download/upload speed
- **Disk I/O** — Read/write speed, IOPS
- **SMART** — Disk health, temperature, power-on hours

Historical data is displayed as charts. Retention is configurable.

## VPN (WireGuard)

BaluHost integrates WireGuard for secure remote access:

1. **VPN page** (Admin) → "Add client"
2. Scan the configuration via **QR code** (mobile) or **download file** (desktop)
3. Install WireGuard app on your device and import the profile

All VPN keys are stored encrypted (Fernet/AES).

## Network Access (Samba & WebDAV)

### Samba (SMB)

Mount as a Windows network drive:
1. Open Explorer → address bar: `\\baluhost.local\` or `\\<server-ip>\`
2. Log in with your BaluHost credentials

### WebDAV

Browser and WebDAV client access:
- URL: `http://baluhost.local:8080/webdav/` (port configurable)
- Authenticate with your BaluHost credentials

Both services are configured in the Setup Wizard or under **Settings**.

## Mobile App & Desktop Client

### BaluApp (Android)

1. Install the app
2. Scan the QR code on the BaluHost web interface (Devices page)
3. Automatic VPN pairing and authentication

### BaluDesk (Windows/Linux)

1. Install the desktop client
2. Enter the pairing code from the web interface
3. Configure sync folders for automatic synchronization

## Notifications

BaluHost can send push notifications to registered mobile devices:

- RAID warnings (Degraded, Failed)
- Storage almost full
- Failed backups
- Security events

Configure under **Settings → Notifications** (requires Firebase setup).

## Cloud Import

Import files from cloud services (via rclone):

- Google Drive, Dropbox, OneDrive, and more
- One-time or scheduled imports
- Configure under **Cloud Import**

## Security

### Password Policy

- Minimum 8 characters
- Uppercase + lowercase + digit required
- Common passwords are rejected

### Two-Factor Authentication (2FA)

1. Settings → Security → Enable 2FA
2. Scan QR code with authenticator app (Google Authenticator, Authy, etc.)
3. Enter code to confirm

### Audit Logging

All security-relevant actions are logged:
- Logins (successful and failed)
- Password changes
- Admin operations
- File operations

Viewable under **Logging** (Admin).

### API Keys

For integrations, API keys can be created (Settings → API Keys).

## Troubleshooting

### Login fails

1. Check username and password (case-sensitive)
2. If 2FA is active: verify authenticator code
3. Clear browser cache
4. Check if server is reachable

### Upload fails

1. Check storage space in Dashboard
2. File too large? (Check quota)
3. Permissions: upload to your own folder

### Page won't load

1. Server reachable? Ping `baluhost.local`
2. Check VPN connection (if remote)
3. Check browser console for errors (F12)

### RAID degraded

1. Open RAID page → identify affected disk
2. Replace disk and start rebuild
3. Check SMART data of remaining disks

---

**Version:** 1.23.0  
**Last updated:** April 2026
