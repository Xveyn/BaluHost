# BaluHost Android App - Implementierungs-Priorisierung

**Datum:** Januar 2026  
**Ziel:** Android App zur produktiven Reife bringen

---

## 📊 Feature Prioritätsmatrix

```
        High Impact
             ▲
             │  Camera Backup ⭐⭐⭐
             │  VPN Config ⭐⭐⭐
             │  Settings UI ⭐⭐
             │
             │  DocumentsProvider ⭐⭐
             │  Search ⭐⭐  Share Links ⭐
             │
             │
     ────────┼──────────────────────► Low Effort, Quick Win
             │
```

---

## 🎯 Sprint 1: VPN & Konfiguration (1 Woche)

### Task 1.1: VPN Configuration Backend Integration ⭐⭐⭐
**Effort:** 3 Tage  
**Impact:** Kritisch für Remote Access  
**Dependencies:** Backend `/api/mobile/vpn/config` Endpoint

#### Subtasks
1. **Backend Endpoint** (`backend/app/`)
   - [ ] `GET /api/mobile/vpn/config` - WireGuard Config abrufen
   - [ ] Config pro Device/User speichern
   - [ ] Config Format: INI oder JSON
   - [ ] Schema: `GET /api/mobile/vpn/config/{device_id}`

2. **Android Implementation**
   - [ ] `VpnConfigService` mit Retrofit Call
   - [ ] `FetchVpnConfigUseCase`
   - [ ] Secure Storage für Config (EncryptedSharedPreferences)
   - [ ] `VpnConfigRepository`

3. **UI Implementation**
   - [ ] `VpnScreen` vollständig implementieren
   - [ ] Connect/Disconnect Toggle
   - [ ] Status Display (Connected/Disconnected/Error)
   - [ ] Config Edit Dialog
   - [ ] Error Handling & Retry

4. **Testing**
   - [ ] Manual Test mit Backend
   - [ ] Device Connection Test
   - [ ] Config Persistence Test
   - [ ] Error Handling Test

#### Code-Struktur
```kotlin
// data/remote/api/VpnApi.kt
interface VpnApi {
    @GET("mobile/vpn/config")
    suspend fun getVpnConfig(): ApiResponse<VpnConfigDto>
    
    @POST("mobile/vpn/config")
    suspend fun updateVpnConfig(@Body config: VpnConfigDto): ApiResponse<Unit>
}

// domain/model/VpnConfig.kt
data class VpnConfig(
    val deviceId: String,
    val configString: String,
    val serverAddress: String,
    val clientIp: String,
    val createdAt: Instant,
    val updatedAt: Instant
)

// VpnViewModel
class VpnViewModel @Inject constructor(
    private val fetchVpnConfigUseCase: FetchVpnConfigUseCase,
    private val vpnManager: VpnManager
) : ViewModel() {
    val vpnState: StateFlow<VpnUiState> = ...
    
    fun connect() { /* ... */ }
    fun disconnect() { /* ... */ }
    fun refreshConfig() { /* ... */ }
}
```

---

### Task 1.2: Settings Screen Implementierung ⭐⭐
**Effort:** 2-3 Tage  
**Impact:** Hoch - User Experience  

#### Sections
1. **Connection Settings**
   - Base URL Configuration
   - Device Name (editable)
   - Server Information
   - Connection Status

2. **Sync Settings**
   - Auto-Sync Enable/Disable
   - Sync Interval (minutes)
   - WiFi-only Sync
   - Bandwidth Limit (optional)

3. **Backup Settings**
   - Camera Backup Enable/Disable
   - Auto Photo Backup
   - Auto Video Backup
   - Backup Location
   - Backup Frequency

4. **Notification Settings**
   - Sync Notifications
   - Error Notifications
   - Download Notifications
   - Offline Alerts

5. **Advanced**
   - Logout
   - Device Management
   - App Version
   - Clear Cache

#### Code-Struktur
```kotlin
// domain/model/AppSettings.kt
data class AppSettings(
    val autoSync: Boolean = true,
    val syncInterval: Int = 15, // minutes
    val wifiOnly: Boolean = false,
    val bandwidthLimit: Int? = null,
    val cameraBackupEnabled: Boolean = false,
    val notificationsEnabled: Boolean = true,
    val lastSyncTime: Instant? = null
)

// data/repository/SettingsRepository.kt
class SettingsRepository @Inject constructor(
    private val dataStore: DataStore<Preferences>
) {
    fun getSettings(): Flow<AppSettings> = ...
    suspend fun updateSettings(settings: AppSettings) = ...
    suspend fun resetSettings() = ...
}

// SettingsViewModel
class SettingsViewModel @Inject constructor(
    private val settingsRepository: SettingsRepository
) : ViewModel() {
    val settings: StateFlow<AppSettings> = ...
    
    fun updateSetting(key: String, value: Any) { /* ... */ }
    fun logout() { /* ... */ }
}
```

