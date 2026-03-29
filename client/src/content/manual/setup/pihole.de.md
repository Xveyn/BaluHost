---
title: Pi-hole DNS einrichten
slug: pihole
icon: shield-check
version: 1.20.5
order: 5
---

# Pi-hole DNS einrichten

Diese Anleitung zeigt, wie du Pi-hole als DNS-Werbefilter über die BaluHost-Integration einrichtest.

## Voraussetzungen

- Admin-Zugang zu BaluHost
- Docker auf dem Server installiert

## Schritte

1. Navigiere zu **Pi-hole** in der Seitenleiste
2. Klicke auf **Pi-hole einrichten**
3. Gib ein sicheres Passwort für das Pi-hole-Webinterface ein
4. Wähle einen Upstream-DNS-Anbieter (z. B. Cloudflare `1.1.1.1` oder Google `8.8.8.8`)
5. Klicke auf **Container starten** – Pi-hole wird automatisch als Docker-Container gestartet
6. Nach dem Start ist das Pi-hole-Webinterface über den angezeigten Link erreichbar
7. Trage die BaluHost-IP als DNS-Server in deinem Router ein, um alle Geräte im Netzwerk zu filtern
