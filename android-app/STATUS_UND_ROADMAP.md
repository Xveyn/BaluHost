# BaluHost Android App - Status & Entwicklungs-Roadmap

**Stand:** Januar 2026  
**Projekt-Status:** 🔄 In aktiver Entwicklung  
**Build-Status:** ✅ Erfolgreich  

---

## 📊 Implementierungs-Übersicht

### ✅ Phase 1: Authentifizierung & Grundlagen (VOLLSTÄNDIG)

#### Core Features
- ✅ **QR-Code Scanner**
  - ML Kit Barcode Scanning
  - `QrScannerScreen` mit Camera Integration
  - QR Payload Parsing (JSON Format)
  - Deep Link Support für QR-Scanning

- ✅ **Device Registration**
  - `RegisterDeviceUseCase` implementiert
  - `POST /api/mobile/register` Endpoint
  - Device Info Collection (Name, Modell, OS Version, App Version)
  - Single-use Token Handling

- ✅ **Token Management**
  - DataStore für Token-Persistierung
  - `PreferencesManager` für Credential Storage
  - Secure Token Storage mit EncryptedSharedPreferences
  - `TokenInterceptor` für Request-Header Management

- ✅ **Authentication Flow**
  - `LoginScreen` implementiert
  - QR-Scanner Integration
  - Automatic Token Refresh
  - Session Persistence

### ✅ Phase 2: Dateimanagement (WEITGEHEND IMPLEMENTIERT)

#### File Management Features
- ✅ **File Browser**
  - `FilesScreen` mit Jetpack Compose UI
  - Hierarchische Ordnernavigation
  - File Listing mit Icons/Thumbnails
  - Current Path Tracking
  - Breadcrumb Navigation

- ✅ **File Operations**
  - Download mit Progress Tracking
  - Upload mit Progress Tracking
  - Delete mit Optimistic UI
  - Rename (Schema vorbereitet)
  - Create Folder (Schema vorbereitet)
  - Multi-File Selection (teilweise)

- ✅ **Thumbnail Generation**
  - Image Thumbnails via Coil
  - Video Thumbnails Integration
  - Generic File Icons
  - Type-based Icon Rendering

- ✅ **File Metadata**
  - Size Display
  - Last Modified Timestamp
  - File Type Recognition
  - Permission Display

#### Upload/Download
- ✅ **Download Implementation**
  - `DownloadFileUseCase`
  - Progress Callback Support
  - Streaming Download
  - SAF (Storage Access Framework) Support
  - File Size Validation

- ✅ **Upload Implementation**
  - `UploadFileUseCase`
  - Chunked Upload für große Dateien
  - Progress Tracking
  - SAF File Picker Integration
  - Multiple File Upload Support
  - Automatic Retry bei Fehler

- ✅ **Download UI**
  - Download Progress Dialog
  - File Size Display
  - Estimated Time Remaining
  - Cancel Option

- ✅ **Upload UI**
  - File Picker (SAF)
  - Upload Progress Indication
  - Multiple File Selection
  - Cancel/Pause Option

### ✅ Phase 3: Offline & Resilience (VOLLSTÄNDIG)

#### Offline Queue System
- ✅ **Persistent Operation Queue**
  - Room Database `PendingOperationEntity`
  - Operation Types: UPLOAD, DELETE, RENAME, CREATE_FOLDER, MOVE
  - Status Tracking: PENDING, RETRYING, FAILED, COMPLETED
  - Automatic Migration (v2 → v3)

- ✅ **Offline Detection & Queuing**
  - `NetworkMonitor` für Connectivity-Tracking
  - Automatic Queue bei Offline
  - Automatic Queue bei Network Error
  - Optimistic UI Updates

- ✅ **Automatic Retry Strategien**
  - **Sofortiges Retry** (NetworkMonitor bei Reconnect)
  - **Periodisches Retry** (WorkManager alle 15 Min)
  - **Tägliches Cleanup** (Alte Operations löschen)
  - Max 3 Retry-Versuche pro Operation
  - Exponential Backoff

- ✅ **UI Components für Queue**
  - `PendingOperationsScreen` (vollständig)
  - Pending Count Badge in FilesScreen
  - Manual Retry Buttons
  - Cancel Buttons
  - Status Badges & Error Messages
  - Live Update via Flow

- ✅ **Background Workers**
  - `OfflineQueueRetryWorker` (Hilt + WorkManager)
  - `OfflineQueueCleanupWorker`
  - Network Constraints
  - Exponential Backoff Strategy
  - Application.onCreate() Scheduling

### ⚠️ Phase 4: Erweiterte Features (TEILWEISE)

#### VPN Integration
- ✅ **WireGuard Service**
  - `BaluHostVpnService` implementiert
  - Configuration Parsing
  - Service Lifecycle Management
  - Notification Integration

