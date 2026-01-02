package com.baluhost.android.data.local.security

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Secure storage manager using EncryptedSharedPreferences.
 * 
 * Stores sensitive data like JWT tokens, refresh tokens, and PIN codes
 * with AES256-GCM encryption backed by Android Keystore.
 * 
 * Best Practices:
 * - Uses MasterKey with AES256_GCM_SPEC for maximum security
 * - Encrypted both keys and values
 * - Fallback to regular SharedPreferences only if encryption fails (logged)
 * - Singleton to ensure single instance across app
 */
@Singleton
class SecurePreferencesManager @Inject constructor(
    @ApplicationContext private val context: Context
) {
    
    companion object {
        private const val TAG = "SecurePreferences"
        private const val ENCRYPTED_PREFS_FILE = "baluhost_secure_prefs"
        
        // Keys for secure storage
        private const val KEY_ACCESS_TOKEN = "access_token"
        private const val KEY_REFRESH_TOKEN = "refresh_token"
        private const val KEY_PIN_HASH = "pin_hash"
        private const val KEY_PIN_SALT = "pin_salt"
        private const val KEY_BIOMETRIC_ENABLED = "biometric_enabled"
        private const val KEY_APP_LOCK_ENABLED = "app_lock_enabled"
    }
    
    private val sharedPreferences: SharedPreferences by lazy {
        try {
            // Create or retrieve the master key for encryption
            val masterKey = MasterKey.Builder(context)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
            
            // Create encrypted shared preferences
            EncryptedSharedPreferences.create(
                context,
                ENCRYPTED_PREFS_FILE,
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )
        } catch (e: Exception) {
            // Fallback to regular SharedPreferences if encryption setup fails
            // This should be logged and monitored in production
            android.util.Log.e(TAG, "Failed to create EncryptedSharedPreferences, falling back to regular", e)
            context.getSharedPreferences("baluhost_prefs_fallback", Context.MODE_PRIVATE)
        }
    }
    
    // ========== Access Token ==========
    
    /**
     * Save JWT access token securely.
     */
    fun saveAccessToken(token: String) {
        sharedPreferences.edit()
            .putString(KEY_ACCESS_TOKEN, token)
            .apply()
    }
    
    /**
     * Retrieve JWT access token.
     * @return Access token or null if not found
     */
    fun getAccessToken(): String? {
        return sharedPreferences.getString(KEY_ACCESS_TOKEN, null)
    }
    
    // ========== Refresh Token ==========
    
    /**
     * Save JWT refresh token securely.
     */
    fun saveRefreshToken(token: String) {
        sharedPreferences.edit()
            .putString(KEY_REFRESH_TOKEN, token)
            .apply()
    }
    
    /**
     * Retrieve JWT refresh token.
     * @return Refresh token or null if not found
     */
    fun getRefreshToken(): String? {
        return sharedPreferences.getString(KEY_REFRESH_TOKEN, null)
    }
    
    // ========== PIN Management ==========
    
    /**
     * Save PIN hash and salt securely.
     * PIN is never stored in plain text - only the hash.
     * 
     * @param pinHash SHA-256 hash of the PIN
     * @param salt Random salt used for hashing
     */
    fun savePinHash(pinHash: String, salt: String) {
        sharedPreferences.edit()
            .putString(KEY_PIN_HASH, pinHash)
            .putString(KEY_PIN_SALT, salt)
            .apply()
    }
    
    /**
     * Get stored PIN hash for validation.
     * @return PIN hash or null if not set
     */
    fun getPinHash(): String? {
        return sharedPreferences.getString(KEY_PIN_HASH, null)
    }
    
    /**
     * Get salt used for PIN hashing.
     * @return Salt or null if not set
     */
    fun getPinSalt(): String? {
        return sharedPreferences.getString(KEY_PIN_SALT, null)
    }
    
    /**
     * Check if PIN is configured.
     */
    fun hasPinConfigured(): Boolean {
        return getPinHash() != null && getPinSalt() != null
    }
    
    /**
     * Remove PIN configuration.
     */
    fun clearPin() {
        sharedPreferences.edit()
            .remove(KEY_PIN_HASH)
            .remove(KEY_PIN_SALT)
            .apply()
    }
    
    // ========== Biometric Settings ==========
    
    /**
     * Enable or disable biometric authentication.
     */
    fun setBiometricEnabled(enabled: Boolean) {
        sharedPreferences.edit()
            .putBoolean(KEY_BIOMETRIC_ENABLED, enabled)
            .apply()
    }
    
    /**
     * Check if biometric authentication is enabled.
     */
    fun isBiometricEnabled(): Boolean {
        return sharedPreferences.getBoolean(KEY_BIOMETRIC_ENABLED, false)
    }
    
    // ========== App Lock Settings ==========
    
    /**
     * Enable or disable app lock feature.
     */
    fun setAppLockEnabled(enabled: Boolean) {
        sharedPreferences.edit()
            .putBoolean(KEY_APP_LOCK_ENABLED, enabled)
            .apply()
    }
    
    /**
     * Check if app lock is enabled.
     */
    fun isAppLockEnabled(): Boolean {
        return sharedPreferences.getBoolean(KEY_APP_LOCK_ENABLED, false)
    }
    
    // ========== Clear Operations ==========
    
    /**
     * Clear only authentication tokens (on logout).
     * Preserves PIN and biometric settings.
     */
    fun clearTokens() {
        sharedPreferences.edit()
            .remove(KEY_ACCESS_TOKEN)
            .remove(KEY_REFRESH_TOKEN)
            .apply()
    }
    
    /**
     * Clear all secure data including tokens, PIN, and settings.
     * Use this on complete logout or device removal.
     */
    fun clearAll() {
        sharedPreferences.edit().clear().apply()
    }

    // ========== Adapter Credentials ==========

    /**
     * Save adapter credentials for a specific adapter key (e.g., folderId or accountId).
     */
    fun saveAdapterCredentials(adapterKey: String, username: String?, password: String?) {
        val userKey = "adapter_${adapterKey}_user"
        val passKey = "adapter_${adapterKey}_pass"
        val editor = sharedPreferences.edit()
        if (username != null) editor.putString(userKey, username) else editor.remove(userKey)
        if (password != null) editor.putString(passKey, password) else editor.remove(passKey)
        editor.apply()
    }

    /**
     * Retrieve adapter credentials for a key.
     */
    fun getAdapterCredentials(adapterKey: String): Pair<String?, String?> {
        val userKey = "adapter_${adapterKey}_user"
        val passKey = "adapter_${adapterKey}_pass"
        return Pair(sharedPreferences.getString(userKey, null), sharedPreferences.getString(passKey, null))
    }

    /**
     * Remove stored adapter credentials for a key.
     */
    fun removeAdapterCredentials(adapterKey: String) {
        sharedPreferences.edit()
            .remove("adapter_${adapterKey}_user")
            .remove("adapter_${adapterKey}_pass")
            .apply()
    }
}
