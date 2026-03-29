---
title: VPN (WireGuard) einrichten
slug: vpn
icon: shield
version: 1.20.5
order: 2
---

# VPN (WireGuard) einrichten

Diese Anleitung erklärt, wie du den integrierten WireGuard-VPN-Server aktivierst und Clients für sicheren Fernzugriff auf dein BaluHost einrichtest.

## Voraussetzungen

- Admin-Zugang zu BaluHost
- WireGuard auf dem Client-Gerät installiert
- Port-Weiterleitung UDP 51820 am Router eingerichtet

## Schritte

1. Navigiere zu **Systemsteuerung → VPN**
2. Klicke auf **VPN-Server aktivieren**
3. Lege das Subnetz und den öffentlichen Endpunkt (deine externe IP oder Domain) fest
4. Klicke auf **Client hinzufügen** und vergib einen Namen
5. Scanne den angezeigten QR-Code mit der WireGuard-App oder lade die Konfigurationsdatei herunter
6. Importiere die Konfiguration in deinen WireGuard-Client und verbinde dich
7. Der neue Client erscheint anschließend in der Client-Übersicht mit Status und Datentransfer
