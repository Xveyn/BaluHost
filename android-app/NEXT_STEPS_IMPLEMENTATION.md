# BaluHost Android App - Konkrete nächste Schritte

**Zeitraum:** Diese Woche (KW 1)  
**Priorität:** VPN Configuration + Settings  
**Geschätzter Aufwand:** 5-6 Tage Entwicklung

---

## 🚀 Schritt 1: VPN Configuration Management

### 1.1 Backend vorbereiten (Koordination mit Backend-Team)

**Datei:** `backend/app/api/routes/mobile.py` oder neue `vpn.py`

```python
# GET /api/mobile/vpn/config
# Gibt WireGuard Config für das Device zurück
# Response:
{
    "device_id": "device-123",
    "config": "[Interface]\n...",  # WireGuard INI format
    "server_address": "vpn.baluhost.local",
    "client_ip": "10.0.0.2",
    "dns": ["10.0.0.1"],
    "allowed_ips": "10.0.0.0/24",
    "created_at": "2026-01-04T00:00:00Z",
    "expires_at": "2026-02-04T00:00:00Z"  # optional
}

# POST /api/mobile/vpn/config
# Ermöglicht Config-Update/Regeneration
# Request:
{
    "device_id": "device-123",
    "regenerate": true  # optional, für neue Keys
}
# Response: wie GET
```

### 1.2 Android Implementation

**Datei:** `app/src/main/java/com/baluhost/android/data/remote/api/VpnApi.kt`

```kotlin
package com.baluhost.android.data.remote.api

import com.baluhost.android.data.remote.dto.VpnConfigDto
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Body

interface VpnApi {
    @GET("mobile/vpn/config")
    suspend fun getVpnConfig(): ApiResponse<VpnConfigDto>
    
    @POST("mobile/vpn/config")
    suspend fun regenerateVpnConfig(
        @Body request: RegenerateVpnConfigRequest
    ): ApiResponse<VpnConfigDto>
}

data class VpnConfigDto(
    val deviceId: String,
    val config: String,  // WireGuard config string
    val serverAddress: String,
    val clientIp: String,
    val dns: List<String>,
    val allowedIps: String,
    val createdAt: String,
    val expiresAt: String? = null
)

data class RegenerateVpnConfigRequest(
    val deviceId: String,
    val regenerate: Boolean = true
)
```

**Datei:** `app/src/main/java/com/baluhost/android/domain/repository/VpnRepository.kt`

```kotlin
package com.baluhost.android.domain.repository

import com.baluhost.android.domain.model.Result
import com.baluhost.android.domain.model.VpnConfig
import kotlinx.coroutines.flow.Flow

interface VpnRepository {
    suspend fun getVpnConfig(): Result<VpnConfig>
    suspend fun regenerateConfig(): Result<VpnConfig>
    suspend fun saveConfig(config: VpnConfig): Result<Unit>
    suspend fun getLocalConfig(): VpnConfig?
    fun observeVpnConfig(): Flow<VpnConfig?>
}
```

**Datei:** `app/src/main/java/com/baluhost/android/data/repository/VpnRepositoryImpl.kt`

```kotlin
package com.baluhost.android.data.repository

import com.baluhost.android.data.local.preferences.SecureStorage
import com.baluhost.android.data.remote.api.VpnApi
import com.baluhost.android.domain.model.Result
import com.baluhost.android.domain.model.VpnConfig
import com.baluhost.android.domain.repository.VpnRepository
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import javax.inject.Inject

class VpnRepositoryImpl @Inject constructor(
    private val vpnApi: VpnApi,
    private val secureStorage: SecureStorage
) : VpnRepository {
    
    override suspend fun getVpnConfig(): Result<VpnConfig> = try {
        val response = vpnApi.getVpnConfig()
        if (response.success) {
            val config = response.data.toDomain()
            saveConfig(Result.Success(config))  // Cache locally
            Result.Success(config)
        } else {
            Result.Error(response.error?.message ?: "Unknown error")
        }
    } catch (e: Exception) {
        Result.Error(e.message ?: "Network error")
    }
    
    override suspend fun saveConfig(config: VpnConfig): Result<Unit> = try {
        secureStorage.saveVpnConfig(config)
        Result.Success(Unit)
    } catch (e: Exception) {
        Result.Error(e.message ?: "Storage error")
    }
    
    override suspend fun getLocalConfig(): VpnConfig? =
        secureStorage.getVpnConfig()
    
    override fun observeVpnConfig(): Flow<VpnConfig?> = flow {
        emit(getLocalConfig())
        try {
            val config = getVpnConfig()
            if (config is Result.Success) {
                emit(config.data)
            }
        } catch (e: Exception) {
            // Keep previous value on error
        }
    }
}

// Mapper Extension
fun VpnConfigDto.toDomain() = VpnConfig(
    deviceId = deviceId,
    configString = config,
    serverAddress = serverAddress,
    clientIp = clientIp,
    dns = dns,
    allowedIps = allowedIps,
    createdAt = Instant.parse(createdAt),
    expiresAt = expiresAt?.let { Instant.parse(it) }
)
```

