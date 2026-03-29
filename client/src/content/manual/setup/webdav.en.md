---
title: Set Up WebDAV
slug: webdav
icon: globe
version: 1.20.5
order: 9
---

# Set Up WebDAV

This guide explains how to enable the built-in WebDAV server and connect with WebDAV clients (e.g. Windows Explorer, macOS Finder, DAVx⁵).

## Prerequisites

- Admin access to BaluHost

## Steps

1. Navigate to **System Control → WebDAV**
2. Click **Enable WebDAV Server**
3. Choose the port (default: 8080) and optionally a base path
4. Save the configuration — the WebDAV service starts automatically
5. Connect with a WebDAV client:
   - **Windows**: Add `http://<server-ip>:<port>` as a network drive in Explorer
   - **macOS**: In Finder go to "Go → Connect to Server" and enter `http://<server-ip>:<port>`
   - **Android/iOS**: Use DAVx⁵ or a similar app
6. Log in with your BaluHost credentials