---

### Task 1.3: Network Error Resilience Improvements
**Effort:** 1-2 Tage  
**Impact:** Stabilität  

- [ ] Improved Timeout Handling (30s → 60s für große Uploads)
- [ ] Connection Pool in OkHttp konfigurieren
- [ ] Retry Interceptor mit Exponential Backoff
- [ ] SSL Certificate Error Handling
- [ ] Offline Mode Indicator

---

## 🎯 Sprint 2: Camera & Media (1-2 Wochen)

### Task 2.1: Camera Backup Implementation ⭐⭐⭐
**Effort:** 5-7 Tage  
**Impact:** Killer Feature  

#### Phase 1: WorkManager Setup
- [ ] `CameraBackupWorker` voll implementieren
- [ ] Periodic Scheduling (1x täglich)
- [ ] Constraints: WiFi + Charging (optional konfigurierbar)
- [ ] Foreground Service Notification

#### Phase 2: Photo/Video Detection
- [ ] Query MediaStore für neue Fotos/Videos
- [ ] Filter nach Datum (seit letztem Backup)
- [ ] Selective Folder Selection UI
- [ ] Exclude App Photos

#### Phase 3: Backup Logic
- [ ] Smart Compression für Bilder
- [ ] Video Streaming Upload
- [ ] Duplicate Detection (Hash-based)
- [ ] Batch Upload
- [ ] Retry bei Fehler

#### Phase 4: UI
- [ ] Backup Settings in SettingsScreen
- [ ] Backup Status Display
- [ ] Manual Trigger Button
- [ ] Backup History

---

### Task 2.2: DocumentsProvider Integration
**Effort:** 3-4 Tage  
**Impact:** Native Android Integration  

- [ ] `BaluHostDocumentsProvider` implementieren
- [ ] DocumentsContract Implementierung
- [ ] File Browsing via DocumentsProvider
- [ ] System File Picker Integration
- [ ] Performance Optimization

---

### Task 2.3: Media Playback (Video/Audio)
**Effort:** 3-4 Tage  
**Impact:** Mittel-Hoch  

#### Video Player
- [ ] `VideoPlayerScreen` Composable
- [ ] ExoPlayer Integration
- [ ] Streaming Playback
- [ ] Seek/Pause/Resume Controls
- [ ] Quality Selection (optional)
- [ ] Full Screen Mode

#### Audio Player
- [ ] `AudioPlayerScreen` Composable
- [ ] ExoPlayer Integration
- [ ] Playlist Support
- [ ] Metadata Display (Album, Artist, Duration)
- [ ] Now Playing Widget

---

## 🎯 Sprint 3: Polish & Advanced (2 Wochen)

### Task 3.1: Search & Filter ⭐⭐
**Effort:** 2-3 Tage  
**Impact:** UX Improvement  

- [ ] `SearchBar` in FilesScreen TopAppBar
- [ ] Real-time File Search (Local + Remote)
- [ ] Filter Options (Type, Date, Size)
- [ ] Search History
- [ ] Sort Options

---

### Task 3.2: Share & Collaboration
**Effort:** 3-4 Tage  
**Impact:** Hoch  

- [ ] Share Links Generation
- [ ] Time-limited Access
- [ ] Password Protection
- [ ] Expiry Configuration
- [ ] Revoke Share Links
- [ ] Share History

#### Backend Requirements
- [ ] `POST /api/shares` - Create share link
- [ ] `GET /api/shares/{id}` - Get share info
- [ ] `DELETE /api/shares/{id}` - Revoke share
- [ ] `GET /api/shares` - List user shares

---

### Task 3.3: UI Polish & Animations
**Effort:** 2-3 Tage  
**Impact:** Professional Look  

- [ ] Material Motion Specifications
- [ ] Page Transitions
- [ ] List Item Animations
- [ ] Loading Skeletons
- [ ] Smooth Scrolling
- [ ] Dark Mode Polish

