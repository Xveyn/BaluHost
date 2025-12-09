package com.baluhost.android.presentation.ui.screens.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.data.local.security.AppLockManager
import com.baluhost.android.data.local.security.BiometricAuthManager
import com.baluhost.android.data.local.security.PinManager
import com.baluhost.android.data.local.security.SecurePreferencesManager
import com.baluhost.android.domain.repository.DeviceRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for Settings screen.
 */
@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val deviceRepository: DeviceRepository,
    private val preferencesManager: PreferencesManager,
    private val securePreferences: SecurePreferencesManager,
    private val biometricAuthManager: BiometricAuthManager,
    private val pinManager: PinManager,
    private val appLockManager: AppLockManager
) : ViewModel() {
    
    private val _uiState = MutableStateFlow(SettingsUiState())
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()
    
    init {
        loadUserInfo()
        loadSecuritySettings()
    }
    
    private fun loadUserInfo() {
        viewModelScope.launch {
            val username = preferencesManager.getUsername().first()
            val serverUrl = preferencesManager.getServerUrl().first()
            val deviceId = preferencesManager.getDeviceId().first()
            
            _uiState.update { currentState ->
                currentState.copy(
                    username = username ?: "Unknown",
                    serverUrl = serverUrl ?: "Not connected",
                    deviceId = deviceId
                )
            }
        }
    }
    
    private fun loadSecuritySettings() {
        viewModelScope.launch {
            val biometricStatus = biometricAuthManager.checkBiometricAvailability(allowDeviceCredential = false)
            val biometricAvailable = biometricStatus == BiometricAuthManager.BiometricStatus.AVAILABLE
            val biometricEnabled = securePreferences.isBiometricEnabled()
            val pinConfigured = pinManager.isPinConfigured()
            val appLockEnabled = securePreferences.isAppLockEnabled()
            val lockTimeout = appLockManager.getLockTimeoutMillis()
            
            _uiState.update { currentState ->
                currentState.copy(
                    biometricAvailable = biometricAvailable,
                    biometricEnabled = biometricEnabled,
                    pinConfigured = pinConfigured,
                    appLockEnabled = appLockEnabled,
                    lockTimeoutMinutes = (lockTimeout / 60_000).toInt()
                )
            }
        }
    }
    
    fun toggleBiometric(enabled: Boolean) {
        viewModelScope.launch {
            securePreferences.setBiometricEnabled(enabled)
            _uiState.update { it.copy(biometricEnabled = enabled) }
        }
    }
    
    fun toggleAppLock(enabled: Boolean) {
        viewModelScope.launch {
            securePreferences.setAppLockEnabled(enabled)
            _uiState.update { it.copy(appLockEnabled = enabled) }
        }
    }
    
    fun setLockTimeout(minutes: Int) {
        viewModelScope.launch {
            appLockManager.setLockTimeoutMillis(minutes * 60_000L)
            _uiState.update { it.copy(lockTimeoutMinutes = minutes) }
        }
    }
    
    fun setupPin(pin: String, onSuccess: () -> Unit, onError: (String) -> Unit) {
        viewModelScope.launch {
            try {
                pinManager.setupPin(pin)
                _uiState.update { it.copy(pinConfigured = true) }
                onSuccess()
            } catch (e: Exception) {
                onError(e.message ?: "Failed to setup PIN")
            }
        }
    }
    
    fun removePin() {
        viewModelScope.launch {
            pinManager.removePin()
            _uiState.update { it.copy(pinConfigured = false) }
        }
    }
    
    /**
     * Delete the current device from the server and clear local data.
     */
    fun deleteDevice() {
        val deviceId = _uiState.value.deviceId
        if (deviceId == null) {
            _uiState.update { it.copy(error = "Device ID not found") }
            return
        }
        
        viewModelScope.launch {
            _uiState.update { it.copy(isDeleting = true, error = null) }
            
            try {
                // Delete device from server
                deviceRepository.deleteDevice(deviceId)
                
                // Clear all local data (including tokens, server URL, etc.)
                preferencesManager.clearAll()
                
                // Reset onboarding status so user goes back to onboarding
                preferencesManager.saveOnboardingCompleted(false)
                
                // Notify success - navigation will be handled by UI
                _uiState.update { it.copy(
                    isDeleting = false,
                    deviceDeleted = true
                ) }
            } catch (e: Exception) {
                _uiState.update { it.copy(
                    isDeleting = false,
                    error = "Failed to remove device: ${e.message}"
                ) }
            }
        }
    }
    
    fun dismissError() {
        _uiState.update { it.copy(error = null) }
    }
}

/**
 * UI state for Settings screen.
 */
data class SettingsUiState(
    val username: String = "",
    val serverUrl: String = "",
    val deviceId: String? = null,
    val isDeleting: Boolean = false,
    val deviceDeleted: Boolean = false,
    val error: String? = null,
    // Security settings
    val biometricAvailable: Boolean = false,
    val biometricEnabled: Boolean = false,
    val pinConfigured: Boolean = false,
    val appLockEnabled: Boolean = false,
    val lockTimeoutMinutes: Int = 5
)
