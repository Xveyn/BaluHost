---
title: Set Up Push Notifications
slug: notifications
icon: bell
version: 1.20.5
order: 7
---

# Set Up Push Notifications

This guide explains how to configure Firebase Cloud Messaging (FCM) for push notifications to the BaluApp.

## Prerequisites

- Admin access to BaluHost
- Firebase project with FCM (Firebase Cloud Messaging) enabled
- Service account JSON file from the Firebase Console

## Steps

1. Create a project in the [Firebase Console](https://console.firebase.google.com)
2. Enable **Firebase Cloud Messaging** under "Project Settings → Cloud Messaging"
3. Create a service account under "Project Settings → Service Accounts" and download the JSON key file
4. Navigate in BaluHost to **System Control → Firebase**
5. Upload the downloaded service account JSON file
6. Configure notification channels (e.g. system alerts, file activity, backups)
7. Send a test notification to verify the configuration
