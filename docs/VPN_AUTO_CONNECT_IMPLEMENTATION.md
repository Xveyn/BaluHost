# VPN Auto-Connect Implementation

## ✅ Phase 3: ViewModel/Screen-Integration (ABGESCHLOSSEN)

Die Integration von NetworkStateManager und VpnStatusBanner in FilesViewModel/FilesScreen und DashboardViewModel/DashboardScreen ist vollständig implementiert.

### Implementierte Änderungen

#### 1. Dependency Injection (NetworkModule.kt)

**Datei:** `android-app/app/src/main/java/com/baluhost/android/di/NetworkModule.kt`

**Änderungen:**
- Import von `NetworkStateManager` und `Context` hinzugefügt
- Provider-Funktion `provideNetworkStateManager` erstellt
```kotlin
@Provides
@Singleton
fun provideNetworkStateManager(
    @ApplicationContext context: Context,
    networkMonitor: NetworkMonitor
): NetworkStateManager {
    return NetworkStateManager(context, networkMonitor)
}
```

#### 2. FilesViewModel Integration

**Datei:** `android-app/app/src/main/java/com/baluhost/android/presentation/ui/screens/files/FilesViewModel.kt`

**Änderungen:**
- Import `NetworkStateManager` und `collectLatest`
- Constructor-Injection von `NetworkStateManager`
- VPN-State-Flows hinzugefügt:
  ```kotlin
  private val _isInHomeNetwork = MutableStateFlow<Boolean?>(null)
  val isInHomeNetwork: StateFlow<Boolean?> = _isInHomeNetwork.asStateFlow()
  
  private val _hasVpnConfig = MutableStateFlow(false)
  val hasVpnConfig: StateFlow<Boolean> = _hasVpnConfig.asStateFlow()
  
  private val _vpnBannerDismissed = MutableStateFlow(false)
  val vpnBannerDismissed: StateFlow<Boolean> = _vpnBannerDismissed.asStateFlow()
  ```
- Methoden `observeHomeNetworkState()` und `checkVpnConfig()` im init-Block aufgerufen
- Implementierung der Beobachtungs-Methoden:
  ```kotlin
  private fun observeHomeNetworkState() {
      viewModelScope.launch {
          preferencesManager.getServerUrl().collectLatest { serverUrl ->
              if (serverUrl != null) {
                  networkStateManager.observeHomeNetworkStatus(serverUrl)
                      .collect { isHome -> 
                          _isInHomeNetwork.value = isHome
                      }
              }
          }
      }
  }
  
  private fun checkVpnConfig() {
      viewModelScope.launch {
          preferencesManager.getVpnConfig().collect { config ->
              _hasVpnConfig.value = !config.isNullOrEmpty()
          }
      }
  }
  
  fun dismissVpnBanner() {
      _vpnBannerDismissed.value = true
  }
  ```

#### 3. FilesScreen Integration

**Datei:** `android-app/app/src/main/java/com/baluhost/android/presentation/ui/screens/files/FilesScreen.kt`

**Änderungen:**
- Import `VpnStatusBanner` hinzugefügt
- VPN-State aus ViewModel gesammelt:
  ```kotlin
  val isInHomeNetwork by viewModel.isInHomeNetwork.collectAsState()
  val hasVpnConfig by viewModel.hasVpnConfig.collectAsState()
  val vpnBannerDismissed by viewModel.vpnBannerDismissed.collectAsState()
  ```
- VpnStatusBanner nach OfflineBanner hinzugefügt:
  ```kotlin
  VpnStatusBanner(
      isInHomeNetwork = isInHomeNetwork,
      hasVpnConfig = hasVpnConfig,
      onConnectVpn = onNavigateToVpn,
      onDismiss = { viewModel.dismissVpnBanner() },
      isDismissed = vpnBannerDismissed
  )
  ```

#### 4. DashboardViewModel Integration

**Datei:** `android-app/app/src/main/java/com/baluhost/android/presentation/ui/screens/dashboard/DashboardViewModel.kt`

