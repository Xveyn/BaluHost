---
title: WebDAV einrichten
slug: webdav
icon: globe
version: 1.20.5
order: 9
---

# WebDAV einrichten

Diese Anleitung erklärt, wie du den integrierten WebDAV-Server aktivierst und dich mit WebDAV-Clients (z. B. Windows Explorer, macOS Finder, DAVx⁵) verbindest.

## Voraussetzungen

- Admin-Zugang zu BaluHost

## Schritte

1. Navigiere zu **Systemsteuerung → WebDAV**
2. Klicke auf **WebDAV-Server aktivieren**
3. Wähle den Port (Standard: 8080) und ggf. einen Basispfad
4. Speichere die Konfiguration – der WebDAV-Dienst startet automatisch
5. Verbinde dich mit einem WebDAV-Client:
   - **Windows**: Im Explorer `http://<server-ip>:<port>` als Netzwerklaufwerk hinzufügen
   - **macOS**: Im Finder über „Gehe zu → Mit Server verbinden" `http://<server-ip>:<port>` eingeben
   - **Android/iOS**: DAVx⁵ oder ähnliche Apps verwenden
6. Melde dich mit deinen BaluHost-Zugangsdaten an
