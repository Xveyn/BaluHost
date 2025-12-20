package com.baluhost.android.presentation.ui.screens.vpn

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.domain.usecase.vpn.ConnectVpnUseCase
import com.baluhost.android.domain.usecase.vpn.DisconnectVpnUseCase
import com.baluhost.android.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for VPN Screen.
 * 
 * Manages VPN connection state.
 */
@HiltViewModel
class VpnViewModel @Inject constructor(
    private val connectVpnUseCase: ConnectVpnUseCase,
    private val disconnectVpnUseCase: DisconnectVpnUseCase,
    private val preferencesManager: PreferencesManager,
    @ApplicationContext private val context: Context
) : ViewModel() {
    
    private val _uiState = MutableStateFlow(VpnUiState())
    val uiState: StateFlow<VpnUiState> = _uiState.asStateFlow()
    
    init {
        checkVpnConfig()
        checkVpnStatus()
        startVpnStatusMonitoring()
    }
    
    private fun checkVpnConfig() {
        viewModelScope.launch {
            val configString = preferencesManager.getVpnConfig().first()
            val hasConfig = !configString.isNullOrEmpty()
            
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
                    android.util.Log.e("VpnViewModel", "Failed to parse endpoint", e)
                }
            }
            
            _uiState.value = _uiState.value.copy(
                hasConfig = hasConfig,
                serverEndpoint = endpoint,
                error = if (!hasConfig) "Keine VPN-Konfiguration gefunden" else null
            )
        }
    }
    
    private fun checkVpnStatus() {
        viewModelScope.launch {
            val isVpnActive = isVpnActive()
            _uiState.value = _uiState.value.copy(isConnected = isVpnActive)
            android.util.Log.d("VpnViewModel", "VPN status check: isConnected=$isVpnActive")
        }
    }
    
    private fun startVpnStatusMonitoring() {
        viewModelScope.launch {
            while (isActive) {
                val isVpnActive = isVpnActive()
                val currentState = _uiState.value.isConnected
                
                if (isVpnActive != currentState) {
                    android.util.Log.d("VpnViewModel", "VPN status changed: $currentState -> $isVpnActive")
                    _uiState.value = _uiState.value.copy(isConnected = isVpnActive)
                }
                
                delay(3000) // Check every 3 seconds
            }
        }
    }
    
    private fun isVpnActive(): Boolean {
        return try {
            val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            val activeNetwork = connectivityManager.activeNetwork ?: return false
            val networkCapabilities = connectivityManager.getNetworkCapabilities(activeNetwork) ?: return false
            
            // Check if the active network is a VPN
            networkCapabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN)
        } catch (e: Exception) {
            android.util.Log.e("VpnViewModel", "Error checking VPN status", e)
            false
        }
    }
    
    fun connect() {
        if (_uiState.value.isConnected || _uiState.value.isLoading) return
        
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            
            android.util.Log.d("VpnViewModel", "Initiating VPN connection")
            val result = connectVpnUseCase()
            
            when (result) {
                is Result.Success -> {
                    android.util.Log.d("VpnViewModel", "VPN connection initiated successfully")
                    // Give service time to establish connection
                    kotlinx.coroutines.delay(2000)
                    
                    // Check actual VPN status after delay
                    val isVpnActive = isVpnActive()
                    android.util.Log.d("VpnViewModel", "VPN active after connect: $isVpnActive")
                    
                    _uiState.value = _uiState.value.copy(
                        isConnected = isVpnActive,
                        isLoading = false,
                        error = if (!isVpnActive) "VPN konnte nicht gestartet werden" else null
                    )
                }
                is Result.Error -> {
                    android.util.Log.e("VpnViewModel", "VPN connection failed", result.exception)
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        isConnected = false,
                        error = "Verbindung fehlgeschlagen: ${result.exception.message}"
                    )
                }
                else -> {
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        isConnected = false,
                        error = "Unbekannter Fehler"
                    )
                }
            }
        }
    }
    
    fun disconnect() {
        if (!_uiState.value.isConnected || _uiState.value.isLoading) return
        
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            
            val result = disconnectVpnUseCase()
            
            when (result) {
                is Result.Success -> {
                    _uiState.value = _uiState.value.copy(
                        isConnected = false,
                        isLoading = false
                    )
                }
                is Result.Error -> {
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        error = result.exception.message
                    )
                }
                else -> {
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        error = "Unknown error"
                    )
                }
            }
        }
    }
}

data class VpnUiState(
    val isConnected: Boolean = false,
    val isLoading: Boolean = false,
    val hasConfig: Boolean = false,
    val serverEndpoint: String? = null,
    val error: String? = null
)