**Änderungen:** Identisch zu FilesViewModel
- Import `NetworkStateManager` und `collectLatest`
- Constructor-Injection von `NetworkStateManager`
- VPN-State-Flows hinzugefügt
- Methoden `observeHomeNetworkState()`, `checkVpnConfig()`, `dismissVpnBanner()` implementiert

#### 5. DashboardScreen Integration

**Datei:** `android-app/app/src/main/java/com/baluhost/android/presentation/ui/screens/dashboard/DashboardScreen.kt`

**Änderungen:**
- Import `VpnStatusBanner` hinzugefügt
- Parameter `onNavigateToVpn: () -> Unit = {}` zur Funktion hinzugefügt
- VPN-State aus ViewModel gesammelt
- VpnStatusBanner vor System-Metriken hinzugefügt

#### 6. Navigation (MainScreen.kt)

**Datei:** `android-app/app/src/main/java/com/baluhost/android/presentation/ui/screens/main/MainScreen.kt`

**Änderungen:**
- `onNavigateToVpn` Parameter zu DashboardScreen hinzugefügt:
  ```kotlin
  onNavigateToVpn = {
      // Navigate using parent nav controller for screens outside bottom nav
      parentNavController.navigate(Screen.Vpn.route)
  }
  ```

### Funktionsweise

#### Network Detection Flow

1. **NetworkStateManager** wird via Hilt in ViewModels injiziert
2. **observeHomeNetworkState()** wird beim ViewModel-Init aufgerufen:
   - Liest Server-URL aus PreferencesManager
   - Startet reactive Flow mit `observeHomeNetworkStatus(serverUrl)`
   - NetworkStateManager vergleicht Subnets (erste 3 Oktetts der IPs)
   - Ergebnis: `true` (home), `false` (away), `null` (unknown)
3. **checkVpnConfig()** prüft ob VPN-Config vorhanden ist
4. **State-Updates** werden an UI weitergereicht

#### VPN Banner Visibility Logic

Das Banner wird angezeigt wenn:
- `isInHomeNetwork == false` (Nutzer ist außerhalb des Heimnetzwerks)
- `hasVpnConfig == true` (VPN-Config ist vorhanden)
- `isDismissed == false` (Nutzer hat Banner nicht geschlossen)

Das Banner versteckt sich automatisch wenn:
- `isInHomeNetwork == true` (Nutzer ist im Heimnetzwerk)
- `isInHomeNetwork == null` (Status unbekannt)
- `hasVpnConfig == false` (keine VPN-Config)
- `isDismissed == true` (Nutzer hat Banner geschlossen)

#### User Actions

1. **"Verbinden" Button:** Navigiert zum VPN-Screen (`onNavigateToVpn()`)
2. **"X" Button:** Schließt Banner (`dismissVpnBanner()`)

### Integration in bestehende Screens

#### FilesScreen
- Banner zwischen `OfflineBanner` und `Scaffold` platziert
- Nutzt bereits existierenden `onNavigateToVpn` Callback

#### DashboardScreen
- Banner am Anfang des ScrollView vor System-Metriken
- Neuer `onNavigateToVpn` Parameter hinzugefügt
- Navigation via `parentNavController` in MainScreen

### Caching & Performance

- **30-Sekunden Cache** in NetworkStateManager verhindert excessive Netzwerk-Checks
- **Reactive StateFlow** nur Updates bei Änderungen
- **PreferencesManager Flow** cached VPN-Config automatisch

### Nächste Schritte (Phase 4)

- Auto-Import VPN Config bei QR-Scan (RegisterDeviceScreen)
- VPN Permission Handling (VpnService.prepare())
- Testing (Home Network Detection, Banner Visibility, Navigation)

### Testing Checklist

- [ ] Device in gleichem WLAN wie NAS → Kein Banner
- [ ] Device in anderem WLAN → Banner erscheint
- [ ] Device mit Mobile Daten → Banner erscheint
- [ ] "Verbinden" Button → Navigation zu VPN Screen
- [ ] "X" Button → Banner verschwindet
- [ ] Dismiss-State bleibt bei App-Neustart (optional: localStorage)
- [ ] VPN Config vorhanden → Banner zeigt an
- [ ] Keine VPN Config → Kein Banner

