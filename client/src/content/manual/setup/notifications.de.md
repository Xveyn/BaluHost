---
title: Push-Benachrichtigungen einrichten
slug: notifications
icon: bell
version: 1.20.5
order: 7
---

# Push-Benachrichtigungen einrichten

Diese Anleitung erklärt, wie du Firebase Cloud Messaging (FCM) für Push-Benachrichtigungen an die BaluApp konfigurierst.

## Voraussetzungen

- Admin-Zugang zu BaluHost
- Firebase-Projekt mit aktiviertem FCM (Firebase Cloud Messaging)
- Service-Account-JSON-Datei aus der Firebase Console

## Schritte

1. Erstelle ein Projekt in der [Firebase Console](https://console.firebase.google.com)
2. Aktiviere **Firebase Cloud Messaging** unter „Projekteinstellungen → Cloud Messaging"
3. Erstelle einen Service Account unter „Projekteinstellungen → Service Accounts" und lade die JSON-Schlüsseldatei herunter
4. Navigiere in BaluHost zu **Systemsteuerung → Firebase**
5. Lade die heruntergeladene Service-Account-JSON-Datei hoch
6. Konfiguriere die Benachrichtigungskanäle (z. B. Systemalarme, Dateiaktivitäten, Backups)
7. Sende eine Testnachricht, um die Konfiguration zu überprüfen
