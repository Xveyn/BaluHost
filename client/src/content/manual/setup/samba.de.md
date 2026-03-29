---
title: Samba/SMB-Freigaben einrichten
slug: samba
icon: folder-open
version: 1.20.5
order: 8
---

# Samba/SMB-Freigaben einrichten

Diese Anleitung erklärt, wie du SMB/CIFS-Netzwerkfreigaben über den integrierten Samba-Server einrichtest, damit Windows, macOS und Linux-PCs auf Dateien zugreifen können.

## Voraussetzungen

- Admin-Zugang zu BaluHost

## Schritte

1. Navigiere zu **Systemsteuerung → Samba**
2. Klicke auf **Samba-Server aktivieren**
3. Klicke auf **Freigabe hinzufügen** und vergib einen Namen (z. B. „Dokumente")
4. Wähle den Quellpfad auf dem BaluHost-Speicher
5. Lege Zugriffsrechte fest (öffentlich oder auf bestimmte Benutzer beschränkt)
6. Speichere die Konfiguration – der Samba-Dienst wird automatisch neu gestartet
7. Verbinde dich vom Windows Explorer mit `\\<server-ip>\<freigabe-name>` oder vom macOS Finder mit `smb://<server-ip>/<freigabe-name>`
