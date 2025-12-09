package com.baluhost.android.data.local.security

import android.content.Context
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.*
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manager for biometric authentication operations.
 * 
 * Handles biometric availability checks and authentication prompts
 * following Android biometric best practices.
 * 
 * Best Practices:
 * - Checks biometric capability before prompting
 * - Supports both biometric and device credential (PIN/Pattern) authentication
 * - Provides clear error messages for different failure scenarios
 * - Uses crypto-backed authentication for maximum security
 */
@Singleton
class BiometricAuthManager @Inject constructor(
    @ApplicationContext private val context: Context
) {
    
    companion object {
        private const val TAG = "BiometricAuth"
    }
    
    private val biometricManager = BiometricManager.from(context)
    
    /**
     * Biometric availability status.
     */
    enum class BiometricStatus {
        AVAILABLE,              // Biometric can be used
        NO_HARDWARE,           // Device doesn't have biometric hardware
        HARDWARE_UNAVAILABLE,  // Hardware temporarily unavailable
        NO_BIOMETRICS,         // No biometric enrolled
        NO_DEVICE_CREDENTIAL,  // No PIN/Pattern/Password set
        UNSUPPORTED           // API level < 23
    }
    
    /**
     * Check if biometric authentication can be used.
     * 
     * @param allowDeviceCredential Allow PIN/Pattern as fallback
     * @return BiometricStatus indicating availability
     */
    fun checkBiometricAvailability(allowDeviceCredential: Boolean = true): BiometricStatus {
        val authenticators = if (allowDeviceCredential) {
            BIOMETRIC_STRONG or DEVICE_CREDENTIAL
        } else {
            BIOMETRIC_STRONG
        }
        
        return when (biometricManager.canAuthenticate(authenticators)) {
            BiometricManager.BIOMETRIC_SUCCESS ->
                BiometricStatus.AVAILABLE
            
            BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE ->
                BiometricStatus.NO_HARDWARE
            
            BiometricManager.BIOMETRIC_ERROR_HW_UNAVAILABLE ->
                BiometricStatus.HARDWARE_UNAVAILABLE
            
            BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED ->
                BiometricStatus.NO_BIOMETRICS
            
            BiometricManager.BIOMETRIC_ERROR_SECURITY_UPDATE_REQUIRED,
            BiometricManager.BIOMETRIC_ERROR_UNSUPPORTED,
            BiometricManager.BIOMETRIC_STATUS_UNKNOWN ->
                BiometricStatus.UNSUPPORTED
            
            else -> BiometricStatus.UNSUPPORTED
        }
    }
    
    /**
     * Check if device has strong biometric hardware (fingerprint, face, iris).
     */
    fun hasBiometricHardware(): Boolean {
        return biometricManager.canAuthenticate(BIOMETRIC_STRONG) != BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE
    }
    
    /**
     * Check if biometric is enrolled and ready to use.
     */
    fun isBiometricEnrolled(): Boolean {
        return biometricManager.canAuthenticate(BIOMETRIC_STRONG) == BiometricManager.BIOMETRIC_SUCCESS
    }
    
    /**
     * Show biometric authentication prompt.
     * 
     * @param activity Activity context for showing prompt
     * @param title Prompt title
     * @param subtitle Prompt subtitle (optional)
     * @param description Prompt description (optional)
     * @param negativeButtonText Text for cancel button
     * @param allowDeviceCredential Allow PIN/Pattern as fallback
     * @param onSuccess Callback when authentication succeeds
     * @param onError Callback when authentication fails with error code and message
     * @param onFailed Callback when biometric doesn't match (user can retry)
     */
    fun authenticate(
        activity: FragmentActivity,
        title: String = "Authentifizierung erforderlich",
        subtitle: String? = "Entsperren Sie BaluHost",
        description: String? = "Verwenden Sie Ihren Fingerabdruck oder Ihr Gesicht",
        negativeButtonText: String = "Abbrechen",
        allowDeviceCredential: Boolean = true,
        onSuccess: () -> Unit,
        onError: (errorCode: Int, errorMessage: String) -> Unit,
        onFailed: () -> Unit = {}
    ) {
        // Check availability first
        val status = checkBiometricAvailability(allowDeviceCredential)
        if (status != BiometricStatus.AVAILABLE) {
            onError(-1, getStatusMessage(status))
            return
        }
        
        // Create prompt info
        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle(title)
            .apply {
                subtitle?.let { setSubtitle(it) }
                description?.let { setDescription(it) }
            }
            .apply {
                if (allowDeviceCredential) {
                    setAllowedAuthenticators(BIOMETRIC_STRONG or DEVICE_CREDENTIAL)
                } else {
                    setAllowedAuthenticators(BIOMETRIC_STRONG)
                    setNegativeButtonText(negativeButtonText)
                }
            }
            .build()
        
        // Create callback
        val callback = object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                super.onAuthenticationSucceeded(result)
                android.util.Log.d(TAG, "Authentication succeeded")
                onSuccess()
            }
            
            override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                super.onAuthenticationError(errorCode, errString)
                android.util.Log.e(TAG, "Authentication error: $errorCode - $errString")
                onError(errorCode, errString.toString())
            }
            
            override fun onAuthenticationFailed() {
                super.onAuthenticationFailed()
                android.util.Log.w(TAG, "Authentication failed - biometric not recognized")
                onFailed()
            }
        }
        
        // Show prompt
        val executor = ContextCompat.getMainExecutor(activity)
        val biometricPrompt = BiometricPrompt(activity, executor, callback)
        biometricPrompt.authenticate(promptInfo)
    }
    
    /**
     * Get user-friendly message for biometric status.
     */
    fun getStatusMessage(status: BiometricStatus): String {
        return when (status) {
            BiometricStatus.AVAILABLE ->
                "Biometrische Authentifizierung verfügbar"
            
            BiometricStatus.NO_HARDWARE ->
                "Dieses Gerät hat keine biometrische Hardware"
            
            BiometricStatus.HARDWARE_UNAVAILABLE ->
                "Biometrische Hardware ist momentan nicht verfügbar"
            
            BiometricStatus.NO_BIOMETRICS ->
                "Keine biometrischen Daten registriert. Bitte fügen Sie einen Fingerabdruck oder ein Gesicht in den Systemeinstellungen hinzu."
            
            BiometricStatus.NO_DEVICE_CREDENTIAL ->
                "Keine Geräte-PIN oder -Muster festgelegt"
            
            BiometricStatus.UNSUPPORTED ->
                "Biometrische Authentifizierung wird auf diesem Gerät nicht unterstützt"
        }
    }
}