**Datei:** `app/src/main/java/com/baluhost/android/domain/model/VpnConfig.kt`

```kotlin
package com.baluhost.android.domain.model

import java.time.Instant

data class VpnConfig(
    val deviceId: String,
    val configString: String,  // Full WireGuard config
    val serverAddress: String,
    val clientIp: String,
    val dns: List<String> = emptyList(),
    val allowedIps: String,
    val createdAt: Instant,
    val expiresAt: Instant? = null
)
```

**Datei:** `app/src/main/java/com/baluhost/android/domain/usecase/FetchVpnConfigUseCase.kt`

```kotlin
package com.baluhost.android.domain.usecase

import com.baluhost.android.domain.model.Result
import com.baluhost.android.domain.model.VpnConfig
import com.baluhost.android.domain.repository.VpnRepository
import javax.inject.Inject

class FetchVpnConfigUseCase @Inject constructor(
    private val vpnRepository: VpnRepository
) {
    suspend operator fun invoke(): Result<VpnConfig> {
        // Try remote first
        val remoteResult = vpnRepository.getVpnConfig()
        if (remoteResult is Result.Success) {
            return remoteResult
        }
        
        // Fallback to local cache
        val localConfig = vpnRepository.getLocalConfig()
        return if (localConfig != null) {
            Result.Success(localConfig)
        } else {
            remoteResult
        }
    }
}
```

**Datei:** `app/src/main/java/com/baluhost/android/presentation/viewmodel/VpnViewModel.kt`

```kotlin
package com.baluhost.android.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baluhost.android.domain.model.Result
import com.baluhost.android.domain.model.VpnConfig
import com.baluhost.android.domain.usecase.FetchVpnConfigUseCase
import com.baluhost.android.service.vpn.VpnManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class VpnUiState(
    val config: VpnConfig? = null,
    val isConnected: Boolean = false,
    val isLoading: Boolean = false,
    val error: String? = null,
    val message: String? = null
)

@HiltViewModel
class VpnViewModel @Inject constructor(
    private val fetchVpnConfigUseCase: FetchVpnConfigUseCase,
    private val vpnManager: VpnManager
) : ViewModel() {
    
    private val _uiState = MutableStateFlow(VpnUiState())
    val uiState: StateFlow<VpnUiState> = _uiState.asStateFlow()
    
    init {
        loadVpnConfig()
    }
    
    fun loadVpnConfig() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            when (val result = fetchVpnConfigUseCase()) {
                is Result.Success -> {
                    _uiState.update { 
                        it.copy(config = result.data, isLoading = false) 
                    }
                }
                is Result.Error -> {
                    _uiState.update {
                        it.copy(
                            error = result.message,
                            isLoading = false
                        )
                    }
                }
            }
        }
    }
    
    fun connect() {
        val config = _uiState.value.config ?: return
        viewModelScope.launch {
            try {
                _uiState.update { it.copy(isLoading = true, error = null) }
                vpnManager.connect(config.configString)
                _uiState.update {
                    it.copy(
                        isConnected = true,
                        isLoading = false,
                        message = "VPN verbunden"
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        error = e.message,
                        isLoading = false
                    )
                }
            }
        }
    }
    
    fun disconnect() {
        viewModelScope.launch {
            try {
                _uiState.update { it.copy(isLoading = true, error = null) }
                vpnManager.disconnect()
                _uiState.update {
                    it.copy(
                        isConnected = false,
                        isLoading = false,
                        message = "VPN getrennt"
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        error = e.message,
                        isLoading = false
                    )
                }
            }
        }
    }
    
    fun refreshConfig() {
        loadVpnConfig()
    }
}
```

### 1.3 VPN UI Screen

**Datei:** `app/src/main/java/com/baluhost/android/presentation/ui/screen/VpnScreen.kt`

