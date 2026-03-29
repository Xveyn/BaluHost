---
title: Set Up Samba/SMB Shares
slug: samba
icon: folder-open
version: 1.20.5
order: 8
---

# Set Up Samba/SMB Shares

This guide explains how to set up SMB/CIFS network shares via the built-in Samba server so that Windows, macOS, and Linux computers can access files.

## Prerequisites

- Admin access to BaluHost

## Steps

1. Navigate to **System Control → Samba**
2. Click **Enable Samba Server**
3. Click **Add Share** and enter a name (e.g. "Documents")
4. Select the source path on the BaluHost storage
5. Set access permissions (public or restricted to specific users)
6. Save the configuration — the Samba service restarts automatically
7. Connect from Windows Explorer using `\\<server-ip>\<share-name>` or from the macOS Finder using `smb://<server-ip>/<share-name>`