- ⏳ **VPN UI**
  - `VpnScreen` Layout vorbereitet
  - Connection Toggle (UI nur)
  - Status Display (UI nur)
  - Config Management Interface (TODO)

- ⏳ **VPN Configuration**
  - Configuration Fetching (NOT Implemented)
  - Configuration Storage (NOT Implemented)
  - Dynamic VPN Setup (NOT Implemented)

#### Camera Backup (SCHEMA ONLY)
- ⏳ **WorkManager Integration**
  - `CameraBackupWorker` vorbereitet
  - `CameraBackupScheduler` vorbereitet
  - Periodic Backup Scheduling (TODO)

- ⏳ **Automatic Backup**
  - Photo/Video Detection (TODO)
  - Selective Backup (TODO)
  - Auto-Sync bei WiFi (TODO)
  - Bandwidth Limiting (TODO)

#### Android Files App Integration (PREPARED)
- ⏳ **DocumentsProvider**
  - Schema vorbereitet
  - Implementation TODO
  - File Access via Files App
  - Integration in System File Picker

#### Settings & Configuration
- ⏳ **Settings Screen**
  - Layout vorbereitet
  - Bandwidth Limits (TODO)
  - Auto-Start Configuration (TODO)
  - Notification Preferences (TODO)
  - Conflict Resolution Strategy (TODO)

#### Media Playback
- ✅ **ExoPlayer Integration**
  - Media3 Dependencies included
  - Video Playback Ready
  - Audio Playback Ready
  - Seeking & Streaming

- ⏳ **Video Player Screen**
  - Schema vorbereitet
  - Full Implementation TODO

- ⏳ **Audio Player Screen**
  - Schema vorbereitet
  - Full Implementation TODO

### 📱 Phase 5: Advanced (NICHT GESTARTET)

- ⏳ VPN Stats & Monitoring
- ⏳ Traffic Optimization
- ⏳ Local Sync Caching
- ⏳ Search & Filter
- ⏳ Favorites/Bookmarks
- ⏳ Share Links
- ⏳ Password Protection
- ⏳ Multi-User Support
- ⏳ Analytics Integration

---

## 🛠️ Technologie-Stack

### Aktuelle Versionen
| Komponente | Version |
|-----------|---------|
| **Android SDK** | Target 35, Min 26 |
| **Kotlin** | 1.9.x |
| **Jetpack Compose** | 2024.09 |
| **Hilt** | 2.51.1 |
| **Retrofit** | 2.9.0 |
| **Room** | 2.6.1 |
| **WorkManager** | 2.9.1 |
| **WireGuard** | 1.0.20230706 |
| **ExoPlayer (Media3)** | 1.4.1 |
| **ML Kit Barcode** | 17.3.0 |
| **Firebase** | Latest (FCM Ready) |

### Architektur
- **Pattern:** Clean Architecture + MVVM
- **Dependency Injection:** Hilt
- **Networking:** Retrofit + OkHttp
- **Database:** Room + DataStore
- **Concurrency:** Coroutines + Flow
- **UI Framework:** Jetpack Compose + Material 3

---

## 🎯 Prioritäts-Roadmap für Ausbauerkennung

### 🔴 Kritisch (Sofort starten)
1. **VPN Configuration Management**
   - Backend Integration: `/api/mobile/vpn/config`
   - Configuration Storage
   - UI für Config-Bearbeitung
   - **Impact:** Ermöglicht Remote Access

2. **Settings Screen**
   - Bandwidth Limits
   - Auto-Start Configuration
   - Notification Preferences
   - Sync Interval Configuration
   - **Impact:** User Experience Improvement

3. **Search & Filter**
   - File Search in FilesScreen
   - Filter nach Datum/Größe/Typ
   - **Impact:** Usability für große Ordner

### 🟠 Hoch (Nächste 2 Wochen)
4. **Camera Backup**
   - WorkManager Implementation
   - Auto-Photo Sync
   - Selective Folders
   - WiFi-only Option
   - **Impact:** Killer Feature für Mobile

5. **DocumentsProvider**
   - Android Files App Integration
   - System File Picker Integration
   - **Impact:** Native Android Integration

6. **Video/Audio Player**
   - Video Player Screen
   - Audio Player Screen
   - Streaming Support
   - **Impact:** Media Preview Feature

### 🟡 Mittel (Später im Monat)
7. **Share & Collaboration**
   - Share Links Generation
   - Time-limited Links
   - Password Protection
   - **Impact:** Collaboration Features

8. **UI Polish**
   - Dark Mode Improvements
   - Animation Refinements
   - Bottom Sheet Dialogs
   - **Impact:** Professional Polish

9. **Error Handling**
   - Better Error Messages
   - Recovery Suggestions
   - Error Analytics
   - **Impact:** User Confidence