```kotlin
package com.baluhost.android.presentation.ui.screen

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Security
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.hilt.navigation.compose.hiltViewModel
import com.baluhost.android.presentation.viewmodel.VpnViewModel

@Composable
fun VpnScreen(
    viewModel: VpnViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Header
        TopAppBar(
            title = { Text("VPN Verbindung") },
            actions = {
                IconButton(onClick = { viewModel.refreshConfig() }) {
                    Icon(Icons.Default.Refresh, contentDescription = "Aktualisieren")
                }
            }
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        // Status Card
        ElevatedCard(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Verbindungsstatus", style = MaterialTheme.typography.titleMedium)
                
                Spacer(modifier = Modifier.height(8.dp))
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                ) {
                    Text(
                        if (uiState.isConnected) "Verbunden" else "Getrennt",
                        style = MaterialTheme.typography.bodyLarge,
                        color = if (uiState.isConnected) 
                            Color.Green else Color.Red
                    )
                    
                    switch(
                        checked = uiState.isConnected,
                        onCheckedChange = { isChecked ->
                            if (isChecked) viewModel.connect()
                            else viewModel.disconnect()
                        },
                        enabled = !uiState.isLoading
                    )
                }
            }
        }
        
        // Config Info
        uiState.config?.let { config ->
            ElevatedCard(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Verbindungsinformationen", style = MaterialTheme.typography.titleMedium)
                    
                    Spacer(modifier = Modifier.height(8.dp))
                    
                    InfoRow("Server:", config.serverAddress)
                    InfoRow("Client IP:", config.clientIp)
                    InfoRow("Erlaubte IPs:", config.allowedIps)
                    if (config.dns.isNotEmpty()) {
                        InfoRow("DNS:", config.dns.joinToString(", "))
                    }
                }
            }
        }
        
        // Error Display
        uiState.error?.let { error ->
            ElevatedCard(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.elevatedCardColors(
                    containerColor = Color(0xFFFFEBEE)
                )
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Fehler", style = MaterialTheme.typography.titleMedium, color = Color.Red)
                    Text(error, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        
        // Success Message
        uiState.message?.let { message ->
            Snackbar(
                modifier = Modifier
                    .align(Alignment.CenterHorizontally)
                    .padding(16.dp)
            ) {
                Text(message)
            }
        }
        
        // Loading State
        if (uiState.isLoading) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.CenterHorizontally))
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = Color.Gray)
        Text(value, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold)
    }
}
```

### 1.4 Hilt Module Update

**Datei:** `app/src/main/java/com/baluhost/android/di/RepositoryModule.kt`

```kotlin
// Add to existing module or create new one
@Module
@InstallIn(SingletonComponent::class)
object VpnModule {
    
    @Provides
    @Singleton
    fun provideVpnRepository(impl: VpnRepositoryImpl): VpnRepository = impl
    
    @Provides
    @Singleton
    fun provideFetchVpnConfigUseCase(
        repository: VpnRepository
    ): FetchVpnConfigUseCase = FetchVpnConfigUseCase(repository)
}
```

---

## 🎯 Schritt 2: Settings Screen

### 2.1 Settings Data Model

**Datei:** `app/src/main/java/com/baluhost/android/domain/model/AppSettings.kt`

```kotlin
package com.baluhost.android.domain.model

data class AppSettings(
    // Connection Settings
    val baseUrl: String = "",
    val deviceName: String = "",
    
    // Sync Settings
    val autoSyncEnabled: Boolean = true,
    val syncIntervalMinutes: Int = 15,
    val wifiOnlySync: Boolean = false,
    val bandwidthLimitMbps: Int? = null,
    
    // Backup Settings
    val cameraBackupEnabled: Boolean = false,
    val autoPhotoBackup: Boolean = false,
    val autoVideoBackup: Boolean = false,
    val backupFrequencyHours: Int = 6,
    
    // Notification Settings
    val syncNotificationsEnabled: Boolean = true,
    val errorNotificationsEnabled: Boolean = true,
    val downloadNotificationsEnabled: Boolean = true,
    val offlineAlertsEnabled: Boolean = true,
    
    // App Info
    val appVersion: String = "",
    val lastSyncTime: Instant? = null
)
```

### 2.2 Settings Repository

**Datei:** `app/src/main/java/com/baluhost/android/data/repository/SettingsRepository.kt`

```kotlin
interface SettingsRepository {
    suspend fun getSettings(): Result<AppSettings>
    suspend fun updateSettings(settings: AppSettings): Result<Unit>
    fun observeSettings(): Flow<AppSettings>
    suspend fun resetSettings(): Result<Unit>
}

class SettingsRepositoryImpl @Inject constructor(
    private val dataStore: DataStore<Preferences>
) : SettingsRepository {
    // Implementation mit DataStore
}
```

### 2.3 Settings ViewModel

```kotlin
@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val settingsRepository: SettingsRepository
) : ViewModel() {
    val settings: StateFlow<AppSettings> = ...
    
    fun updateSetting(key: String, value: Any) { /* ... */ }
    fun resetSettings() { /* ... */ }
    fun logout() { /* ... */ }
}
```

