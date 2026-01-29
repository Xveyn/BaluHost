# BaluHost Android - TODO (Top 3 Prioritäten)

**Stand:** Januar 2026 | **App Status:** 60% fertig

Die drei dringendsten Aufgaben für die Android-App, priorisiert nach Impact und Kritikalität.

---

## 🔴 PRIO 1: VPN Configuration Management

**Zeitaufwand:** 2-3 Tage | **Impact:** Kritisch (Remote Access)

**Warum kritisch:** Ohne VPN ist die App nur im lokalen Netzwerk nutzbar. VPN-Support ist essentiell für einen mobilen NAS-Client.

### Backend (Koordination erforderlich)

- [ ] Endpoint: `GET /api/mobile/vpn/config`
  - Response: WireGuard Config + Metadata (Server, Client IP, DNS, etc.)
- [ ] Endpoint: `POST /api/mobile/vpn/config`
  - Request: Regenerate VPN keys
  - Response: Neue WireGuard Config
- [ ] WireGuard Config Response Format standardisieren

### Android App

**Data Layer:**
- [ ] `VpnApi` Interface + DTOs (`data/remote/api/VpnApi.kt`)
- [ ] `VpnRepository` Interface (`domain/repository/VpnRepository.kt`)
- [ ] `VpnRepositoryImpl` mit API + SecureStorage (`data/repository/VpnRepositoryImpl.kt`)
- [ ] `VpnConfig` Domain Model (`domain/model/VpnConfig.kt`)

**Domain Layer:**
- [ ] `FetchVpnConfigUseCase` (Fetch from API, fallback to cache)
- [ ] `RegenerateVpnConfigUseCase` (POST regenerate)

**Presentation Layer:**
- [ ] `VpnViewModel` mit State Management
  - State: `config`, `isConnected`, `isLoading`, `error`, `message`
  - Actions: `loadVpnConfig()`, `connect()`, `disconnect()`, `refreshConfig()`
- [ ] `VpnScreen` UI Composable
  - Status Card (Verbunden/Getrennt)
  - Connect/Disconnect Toggle
  - Config Info Display (Server, Client IP, DNS, etc.)
  - Error Display
  - Loading State
  - Refresh Button

**Infrastructure:**
- [ ] SecureStorage Integration (VPN Config verschlüsselt speichern)
- [ ] Hilt Module Update (VpnRepository, VpnApi binding)
- [ ] Navigation: Add `VpnScreen` Route

### Testing

- [ ] Manual Test: VPN Connect/Disconnect
- [ ] Config Fetch & Local Caching
- [ ] Error Handling (Offline, Invalid Config)
- [ ] Reconnect after App Restart

**Kritische Dateien:**
- `data/remote/api/VpnApi.kt`
- `data/repository/VpnRepositoryImpl.kt`
- `domain/repository/VpnRepository.kt`
- `domain/model/VpnConfig.kt`
- `presentation/ui/screens/vpn/VpnScreen.kt`
- `presentation/viewmodel/VpnViewModel.kt`

**Fertigstellungs-Kriterien:**
- [x] Backend Endpoint funktioniert
- [x] App kann VPN aufbauen & trennen
- [x] Config wird lokal gecached (SecureStorage)
- [x] UI zeigt Verbindungsstatus korrekt an

---

## 🟠 PRIO 2: Settings Screen

**Zeitaufwand:** 2-3 Tage | **Impact:** Hoch (User Experience)

**Warum wichtig:** User braucht Kontrolle über Sync-Verhalten, Backup-Einstellungen, Benachrichtigungen und mehr. Settings Screen ist Standard für jede Mobile App.

### Data Layer

- [ ] `AppSettings` Domain Model (`domain/model/AppSettings.kt`)
  - Connection: `baseUrl`, `deviceName`
  - Sync: `autoSyncEnabled`, `syncIntervalMinutes`, `wifiOnlySync`, `bandwidthLimitMbps`
  - Backup: `cameraBackupEnabled`, `autoPhotoBackup`, `autoVideoBackup`, `backupFrequencyHours`
  - Notifications: `syncNotifications`, `errorNotifications`, `downloadNotifications`, `offlineAlerts`
  - App Info: `appVersion`, `lastSyncTime`

