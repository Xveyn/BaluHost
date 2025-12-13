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
        
        // Default auto-lock timeout: 10 seconds (for testing - should be 5 minutes in production)
        const val DEFAULT_TIMEOUT_MILLIS = 10 * 1000L
        
        // Keys
        private val KEY_LAST_BACKGROUND_TIME = longPreferencesKey("last_background_time")
        private val KEY_LOCK_TIMEOUT_MILLIS = longPreferencesKey("lock_timeout_millis")
        
        // Track if this is a fresh process start
        private var isProcessFreshStart = true
    }
    
    /**
     * Record the timestamp when app goes to background.
     */
    suspend fun onAppBackground() {
        if (!isAppLockEnabled()) {
            return
        }
        
        // Mark that this is no longer a fresh start
        isProcessFreshStart = false
        
        val currentTime = System.currentTimeMillis()
        dataStore.edit { prefs ->
            prefs[KEY_LAST_BACKGROUND_TIME] = currentTime
        }
        android.util.Log.d(TAG, "App went to background at $currentTime")
    }
    
    /**
     * Check if lock screen should be shown when app resumes.
     * 
     * Best Practice:
     * - If app process was killed (fresh start) → ALWAYS show lock
     * - If app was just in background → show lock after timeout (10 seconds)
     * 
     * @return true if lock screen should be shown
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
        
        // Check if this is a fresh process start (app was killed and restarted)
        if (isProcessFreshStart) {
            android.util.Log.d(TAG, "Fresh process start - showing lock screen")
            isProcessFreshStart = false // Mark as seen
            return true
        }
        
        // Get last background time
        val lastBackgroundTime = dataStore.data.map { prefs ->
            prefs[KEY_LAST_BACKGROUND_TIME] ?: 0L
        }.first()
        
        if (lastBackgroundTime == 0L) {
            // No background time recorded yet - first run after install
            android.util.Log.d(TAG, "No background time recorded - showing lock screen")
            return true
        }
        
        // App was just in background - check timeout
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
        // Clear the timestamp completely so next cold start shows lock screen
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