### 2.4 Settings Screen UI

```kotlin
@Composable
fun SettingsScreen(
    viewModel: SettingsViewModel = hiltViewModel(),
    onNavigateBack: () -> Unit
) {
    val settings by viewModel.settings.collectAsState()
    
    Column(modifier = Modifier.fillMaxSize()) {
        TopAppBar(title = { Text("Einstellungen") })
        
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Connection Settings Section
            item {
                SettingsSection("Verbindung") {
                    SettingItem("Server:", settings.baseUrl)
                    SettingItem("Geräte-Name:", settings.deviceName)
                }
            }
            
            // Sync Settings Section
            item {
                SettingsSection("Synchronisierung") {
                    ToggleSetting(
                        "Auto-Sync aktiviert",
                        settings.autoSyncEnabled,
                        { viewModel.updateSetting("autoSync", it) }
                    )
                    if (settings.autoSyncEnabled) {
                        SliderSetting(
                            "Sync-Intervall (Minuten)",
                            settings.syncIntervalMinutes.toFloat(),
                            5f..60f
                        )
                    }
                    ToggleSetting(
                        "Nur WiFi",
                        settings.wifiOnlySync,
                        { viewModel.updateSetting("wifiOnly", it) }
                    )
                }
            }
            
            // Backup Settings Section
            item {
                SettingsSection("Sicherung") {
                    ToggleSetting(
                        "Kamera-Backup",
                        settings.cameraBackupEnabled,
                        { viewModel.updateSetting("cameraBackup", it) }
                    )
                    if (settings.cameraBackupEnabled) {
                        ToggleSetting(
                            "Fotos automatisch sichern",
                            settings.autoPhotoBackup,
                            { viewModel.updateSetting("autoPhotoBackup", it) }
                        )
                        ToggleSetting(
                            "Videos automatisch sichern",
                            settings.autoVideoBackup,
                            { viewModel.updateSetting("autoVideoBackup", it) }
                        )
                    }
                }
            }
            
            // Notification Settings
            item {
                SettingsSection("Benachrichtigungen") {
                    ToggleSetting(
                        "Sync-Benachrichtigungen",
                        settings.syncNotificationsEnabled,
                        { viewModel.updateSetting("syncNotify", it) }
                    )
                    ToggleSetting(
                        "Fehler-Benachrichtigungen",
                        settings.errorNotificationsEnabled,
                        { viewModel.updateSetting("errorNotify", it) }
                    )
                }
            }
            
            // Advanced
            item {
                SettingsSection("Erweitert") {
                    Button(
                        onClick = { viewModel.resetSettings() },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("Auf Standard zurücksetzen")
                    }
                    Button(
                        onClick = { viewModel.logout() },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Color.Red
                        )
                    ) {
                        Text("Abmelden")
                    }
                }
            }
        }
    }
}
```

---

## ✅ Checkliste für diese Woche

- [ ] Backend Endpoint `/api/mobile/vpn/config` implementiert
- [ ] VpnApi + DTO + Domain Model erstellt
- [ ] VpnRepository + RepositoryImpl fertig
- [ ] FetchVpnConfigUseCase implementiert
- [ ] VpnViewModel mit State Management
- [ ] VpnScreen UI fertig
- [ ] Hilt Module konfiguriert
- [ ] Manual Testing mit Backend durchgeführt
- [ ] SettingsRepository + ViewModel erstellt
- [ ] SettingsScreen UI fertig
- [ ] Settings Persistence mit DataStore getestet
- [ ] Build ohne Fehler
- [ ] Navigation aktualisiert (VpnScreen + SettingsScreen)

---

## 🧪 Test Cases

### VPN Config Test
```
1. App starten → VpnScreen
2. "Aktualisieren" Knopf drücken
3. Config sollte geladen werden
4. Toggle zum Verbinden drücken
5. VPN sollte sich verbinden
6. Status sollte "Verbunden" zeigen
7. Toggle zum Trennen drücken
8. Status sollte "Getrennt" zeigen
```

### Settings Test
```
1. App starten → SettingsScreen
2. Auto-Sync Toggle Ändern
3. Setting sollte gespeichert sein
4. App neustarten
5. Setting sollte noch aktiviert sein
6. "Auf Standard zurücksetzen" testen
7. Settings sollten zurückgesetzt sein
```

---

## 📞 Bei Fragen/Problemen

- Backend Endpoint Struktur im Team abklären
- WireGuard Config Format standardisieren
- DataStore Schema mit Kotlin Preferences vereinbaren

