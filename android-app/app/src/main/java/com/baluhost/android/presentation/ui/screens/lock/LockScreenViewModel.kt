package com.baluhost.android.presentation.ui.screens.lock

import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baluhost.android.data.local.security.AppLockManager
import com.baluhost.android.data.local.security.BiometricAuthManager
import com.baluhost.android.data.local.security.PinManager
import com.baluhost.android.data.local.security.SecurePreferencesManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for Lock Screen.
 */
@HiltViewModel
class LockScreenViewModel @Inject constructor(
    private val biometricAuthManager: BiometricAuthManager,
    private val pinManager: PinManager,
    private val appLockManager: AppLockManager,
    private val securePreferences: SecurePreferencesManager
) : ViewModel() {
    
    private val _uiState = MutableStateFlow(LockScreenUiState())
    val uiState: StateFlow<LockScreenUiState> = _uiState.asStateFlow()
    
    init {
        checkAuthenticationMethods()
    }
    
    /**
     * Check what authentication methods are available.
     */
    private fun checkAuthenticationMethods() {
        val biometricStatus = biometricAuthManager.checkBiometricAvailability(allowDeviceCredential = false)
        val isBiometricEnabled = securePreferences.isBiometricEnabled()
        val biometricAvailable = biometricStatus == BiometricAuthManager.BiometricStatus.AVAILABLE &&
                                isBiometricEnabled
        
        val pinAvailable = pinManager.isPinConfigured()
        
        android.util.Log.d("LockScreenViewModel", "Biometric status: $biometricStatus")
        android.util.Log.d("LockScreenViewModel", "Biometric enabled in settings: $isBiometricEnabled")
        android.util.Log.d("LockScreenViewModel", "Biometric available: $biometricAvailable")
        android.util.Log.d("LockScreenViewModel", "PIN available: $pinAvailable")
        
        _uiState.update { currentState ->
            currentState.copy(
                biometricAvailable = biometricAvailable,
                pinAvailable = pinAvailable
            )
        }
    }
    
    /**
     * Authenticate using biometric.
     */
    fun authenticateBiometric(activity: FragmentActivity) {
        _uiState.update { it.copy(isAuthenticating = true, error = null) }
        
        biometricAuthManager.authenticate(
            activity = activity,
            title = "BaluHost entsperren",
            subtitle = "Verwenden Sie Ihren Fingerabdruck oder Ihr Gesicht",
            allowDeviceCredential = false,
            onSuccess = {
                viewModelScope.launch {
                    // Reset lock timer
                    appLockManager.onAppForeground()
                    
                    // Mark as unlocked
                    _uiState.update { it.copy(
                        isAuthenticating = false,
                        isUnlocked = true,
                        error = null
                    ) }
                }
            },
            onError = { errorCode, errorMessage ->
                _uiState.update { it.copy(
                    isAuthenticating = false,
                    error = errorMessage
                ) }
            },
            onFailed = {
                _uiState.update { it.copy(
                    isAuthenticating = false,
                    error = "Biometrische Daten nicht erkannt. Bitte versuchen Sie es erneut."
                ) }
            }
        )
    }
    
    /**
     * Authenticate using PIN.
     * 
     * @return true if PIN is correct, false otherwise
     */
    fun authenticatePin(pin: String): Boolean {
        val isValid = pinManager.verifyPin(pin)
        
        if (isValid) {
            viewModelScope.launch {
                // Reset lock timer
                appLockManager.onAppForeground()
                
                // Mark as unlocked
                _uiState.update { it.copy(
                    isUnlocked = true,
                    error = null
                ) }
            }
        }
        
        return isValid
    }
    
    fun dismissError() {
        _uiState.update { it.copy(error = null) }
    }
}

/**
 * UI state for Lock Screen.
 */
data class LockScreenUiState(
    val biometricAvailable: Boolean = false,
    val pinAvailable: Boolean = false,
    val isAuthenticating: Boolean = false,
    val isUnlocked: Boolean = false,
    val error: String? = null
)
