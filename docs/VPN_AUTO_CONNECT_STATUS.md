# VPN Auto-Connect - Implementierungs-Status

## ✅ Komplett implementiert

### Phase 1: Network State Detection
- ✅ **NetworkStateManager.kt** erstellt
  - IP Subnet Vergleich (192.168.x.x)
  - Keine Location Permission benötigt
  - Caching (30s)
  - Reactive Flow Support
  - Methoden:
    - `checkHomeNetworkStatus(serverUrl)` - Sync check
    - `observeHomeNetworkStatus(serverUrl)` - Flow für Reactive UI
    - `isSameSubnet()` - IPv4 Subnet Matching

### Phase 2: VPN Status Banner UI  
- ✅ **VpnStatusBanner.kt** erstellt
  - Standard Banner (mit Icon, Nachricht, Connect-Button)
  - Compact Banner (für kleinere Screens)
  - Animated Visibility
  - Dismissable
  - Orange Warning Design

## 📋 Noch zu tun (Integration)

### Phase 3: Banner Integration in Screens

#### 3.1 FilesViewModel erweitern
```kotlin
// FilesViewModel.kt

@HiltViewModel
class FilesViewModel @Inject constructor(
    // ... existing dependencies
    private val networkStateManager: NetworkStateManager,
    private val preferencesManager: PreferencesManager
) : ViewModel() {
    
    // Network state
    private val _isInHomeNetwork = MutableStateFlow<Boolean?>(null)
    val isInHomeNetwork: StateFlow<Boolean?> = _isInHomeNetwork.asStateFlow()
    
    private val _hasVpnConfig = MutableStateFlow(false)
    val hasVpnConfig: StateFlow<Boolean> = _hasVpnConfig.asStateFlow()
    
    private val _vpnBannerDismissed = MutableStateFlow(false)
    val vpnBannerDismissed: StateFlow<Boolean> = _vpnBannerDismissed.asStateFlow()
    
    init {
        // ... existing init
        observeNetworkState()
        checkVpnConfig()
    }
    
    private fun observeNetworkState() {
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
        // Optional: Save to preferences for persistent dismiss
    }
}
```

#### 3.2 FilesScreen.kt - Banner hinzufügen
```kotlin
@Composable
fun FilesScreen(
    // ... existing params
    navController: NavController
) {
    val viewModel: FilesViewModel = hiltViewModel()
    val uiState by viewModel.uiState.collectAsState()
    
    // VPN State
    val isInHomeNetwork by viewModel.isInHomeNetwork.collectAsState()
    val hasVpnConfig by viewModel.hasVpnConfig.collectAsState()
    val vpnBannerDismissed by viewModel.vpnBannerDismissed.collectAsState()
    
    Scaffold(
        topBar = {
            // ... existing TopAppBar
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // VPN Status Banner (Top)
            VpnStatusBanner(
                isInHomeNetwork = isInHomeNetwork,
                hasVpnConfig = hasVpnConfig,
                onConnectVpn = {
                    navController.navigate("vpn")
                },
                onDismiss = {
                    viewModel.dismissVpnBanner()
                },
                isDismissed = vpnBannerDismissed
            )
            
            // Rest of UI
            // ...
        }
    }
}
```

#### 3.3 Gleiche Integration für DashboardScreen

### Phase 4: Auto-Import VPN Config

#### 4.1 ImportVpnConfigUseCase erweitern
```kotlin
// ImportVpnConfigUseCase.kt

class ImportVpnConfigUseCase @Inject constructor(
    private val preferencesManager: PreferencesManager,
    private val context: Context
) {
    
    suspend operator fun invoke(qrData: String): Result<VpnConfig> {
        return try {
            // Parse QR code JSON
            val data = Json.decodeFromString<RegistrationData>(qrData)
            val vpnConfigBase64 = data.vpn_config ?: return Result.failure(
                Exception("No VPN config in QR code")
            )
            
            // Decode Base64
            val configContent = String(
                Base64.decode(vpnConfigBase64, Base64.DEFAULT)
            )
            
            // Parse WireGuard config
            val config = parseWireGuardConfig(configContent)
            
            // Save to preferences
            preferencesManager.saveVpnConfig(configContent)
            
            // *** AUTO-REGISTER in Android VPN ***
            registerVpnTunnel(config, configContent)
            
            Result.success(config)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    private suspend fun registerVpnTunnel(
        config: VpnConfig,
        configContent: String
    ) {
        // Request VPN permission
        val intent = VpnService.prepare(context)
        if (intent != null) {
            // User needs to grant permission
            // TODO: Show permission dialog
        }
        
        // Create WireGuard tunnel
        // This requires WireGuard Android library
        val tunnel = Tunnel.create("BaluHost VPN", configContent)
        
        // Save tunnel (will appear in Android VPN settings)
        TunnelManager.addTunnel(tunnel)
    }
}
```

