package com.baluhost.android.data.local.security

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manager for app lock functionality and auto-lock timeout.
 * 
 * Handles:
 * - Tracking when app goes to background
 * - Determining if lock screen should be shown on resume
 * - Auto-lock timeout (default 5 minutes)
 * 
 * Best Practices:
 * - Uses DataStore for timestamp storage (not sensitive)
 * - Configurable timeout duration
 * - Respects app lock enabled/disabled state
 */
@Singleton
class AppLockManager @Inject constructor(
    @ApplicationContext private val context: Context,
    private val dataStore: DataStore<Preferences>,
    private val securePreferences: SecurePreferencesManager
) {
    
    companion object {
        private const val TAG = "AppLockManager"
        
        // Default auto-lock timeout: 5 minutes
        const val DEFAULT_TIMEOUT_MILLIS = 5 * 60 * 1000L
        
        // Keys
        private val KEY_LAST_BACKGROUND_TIME = longPreferencesKey("last_background_time")
        private val KEY_LOCK_TIMEOUT_MILLIS = longPreferencesKey("lock_timeout_millis")
    }
    
    /**
     * Record the timestamp when app goes to background.
     */
    suspend fun onAppBackground() {
        if (!isAppLockEnabled()) {
            return
        }
        
        val currentTime = System.currentTimeMillis()
        dataStore.edit { prefs ->
            prefs[KEY_LAST_BACKGROUND_TIME] = currentTime
        }
        android.util.Log.d(TAG, "App went to background at $currentTime")
    }
    
    /**
     * Check if lock screen should be shown when app resumes.
     * 
     * @return true if app was in background longer than timeout duration
     */
    suspend fun shouldShowLockScreen(): Boolean {
        // Check if app lock is enabled
        if (!isAppLockEnabled()) {
            android.util.Log.d(TAG, "App lock is disabled")
            return false
        }
        
        // Check if authentication method is configured
        if (!securePreferences.isBiometricEnabled() && !securePreferences.hasPinConfigured()) {
            android.util.Log.d(TAG, "No authentication method configured")
            return false
        }
        
        // Get last background time
        val lastBackgroundTime = dataStore.data.map { prefs ->
            prefs[KEY_LAST_BACKGROUND_TIME] ?: 0L
        }.first()
        
        if (lastBackgroundTime == 0L) {
            // First app launch or no background event recorded
            android.util.Log.d(TAG, "No previous background time recorded")
            return false
        }
        
        // Calculate elapsed time
        val currentTime = System.currentTimeMillis()
        val elapsedTime = currentTime - lastBackgroundTime
        
        // Get timeout duration
        val timeoutDuration = getLockTimeoutMillis()
        
        val shouldLock = elapsedTime >= timeoutDuration
        android.util.Log.d(TAG, "Elapsed: ${elapsedTime}ms, Timeout: ${timeoutDuration}ms, Should lock: $shouldLock")
        
        return shouldLock
    }
    
    /**
     * Reset lock timer (call after successful authentication).
     */
    suspend fun onAppForeground() {
        dataStore.edit { prefs ->
            prefs.remove(KEY_LAST_BACKGROUND_TIME)
        }
        android.util.Log.d(TAG, "App came to foreground, lock timer reset")
    }
    
    /**
     * Get lock timeout duration in milliseconds.
     */
    suspend fun getLockTimeoutMillis(): Long {
        return dataStore.data.map { prefs ->
            prefs[KEY_LOCK_TIMEOUT_MILLIS] ?: DEFAULT_TIMEOUT_MILLIS
        }.first()
    }
    
    /**
     * Set lock timeout duration.
     * 
     * @param timeoutMillis Timeout in milliseconds (minimum 30 seconds)
     */
    suspend fun setLockTimeoutMillis(timeoutMillis: Long) {
        require(timeoutMillis >= 30_000L) { "Timeout must be at least 30 seconds" }
        
        dataStore.edit { prefs ->
            prefs[KEY_LOCK_TIMEOUT_MILLIS] = timeoutMillis
        }
        android.util.Log.d(TAG, "Lock timeout set to ${timeoutMillis}ms")
    }
    
    /**
     * Get lock timeout as Flow for UI observation.
     */
    fun getLockTimeoutFlow(): Flow<Long> {
        return dataStore.data.map { prefs ->
            prefs[KEY_LOCK_TIMEOUT_MILLIS] ?: DEFAULT_TIMEOUT_MILLIS
        }
    }
    
    /**
     * Check if app lock feature is enabled.
     */
    private fun isAppLockEnabled(): Boolean {
        return securePreferences.isAppLockEnabled()
    }
    
    /**
     * Enable app lock feature.
     */
    fun enableAppLock() {
        securePreferences.setAppLockEnabled(true)
        android.util.Log.d(TAG, "App lock enabled")
    }
    
    /**
     * Disable app lock feature.
     */
    fun disableAppLock() {
        securePreferences.setAppLockEnabled(false)
        android.util.Log.d(TAG, "App lock disabled")
    }
    
    /**
     * Check if app lock is configured and ready.
     * (Enabled + has authentication method)
     */
    fun isAppLockConfigured(): Boolean {
        return isAppLockEnabled() && 
               (securePreferences.isBiometricEnabled() || securePreferences.hasPinConfigured())
    }
}
