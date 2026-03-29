---
title: Set Up VPN (WireGuard)
slug: vpn
icon: shield
version: 1.20.5
order: 2
---

# Set Up VPN (WireGuard)

This guide explains how to enable the built-in WireGuard VPN server and configure clients for secure remote access to your BaluHost.

## Prerequisites

- Admin access to BaluHost
- WireGuard installed on the client device
- Port forwarding for UDP 51820 configured on your router

## Steps

1. Navigate to **System Control → VPN**
2. Click **Enable VPN Server**
3. Set the subnet and public endpoint (your external IP or domain)
4. Click **Add Client** and enter a name
5. Scan the displayed QR code with the WireGuard app or download the config file
6. Import the configuration into your WireGuard client and connect
7. The new client will appear in the client list showing status and data transfer
