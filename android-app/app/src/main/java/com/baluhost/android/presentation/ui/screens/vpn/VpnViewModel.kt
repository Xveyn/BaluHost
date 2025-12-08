package com.baluhost.android.presentation.ui.screens.vpn

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.domain.usecase.vpn.ConnectVpnUseCase
import com.baluhost.android.domain.usecase.vpn.DisconnectVpnUseCase
import com.baluhost.android.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
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
    private val preferencesManager: PreferencesManager
) : ViewModel() {
    
    private val _uiState = MutableStateFlow(VpnUiState())
    val uiState: StateFlow<VpnUiState> = _uiState.asStateFlow()
    
    init {
        checkVpnConfig()
    }
    
    private fun checkVpnConfig() {
        viewModelScope.launch {
            val hasConfig = preferencesManager.getVpnConfig().first() != null
            _uiState.value = _uiState.value.copy(
                hasConfig = hasConfig,
                error = if (!hasConfig) "No VPN configuration found" else null
            )
        }
    }
    
    fun connect() {
        if (_uiState.value.isConnected || _uiState.value.isLoading) return
        
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            
            val result = connectVpnUseCase()
            
            when (result) {
                is Result.Success -> {
                    _uiState.value = _uiState.value.copy(
                        isConnected = true,
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
