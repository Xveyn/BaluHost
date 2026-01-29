package com.baluhost.android.presentation.ui.screens.vpn

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.domain.network.NetworkStateManager
import com.baluhost.android.domain.usecase.vpn.ConnectVpnUseCase
import com.baluhost.android.domain.usecase.vpn.DisconnectVpnUseCase
import com.baluhost.android.domain.usecase.vpn.FetchVpnConfigUseCase
import com.baluhost.android.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for VPN Screen.
 *
 * Manages VPN connection state and configuration.
 * Uses NetworkStateManager for VPN status checking without Android Context dependency.
 */
@HiltViewModel
class VpnViewModel @Inject constructor(
    private val fetchVpnConfigUseCase: FetchVpnConfigUseCase,
    private val connectVpnUseCase: ConnectVpnUseCase,
    private val disconnectVpnUseCase: DisconnectVpnUseCase,
    private val preferencesManager: PreferencesManager,
    private val networkStateManager: NetworkStateManager
) : ViewModel() {
    
    private val _uiState = MutableStateFlow(VpnUiState())
    val uiState: StateFlow<VpnUiState> = _uiState.asStateFlow()
    
    init {
        loadVpnConfig()
        checkVpnStatus()
        startVpnStatusMonitoring()
    }
    
    /**
     * Load VPN configuration from backend or cache.
     */
    private fun loadVpnConfig() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true)
            
            Log.d(TAG, "Loading VPN config")
            val result = fetchVpnConfigUseCase()
            
            when (result) {
                is Result.Success -> {
                    val config = result.data
                    Log.d(TAG, "VPN config loaded: ${config.deviceName}")
                    
                    // Extract endpoint from config
                    var endpoint: String? = null
                    try {
                        val lines = config.configString.lines()
                        for (line in lines) {
                            if (line.trim().startsWith("Endpoint")) {
                                endpoint = line.substringAfter("=").trim()
                                break
                            }
                        }
                    } catch (e: Exception) {
                        Log.e(TAG, "Failed to parse endpoint", e)
                    }
                    
                    _uiState.value = _uiState.value.copy(
                        hasConfig = true,
                        serverEndpoint = endpoint ?: config.assignedIp,
                        clientIp = config.assignedIp,
                        deviceName = config.deviceName,
                        isLoading = false,
                        error = null
                    )
                }
                is Result.Error -> {
                    Log.e(TAG, "Failed to load VPN config", result.exception)
                    
                    // Try to load from local cache
                    checkVpnConfig()
                    
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        error = "Konfiguration konnte nicht geladen werden: ${result.exception.message}"
                    )
                }
                is Result.Loading -> {
                    // Already loading
                }
            }
        }
    }
    
    /**
     * Check cached VPN config.
     */
    private suspend fun checkVpnConfig() {
        val configString = preferencesManager.getVpnConfig().first()
        val hasConfig = !configString.isNullOrEmpty()
        
        if (hasConfig) {
            Log.d(TAG, "Found cached VPN config")
            
            // Extract endpoint from config if available
            var endpoint: String? = null
            if (configString != null) {
                try {
                    val lines = configString.lines()
                    for (line in lines) {
                        if (line.trim().startsWith("Endpoint")) {
                            endpoint = line.substringAfter("=").trim()
                            break
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to parse endpoint", e)
                }
            }
            
            val assignedIp = preferencesManager.getVpnAssignedIp().first()
            val deviceName = preferencesManager.getVpnDeviceName().first()
            
            _uiState.value = _uiState.value.copy(
                hasConfig = true,
                serverEndpoint = endpoint ?: assignedIp,
                clientIp = assignedIp,
                deviceName = deviceName ?: "Unbekanntes Gerät",
                error = null
            )
        }
    }
    
    /**
     * Check current VPN status.
     */
    private fun checkVpnStatus() {
        val isVpnActive = networkStateManager.isVpnActive()
        _uiState.value = _uiState.value.copy(isConnected = isVpnActive)
        Log.d(TAG, "VPN status check: isConnected=$isVpnActive")
    }

    /**
     * Start monitoring VPN status using reactive Flow.
     */
    private fun startVpnStatusMonitoring() {
        viewModelScope.launch {
            networkStateManager.observeVpnStatus().collect { isVpnActive ->
                val currentState = _uiState.value.isConnected

                if (isVpnActive != currentState) {
                    Log.d(TAG, "VPN status changed: $currentState -> $isVpnActive")
                    _uiState.value = _uiState.value.copy(isConnected = isVpnActive)
                }
            }
        }
    }
    
    /**
     * Refresh VPN configuration from backend.
     */
    fun refreshConfig() {
        loadVpnConfig()
    }
    
    /**
     * Connect to VPN.
     */
    fun connect() {
        if (_uiState.value.isConnected || _uiState.value.isLoading) return
        if (!_uiState.value.hasConfig) {
            _uiState.value = _uiState.value.copy(
                error = "VPN-Konfiguration nicht verfügbar"
            )
            return
        }
        
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            
            Log.d(TAG, "Initiating VPN connection")
            val result = connectVpnUseCase()
            
            when (result) {
                is Result.Success -> {
                    Log.d(TAG, "VPN connection initiated successfully")
                    // Give service time to establish connection
                    delay(2000)

                    // Check actual VPN status after delay
                    val isVpnActive = networkStateManager.isVpnActive()
                    Log.d(TAG, "VPN active after connect: $isVpnActive")

                    _uiState.value = _uiState.value.copy(
                        isConnected = isVpnActive,
                        isLoading = false,
                        error = if (!isVpnActive) "VPN konnte nicht gestartet werden" else null
                    )
                }
                is Result.Error -> {
                    Log.e(TAG, "VPN connection failed", result.exception)
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        isConnected = false,
                        error = "Verbindung fehlgeschlagen: ${result.exception.message}"
                    )
                }
                is Result.Loading -> {
                    // Connection loading
                }
            }
        }
    }
    
    /**
     * Disconnect from VPN.
     */
    fun disconnect() {
        if (!_uiState.value.isConnected || _uiState.value.isLoading) return
        
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            
            Log.d(TAG, "Disconnecting VPN")
            val result = disconnectVpnUseCase()
            
            when (result) {
                is Result.Success -> {
                    Log.d(TAG, "VPN disconnected successfully")
                    _uiState.value = _uiState.value.copy(
                        isConnected = false,
                        isLoading = false
                    )
                }
                is Result.Error -> {
                    Log.e(TAG, "VPN disconnect failed", result.exception)
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        error = result.exception.message
                    )
                }
                is Result.Loading -> {
                    // Disconnection loading
                }
            }
        }
    }
    
    companion object {
        private const val TAG = "VpnViewModel"
    }
}

data class VpnUiState(
    val isConnected: Boolean = false,
    val isLoading: Boolean = false,
    val hasConfig: Boolean = false,
    val serverEndpoint: String? = null,
    val clientIp: String? = null,
    val deviceName: String? = null,
    val error: String? = null
)