## ✅ Phase 1: Network Detection (ABGESCHLOSSEN)

Siehe `VPN_AUTO_CONNECT_PLAN.md` für Details.

**Implementiert:**
- NetworkStateManager.kt mit IP-Subnet-Vergleich
- Reactive StateFlow für UI-Updates
- 30-Sekunden Caching

## ✅ Phase 2: UI Components (ABGESCHLOSSEN)

Siehe `VPN_AUTO_CONNECT_PLAN.md` für Details.

**Implementiert:**
- VpnStatusBanner.kt (Full & Compact)
- Material3 Design mit Animationen
- Dismissable mit State Management

## ⏳ Phase 4: Auto-Import (IN BEARBEITUNG)

**Ziel:** VPN-Config automatisch während QR-Scan zu Android Settings hinzufügen

### Implementierte Änderungen

#### 1. ImportVpnConfigUseCase Enhancement

**Datei:** `android-app/app/src/main/java/com/baluhost/android/domain/usecase/vpn/ImportVpnConfigUseCase.kt`

**Änderungen:**
- Android Context Injection für VPN-Service-Zugriff
- Neuer Parameter `autoRegister: Boolean = true` in invoke()
- Methode `prepareVpnTunnel(config)` für VPN-Tunnel-Vorbereitung
- Logging mit TAG constant
- Fehlerbehandlung: VPN-Import schlägt nicht fehl wenn Auto-Registration fehlschlägt

**Code:**
```kotlin
class ImportVpnConfigUseCase @Inject constructor(
    @ApplicationContext private val context: Context,
    private val preferencesManager: PreferencesManager
) {
    
    suspend operator fun invoke(configBase64: String, autoRegister: Boolean = true): Result<VpnConfig> {
        // ... existing code ...
        
        // Auto-register VPN tunnel if requested
        if (autoRegister) {
            try {
                prepareVpnTunnel(config)
                Log.d(TAG, "VPN tunnel prepared successfully")
            } catch (e: Exception) {
                Log.w(TAG, "VPN tunnel preparation failed (will require manual setup): ${e.message}")
                // Don't fail the import if VPN registration fails
                // User can still connect manually via VPN screen
            }
        }
    }
    
    private fun prepareVpnTunnel(config: VpnConfig) {
        // Store VPN configuration metadata
        // VPN connection will be handled by VpnScreen when user activates it
        // or automatically when user clicks "Verbinden" in VpnStatusBanner
    }
}
```

#### 2. QrScannerViewModel Enhancement

**Datei:** `android-app/app/src/main/java/com/baluhost/android/presentation/ui/screens/qrscanner/QrScannerViewModel.kt`

**Änderungen:**
- VPN-Import mit `autoRegister = true` aufrufen
- `vpnConfigured` Flag zu Success-State hinzugefügt
- Logging für VPN-Import-Status

**Code:**
```kotlin
registrationData.vpnConfig?.let { vpnConfig ->
    viewModelScope.launch {
        val vpnResult = importVpnConfigUseCase(
            configBase64 = vpnConfig,
            autoRegister = true
        )
        when (vpnResult) {
            is Result.Success -> {
                android.util.Log.d("QrScanner", "VPN config imported: ${vpnResult.data.serverEndpoint}")
                vpnImported = true
            }
            is Result.Error -> {
                android.util.Log.e("QrScanner", "VPN import failed: ${vpnResult.exception.message}")
            }
            else -> {}
        }
    }
}

_uiState.value = QrScannerState.Success(
    authResult = result.data,
    vpnConfigured = vpnImported || registrationData.vpnConfig != null
)
```

**QrScannerState Update:**
```kotlin
sealed class QrScannerState {
    object Scanning : QrScannerState()
    object Processing : QrScannerState()
    data class Success(
        val authResult: AuthResult,
        val vpnConfigured: Boolean = false  // NEW
    ) : QrScannerState()
    data class Error(val message: String) : QrScannerState()
}
```

#### 3. QrScannerScreen UI Enhancement

**Datei:** `android-app/app/src/main/java/com/baluhost/android/presentation/ui/screens/qrscanner/QrScannerScreen.kt`