### 🟢 Niedrig (Backlog)
10. **Favorites/Bookmarks**
11. **Multi-User Support**
12. **Local Sync Caching**
13. **Traffic Optimization**
14. **Analytics Integration**
15. **Push Notifications (FCM)**

---

## 📁 Projekt-Struktur (Aktuelle)

```
android-app/
├── app/
│   ├── src/main/java/com/baluhost/android/
│   │   ├── BaluHostApplication.kt          # App Class + Hilt
│   │   ├── data/
│   │   │   ├── local/
│   │   │   │   ├── dao/                    # Room DAOs
│   │   │   │   ├── entity/                 # Database Entities
│   │   │   │   └── preferences/            # DataStore + SecureStorage
│   │   │   ├── remote/
│   │   │   │   ├── api/                    # Retrofit Services
│   │   │   │   ├── dto/                    # Data Transfer Objects
│   │   │   │   └── interceptor/            # Token Interceptor
│   │   │   └── repository/                 # Repository Implementations
│   │   ├── domain/
│   │   │   ├── model/                      # Domain Models
│   │   │   ├── repository/                 # Repository Interfaces
│   │   │   ├── usecase/                    # Use Cases
│   │   │   └── adapter/                    # Cloud Adapters
│   │   ├── presentation/
│   │   │   ├── ui/
│   │   │   │   ├── composable/             # Reusable Composables
│   │   │   │   ├── dialog/                 # Dialog Components
│   │   │   │   └── screen/                 # Full Screen Composables
│   │   │   ├── viewmodel/                  # ViewModels
│   │   │   ├── navigation/                 # Navigation Setup
│   │   │   ├── theme/                      # Material 3 Theme
│   │   │   └── MainActivity.kt
│   │   ├── service/
│   │   │   ├── vpn/                        # VPN Service
│   │   │   ├── camera/                     # Camera Backup Worker
│   │   │   └── offline/                    # Offline Queue Workers
│   │   ├── di/                             # Hilt Modules
│   │   └── util/
│   │       ├── extension/                  # Kotlin Extensions
│   │       ├── network/                    # Network Monitor
│   │       └── helper/                     # Utility Helpers
│   ├── src/test/java/                      # Unit Tests
│   └── build.gradle.kts
└── README.md, OFFLINE_QUEUE_COMPLETE.md, etc.
```

---

## 🧪 Testing Status

### Unit Tests
- ⏳ Repository Tests (TODO)
- ⏳ UseCase Tests (TODO)
- ⏳ ViewModel Tests (TODO)

### Integration Tests
- ⏳ API Integration Tests (TODO)
- ⏳ Database Tests (TODO)

### UI Tests
- ⏳ Navigation Tests (TODO)
- ⏳ Screen Composition Tests (TODO)

---

## 🔒 Security Status

### Implementiert
- ✅ JWT Token Management
- ✅ EncryptedSharedPreferences
- ✅ Secure Token Storage
- ✅ SSL/TLS Support (via Retrofit/OkHttp)

### TODO
- ⏳ Certificate Pinning
- ⏳ Biometric Authentication
- ⏳ Keystore Integration

---

## 📈 Performance Metriken

| Metrik | Status | Target |
|--------|--------|--------|
| **App Start Time** | ~2-3s | <3s ✅ |
| **File List Load** | ~500ms | <1s ✅ |
| **Large File Upload** | Chunked | Streaming ⏳ |
| **Battery Impact** | Low | Very Low ⏳ |

---

## 📝 Nächste Aktionen

### Diese Woche
1. [ ] VPN Configuration Backend Integration
2. [ ] Settings Screen Implementation
3. [ ] Search Feature in FilesScreen

### Nächste Woche
4. [ ] Camera Backup Implementation
5. [ ] DocumentsProvider Integration
6. [ ] Video/Audio Player

### KW 3
7. [ ] Share Links Feature
8. [ ] UI Polish & Animations
9. [ ] Error Handling Improvements

---

## 🤝 Collaboration Notes

- **Backend API:** FastAPI in `/backend`
- **Mobile Registration:** `/api/mobile/token/generate`, `/api/mobile/register`
- **File API:** `/api/files/...` (upload, download, delete, etc.)
- **VPN API:** `/api/mobile/vpn/config` (TODO - Backend)
- **Dokumentation:** `/docs/ANDROID_APP_GUIDE.md`, `/docs/MOBILE_REGISTRATION.md`

---

## 📚 Weiterführende Dokumentation

- [Android App Guide](../docs/ANDROID_APP_GUIDE.md)
- [Mobile Registration Flow](../docs/MOBILE_REGISTRATION.md)
- [Offline Queue System](./OFFLINE_QUEUE_COMPLETE.md)
- [Build Errors Log](./build_errors.txt)