---

### Task 3.4: Error Handling & Recovery
**Effort:** 1-2 Tage  
**Impact:** User Confidence  

- [ ] Better Error Messages (User-friendly)
- [ ] Recovery Suggestions
- [ ] Error Analytics (Optional Sentry)
- [ ] Crash Reports
- [ ] Network Error Dialog

---

## 📋 Implementation Checklist - VPN & Settings (Diese Woche)

### Backend Vorbereitung
- [ ] `/api/mobile/vpn/config` GET Endpoint
- [ ] `/api/mobile/vpn/config` POST Endpoint (Optional)
- [ ] Database Schema für VPN Config
- [ ] WireGuard Config Format Spezifikation

### Android Frontend
- [ ] VpnConfigService + Repository
- [ ] FetchVpnConfigUseCase
- [ ] VpnManager für Connection Management
- [ ] VpnViewModel mit State Management
- [ ] VpnScreen UI Complete
- [ ] SettingsScreen Complete
- [ ] Settings Repository + ViewModel
- [ ] DataStore Integration für Settings

### Testing
- [ ] Manual Testing mit echtem Backend
- [ ] Network Condition Testing (Offline Simulation)
- [ ] VPN Connection Test
- [ ] Settings Persistence Test
- [ ] Error Scenario Testing

---

## 🔧 Technical Debt & Bug Fixes

### High Priority
1. [ ] Fix Compile Warnings in build_errors.txt
2. [ ] Update Android Gradle Plugin to support compileSdk 35
3. [ ] Test auf Android 14+ Devices
4. [ ] Firebase FCM Setup (Boilerplate existiert)

### Medium Priority
5. [ ] Unit Tests für ViewModels
6. [ ] Integration Tests für API Calls
7. [ ] Database Migration Tests
8. [ ] Performance Profiling (File List)

### Low Priority
9. [ ] Add Logging Framework (spdlog-like für Kotlin)
10. [ ] Accessibility Improvements (ContentDescription)
11. [ ] Localization Setup (Strings Resources)

---

## 📈 Success Metrics

| Metric | Target | Effort |
|--------|--------|--------|
| **App Launch Time** | <3 seconds | Low |
| **File List Load** | <1 second | Low |
| **VPN Connection** | <5 seconds | Medium |
| **Upload 10MB File** | <30 seconds (WiFi) | Medium |
| **Offline Reliability** | >95% | Low |
| **Camera Backup** | Auto complete | High |
| **Search Response** | <500ms | Medium |

---

## 🚀 Release Plan

### v1.1.0 (Alpha) - 2 Wochen
- VPN Configuration Management
- Settings Screen
- Improved Error Handling

### v1.2.0 (Beta) - 4 Wochen
- Camera Backup
- DocumentsProvider
- Media Playback
- Search & Filter

### v1.3.0 (Production Ready) - 6 Wochen
- Share Links
- Polish & Animations
- Full Testing
- Performance Optimization

---

## 💡 Notizen für Entwickler

### Best Practices für diese Sprints
1. **Kotlin Coroutines:** Nutze `viewModelScope` für ViewModel-Operationen
2. **Flow vs StateFlow:** StateFlow für UI State, Flow für Events
3. **Hilt Injection:** Alle Services über Hilt injecten
4. **Compose:** Prefer Composables über XML Layouts
5. **Error Handling:** Try-catch in UseCases, Result<T> für UI
6. **Testing:** Unit Tests für LogicHauptlich (ViewModels, UseCases)

### Häufige Fehler zu vermeiden
1. ❌ Main Thread Blocking in API Calls
2. ❌ Memory Leaks in ViewModels
3. ❌ Hardcoded Strings (Use Strings Resources)
4. ❌ Unhandled Exceptions
5. ❌ Missing Null Checks
6. ❌ Inefficient List Rendering

### Performance Tips
1. ✅ Use `LazyColumn` statt `Column` für lange Listen
2. ✅ Use `rememberCoroutineScope()` für Event Handler
3. ✅ Use `remember` für expensive Computations
4. ✅ Use Pagination für große Datasets
5. ✅ Cache API Responses lokal

---

## 📞 Support & Questions

- **Kotlin/Jetpack:** Android Developer Docs
- **API Integration:** Backend `/docs/API_REFERENCE.md`
- **VPN Setup:** WireGuard Android Library Docs
- **Compose:** Official Google Compose Documentation