- [ ] `SettingsRepository` Interface (`domain/repository/SettingsRepository.kt`)
  - `getSettings()`, `updateSettings()`, `observeSettings()`, `resetSettings()`

- [ ] `SettingsRepositoryImpl` (`data/repository/SettingsRepositoryImpl.kt`)
  - DataStore Integration (Preferences)
  - PreferenceKeys Definition

### UI & ViewModel

- [ ] `SettingsViewModel` (`presentation/viewmodel/SettingsViewModel.kt`)
  - State: `settings: StateFlow<AppSettings>`
  - Actions: `updateSetting(key, value)`, `resetSettings()`, `logout()`

- [ ] `SettingsScreen` Composable (`presentation/ui/screens/settings/SettingsScreen.kt`)

**UI Sections:**
- [ ] **Section 1: Verbindung**
  - Server URL (read-only)
  - Geräte-Name (read-only)

- [ ] **Section 2: Synchronisierung**
  - Auto-Sync aktiviert (Toggle)
  - Sync-Intervall (Slider: 5-60 Min)
  - Nur WiFi (Toggle)
  - Bandbreiten-Limit (Optional Input)

- [ ] **Section 3: Sicherung**
  - Kamera-Backup aktiviert (Toggle)
  - Fotos automatisch sichern (Toggle)
  - Videos automatisch sichern (Toggle)
  - Backup-Frequenz (Slider: 1-24 Std)

- [ ] **Section 4: Benachrichtigungen**
  - Sync-Benachrichtigungen (Toggle)
  - Fehler-Benachrichtigungen (Toggle)
  - Download-Benachrichtigungen (Toggle)
  - Offline-Warnungen (Toggle)

- [ ] **Section 5: Erweitert**
  - App-Version anzeigen (read-only)
  - Letzte Sync-Zeit anzeigen (read-only)
  - "Auf Standard zurücksetzen" Button
  - "Abmelden" Button (rot)

- [ ] Navigation Integration (SettingsScreen Route)

### Testing

- [ ] Settings Persistence Test (DataStore)
- [ ] Reset Settings Test
- [ ] App Restart: Settings sollten bleiben
- [ ] Toggle/Slider Updates funktionieren

**Kritische Dateien:**
- `domain/model/AppSettings.kt`
- `domain/repository/SettingsRepository.kt`
- `data/repository/SettingsRepositoryImpl.kt`
- `presentation/ui/screens/settings/SettingsScreen.kt`
- `presentation/viewmodel/SettingsViewModel.kt`

**Fertigstellungs-Kriterien:**
- [x] Alle 5 Sections implementiert
- [x] Settings werden in DataStore persistiert
- [x] Reset funktioniert (zurück zu Defaults)
- [x] Logout funktioniert (löscht Credentials, navigiert zu Login)

---

## 🟠 PRIO 3: Camera Backup

**Zeitaufwand:** 5-7 Tage | **Impact:** Hoch (Killer-Feature)

**Warum wichtig:** Automatische Foto-/Video-Sicherung ist DER Hauptgrund, warum viele User eine NAS-App nutzen. Killer-Feature für BaluHost Mobile.

**Abhängigkeit:** Settings Screen sollte zuerst fertig sein (für Backup-Toggles).

### Phase 1: Photo/Video Detection

- [ ] MediaStore Integration (`util/MediaStoreScanner.kt`)
  - Query Photos: `MediaStore.Images.Media.EXTERNAL_CONTENT_URI`
  - Query Videos: `MediaStore.Video.Media.EXTERNAL_CONTENT_URI`
  - Filter: Nur neue Dateien seit letztem Backup

- [ ] Permission Handling
  - Android 13+: `READ_MEDIA_IMAGES`, `READ_MEDIA_VIDEO`
  - Android 12-: `READ_EXTERNAL_STORAGE`
  - Permission Request Flow in UI

- [ ] File Change Observer (`ContentObserver`)
  - Beobachte MediaStore für neue Fotos/Videos
  - Trigger Backup-Worker bei Änderungen