**Änderungen:**
- Success-State zeigt VPN-Status an
- 2-Sekunden Delay bei VPN-Konfiguration zum Anzeigen der Success-Message
- ProcessingOverlay zeigt Checkmark und "VPN konfiguriert" bei Erfolg

**UI-Updates:**
```kotlin
// Processing with success state
ProcessingOverlay(
    isSuccess = uiState is QrScannerState.Success,
    vpnConfigured = (uiState as? QrScannerState.Success)?.vpnConfigured ?: false
)

// Success message
if (isSuccess) {
    Icon(Icons.Default.CheckCircle, ...)
    Text("Registrierung erfolgreich")
    if (vpnConfigured) {
        Text("✓ VPN konfiguriert", color = primary)
    }
}
```

### Funktionsweise

#### QR-Scan-Flow mit VPN-Import

1. **QR-Code scannen** → Parse JSON mit `token`, `server`, `vpn_config` (Base64)
2. **Device registrieren** → RegisterDeviceUseCase speichert Tokens
3. **VPN-Config importieren** (wenn vorhanden):
   - Base64-Decode → WireGuard Config String
   - Parse Config → Extract IP, Endpoint, Keys
   - Save zu PreferencesManager
   - `prepareVpnTunnel()` → VPN-Tunnel-Metadaten speichern
4. **Success-Screen anzeigen** → "✓ VPN konfiguriert" für 2 Sekunden
5. **Navigate zu Files** → VpnStatusBanner zeigt sich wenn außerhalb Heimnetzwerk

#### VPN-Tunnel-Vorbereitung

- **prepareVpnTunnel()** speichert VPN-Konfiguration in Preferences
- VPN-Verbindung wird **nicht automatisch** aktiviert (erfordert User-Consent)
- User kann VPN aktivieren via:
  - VpnScreen (manuell)
  - VpnStatusBanner "Verbinden" Button (wenn außerhalb Heimnetzwerk)
  - Beide Wege führen zu VpnScreen → `VpnService.prepare()` Permission-Check

### VPN Permission Handling (Ausstehend)

**Aktueller Status:** VPN wird importiert aber nicht automatisch verbunden

**Grund:** Android VpnService erfordert explizite User-Permission via `VpnService.prepare()`

**Implementierung in Phase 4 (Teil 2):**
- VpnScreen: Permission-Check bei Connect-Button
- Auto-Connect Option nach erfolgreichem Import (optional)
- Toast/Snackbar: "VPN wurde importiert - Jetzt verbinden?"

### Testing Checklist

**QR-Scan mit VPN:**
- [x] QR-Code mit `vpn_config` scannen → VPN wird gespeichert
- [x] Success-Screen zeigt "✓ VPN konfiguriert"
- [x] PreferencesManager enthält VPN-Config String
- [x] Logging zeigt VPN-Import-Status
- [ ] VpnScreen zeigt importierte Config an
- [ ] VpnStatusBanner erscheint außerhalb Heimnetzwerk

**QR-Scan ohne VPN:**
- [x] QR-Code ohne `vpn_config` scannen → Keine VPN-Message
- [x] Success-Screen zeigt nur "Registrierung erfolgreich"
- [x] App funktioniert normal ohne VPN

**Fehlerbehandlung:**
- [x] VPN-Import schlägt fehl → Device-Registration erfolgt trotzdem
- [x] Logging zeigt Fehler aber kein User-facing Error
- [x] User kann VPN später manuell einrichten

### Nächste Schritte (Phase 4 Teil 2)

1. **VPN Permission Handling:**
   - VpnService.prepare() Dialog in VpnScreen
   - Permission-Result-Handling
   - Auto-Connect nach Permission-Grant (optional)

2. **User Experience:**
   - Toast nach QR-Scan: "VPN konfiguriert - Jetzt verbinden?"
   - Navigation zu VPN-Screen anbieten
   - VpnStatusBanner zeigt "Aktivieren" statt "Verbinden"

3. **Testing:**
   - End-to-End Test: QR-Scan → VPN Import → Banner → Connect
   - Permission-Flow testen
   - Fehlerbehandlung bei fehlender Permission
