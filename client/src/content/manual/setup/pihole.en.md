---
title: Set Up Pi-hole DNS
slug: pihole
icon: shield-check
version: 1.20.5
order: 5
---

# Set Up Pi-hole DNS

This guide shows how to set up Pi-hole as a network-wide DNS ad blocker through the BaluHost integration.

## Prerequisites

- Admin access to BaluHost
- Docker installed on the server

## Steps

1. Navigate to **Pi-hole** in the sidebar
2. Click **Set Up Pi-hole**
3. Enter a secure password for the Pi-hole web interface
4. Choose an upstream DNS provider (e.g. Cloudflare `1.1.1.1` or Google `8.8.8.8`)
5. Click **Start Container** — Pi-hole is launched automatically as a Docker container
6. Once started the Pi-hole web interface is accessible via the displayed link
7. Set the BaluHost IP as the DNS server in your router to filter all devices on the network