#### 4.2 RegisterDeviceScreen.kt - QR Scan Integration
```kotlin
// Nach erfolgreicher QR-Scan:
LaunchedEffect(scanResult) {
    if (scanResult != null) {
        val result = importVpnConfigUseCase(scanResult)
        
        result.onSuccess { vpnConfig ->
            // Show success message
            Toast.makeText(
                context,
                "VPN-Konfiguration automatisch eingerichtet!",
                Toast.LENGTH_LONG
            ).show()
            
            // Optionally navigate to VPN screen
            navController.navigate("vpn")
        }
        
        result.onFailure { error ->
            // VPN import failed, but device registration might still work
            Log.e("RegisterDevice", "VPN import failed", error)
        }
    }
}
```

### Phase 5: DI Module Setup

#### 5.1 NetworkModule.kt erstellen/erweitern
```kotlin
@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    
    @Provides
    @Singleton
    fun provideNetworkMonitor(
        @ApplicationContext context: Context
    ): NetworkMonitor {
        return NetworkMonitorImpl(context)
    }
    
    @Provides
    @Singleton
    fun provideNetworkStateManager(
        @ApplicationContext context: Context,
        networkMonitor: NetworkMonitor
    ): NetworkStateManager {
        return NetworkStateManager(context, networkMonitor)
    }
}
```

## 🔧 Benötigte Dependencies

### build.gradle (app level)
```gradle
dependencies {
    // ... existing

    // WireGuard for VPN Auto-Registration (optional)
    implementation 'com.wireguard.android:tunnel:1.0.20230427'
}
```

## 📝 Testing Checklist

1. [ ] **Heimnetz-Erkennung**
   - [ ] App im gleichen WLAN wie NAS → Kein Banner
   - [ ] App in anderem WLAN → Banner erscheint
   - [ ] App mit mobilen Daten → Banner erscheint
   - [ ] Banner-Dismiss funktioniert

2. [ ] **VPN Connect Button**
   - [ ] Click auf "Verbinden" → Navigation zu VpnScreen
   - [ ] VpnScreen öffnet sich korrekt

3. [ ] **Auto-Import**
   - [ ] QR-Code scannen → VPN Config automatisch gespeichert
   - [ ] Android VPN Settings → Tunnel "BaluHost VPN" sichtbar
   - [ ] VPN Permission Dialog erscheint

4. [ ] **Banner Visibility**
   - [ ] Banner verschwindet nach VPN-Connect
   - [ ] Banner erscheint wieder nach VPN-Disconnect (wenn außerhalb Heimnetz)

## ⚠️ Known Issues & Limitations

1. **VPN Auto-Registration:** Benötigt WireGuard Library oder Custom VPN Service
2. **Permission Handling:** VPN Permission muss vom User granted werden
3. **IP Detection:** Funktioniert nur mit IPv4, nicht mit IPv6
4. **Domain Names:** Wenn Server-URL ein Domain-Name ist (statt IP), kann Heimnetz nicht erkannt werden
5. **VPN-on-VPN:** Wenn User bereits ein anderes VPN nutzt, kann Detection fehlschlagen

## 🚀 Next Steps (Priorität)

1. **High:** ViewModels erweitern (FilesViewModel, DashboardViewModel)
2. **High:** Banner in Screens integrieren
3. **Medium:** DI Module Setup
4. **Medium:** Auto-Import VPN Config implementieren
5. **Low:** WireGuard Tunnel Registration (optional, komplex)

## 📚 Alternative Ansätze

### Vereinfachte Version (ohne Auto-Registration):
- Zeige nur Banner mit "VPN aktivieren" Hinweis
- User navigiert manuell zu VpnScreen
- User aktiviert VPN manuell
- **Vorteil:** Einfacher, weniger Permissions
- **Nachteil:** Mehr User-Interaktion nötig

### Erweiterte Version (mit Auto-Connect):
- Background Service überwacht Netzwerk-Status
- Verbindet VPN automatisch wenn außerhalb Heimnetz
- Trennt VPN automatisch wenn im Heimnetz
- **Vorteil:** Zero-Touch UX
- **Nachteil:** Battery Drain, Permissions, Komplex

---

**Empfehlung:** Start mit vereinfachter Version (nur Banner), dann Optional Auto-Connect später hinzufügen.