- [ ] Backup Candidate Selection Logic
  - Filter bereits gesicherte Dateien (Hash-Vergleich)
  - Filter nach User-Auswahl (nur bestimmte Ordner)

### Phase 2: Auto-Backup Worker

- [ ] `CameraBackupWorker` (`data/worker/CameraBackupWorker.kt`)
  - Extends `CoroutineWorker`
  - Hilt Integration (`@HiltWorker`)
  - Constraints: `NetworkType.UNMETERED` (WiFi-only)

- [ ] Upload Queue Integration
  - Reuse `OfflineQueueRepository`
  - Queue Upload Operations für neue Fotos/Videos
  - Automatic Retry bei Fehler

- [ ] WiFi-Only Constraint
  - WorkManager Constraint: `setRequiredNetworkType(NetworkType.UNMETERED)`

- [ ] Bandwidth Limiting
  - Optional: Throttle Upload Speed (Settings Integration)

- [ ] Duplicate Detection
  - Hash-based (SHA256 von File Content)
  - Skip bereits hochgeladene Dateien

### Phase 3: UI

- [ ] `BackupStatusScreen` (`presentation/ui/screens/backup/BackupStatusScreen.kt`)
  - Backup Progress (aktueller Upload)
  - Last Backup Timestamp
  - Statistics (Anzahl Fotos/Videos gesichert)
  - "Jetzt Sichern" Button (Manual Trigger)

- [ ] `FolderSelectionDialog` (`presentation/ui/components/FolderSelectionDialog.kt`)
  - Liste aller Foto/Video Ordner
  - Multi-Select (Checkboxen)
  - "Nur ausgewählte Ordner sichern" Option

- [ ] Settings Integration
  - Camera Backup Toggle (aktiviert/deaktiviert Worker)
  - Auto-Photo/Video Backup Toggles
  - Backup-Frequenz Slider

### Phase 4: Testing

- [ ] Manual Test: Neues Foto aufnehmen → Auto Upload
- [ ] WiFi Constraint Test (Deaktiviere WiFi → kein Upload)
- [ ] Selective Folder Test (Nur DCIM/Camera sichern)
- [ ] Duplicate Detection Test (Upload gleiche Datei 2x)
- [ ] App Restart: Pending Uploads sollten weiterlaufen

**Kritische Dateien:**
- `data/worker/CameraBackupWorker.kt`
- `domain/usecase/backup/DetectNewPhotosUseCase.kt`
- `domain/usecase/backup/QueueBackupUseCase.kt`
- `presentation/ui/screens/backup/BackupStatusScreen.kt`
- `presentation/ui/components/FolderSelectionDialog.kt`
- `util/MediaStoreScanner.kt`

**Fertigstellungs-Kriterien:**
- [x] Neue Fotos/Videos werden erkannt
- [x] Auto-Upload bei WiFi funktioniert
- [x] User kann Ordner selektiv auswählen
- [x] Backup-Status wird angezeigt (Progress, Last Backup, Stats)
- [x] Duplicate Detection funktioniert (keine doppelten Uploads)

---

## 📊 Roadmap-Übersicht

```
Woche 1 (KW X):       🔴 VPN Config + 🟠 Settings Screen
Woche 2-3 (KW X+1):   🟠 Camera Backup (alle 4 Phasen)
Woche 4 (KW X+2):     ✅ Testing & Polish
```

---

## 🎯 Nächster Schritt

**Start mit:** 🔴 **VPN Configuration Management**

**Grund:** Kritischer Blocker für Remote Access. Ohne VPN ist die App nur im lokalen Netzwerk nutzbar.

**Voraussetzung:** Backend-Team muss `/api/mobile/vpn/config` Endpoint bereitstellen.

---

## 📚 Weiterführende Dokumentation

- **STATUS_UND_ROADMAP.md** - Vollständiger Status aller Features (1-5 Phasen)
- **QUICK_START.md** - Schnellübersicht (Deutsch)
- **NEXT_STEPS_IMPLEMENTATION.md** - Detaillierte Code-Beispiele für VPN + Settings
- **CLAUDE.md** - Entwickler-Guide für Android-App
- **README.md** - Setup & Grundlagen

---

**Letzte Aktualisierung:** 29. Januar 2026
