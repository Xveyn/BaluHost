package com.baluhost.android.data.local.datastore

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import com.baluhost.android.data.local.security.SecurePreferencesManager
import com.baluhost.android.util.Constants
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manages app preferences using DataStore.
 * 
 * Stores non-sensitive data like server URL, user preferences.
 * Sensitive data (tokens, PIN, biometric settings) are stored in SecurePreferencesManager.
 */
@Singleton
class PreferencesManager @Inject constructor(
    private val dataStore: DataStore<Preferences>,
    private val securePreferences: SecurePreferencesManager
) {
    
    // Keys (access/refresh tokens now stored in SecurePreferencesManager)
    private val serverUrlKey = stringPreferencesKey(Constants.PrefsKeys.SERVER_URL)
    private val userIdKey = stringPreferencesKey(Constants.PrefsKeys.USER_ID)
    private val usernameKey = stringPreferencesKey(Constants.PrefsKeys.USERNAME)
    private val cameraBackupEnabledKey = stringPreferencesKey(Constants.PrefsKeys.CAMERA_BACKUP_ENABLED)
    private val wifiOnlyKey = stringPreferencesKey(Constants.PrefsKeys.WIFI_ONLY)
    private val lastBackupTimeKey = stringPreferencesKey(Constants.PrefsKeys.LAST_BACKUP_TIME)
    private val vpnConfigKey = stringPreferencesKey(Constants.PrefsKeys.VPN_CONFIG)
    private val fcmTokenKey = stringPreferencesKey("fcm_token")
    private val deviceIdKey = stringPreferencesKey("device_id")
    private val onboardingCompletedKey = stringPreferencesKey("onboarding_completed")
    
    // Access Token (delegated to SecurePreferencesManager for encryption)
    suspend fun saveAccessToken(token: String) {
        securePreferences.saveAccessToken(token)
    }
    
    fun getAccessToken(): Flow<String?> = flow {
        emit(securePreferences.getAccessToken())
    }
    
    // Refresh Token (delegated to SecurePreferencesManager for encryption)
    suspend fun saveRefreshToken(token: String) {
        securePreferences.saveRefreshToken(token)
    }
    
    fun getRefreshToken(): Flow<String?> = flow {
        emit(securePreferences.getRefreshToken())
    }
    
    // Server URL
    suspend fun saveServerUrl(url: String) {
        dataStore.edit { prefs -> prefs[serverUrlKey] = url }
    }
    
    fun getServerUrl(): Flow<String?> {
        return dataStore.data.map { prefs -> prefs[serverUrlKey] }
    }
    
    // User Info
    suspend fun saveUserId(userId: Int) {
        dataStore.edit { prefs -> prefs[userIdKey] = userId.toString() }
    }
    
    fun getUserId(): Flow<Int?> {
        return dataStore.data.map { prefs -> prefs[userIdKey]?.toIntOrNull() }
    }
    
    suspend fun saveUsername(username: String) {
        dataStore.edit { prefs -> prefs[usernameKey] = username }
    }
    
    fun getUsername(): Flow<String?> {
        return dataStore.data.map { prefs -> prefs[usernameKey] }
    }
    
    // Camera Backup Settings
    suspend fun saveCameraBackupEnabled(enabled: Boolean) {
        dataStore.edit { prefs -> prefs[cameraBackupEnabledKey] = enabled.toString() }
    }
    
    fun isCameraBackupEnabled(): Flow<Boolean> {
        return dataStore.data.map { prefs -> 
            prefs[cameraBackupEnabledKey]?.toBoolean() ?: false 
        }
    }
    
    suspend fun saveWifiOnly(wifiOnly: Boolean) {
        dataStore.edit { prefs -> prefs[wifiOnlyKey] = wifiOnly.toString() }
    }
    
    fun isWifiOnly(): Flow<Boolean> {
        return dataStore.data.map { prefs -> 
            prefs[wifiOnlyKey]?.toBoolean() ?: true 
        }
    }
    
    suspend fun saveLastBackupTime(timestamp: Long) {
        dataStore.edit { prefs -> prefs[lastBackupTimeKey] = timestamp.toString() }
    }
    
    fun getLastBackupTime(): Flow<Long> {
        return dataStore.data.map { prefs -> 
            prefs[lastBackupTimeKey]?.toLongOrNull() ?: 0L 
        }
    }
    
    // VPN Config
    suspend fun saveVpnConfig(config: String) {
        dataStore.edit { prefs -> prefs[vpnConfigKey] = config }
    }
    
    fun getVpnConfig(): Flow<String?> {
        return dataStore.data.map { prefs -> prefs[vpnConfigKey] }
    }
    
    // FCM Token (Firebase Cloud Messaging)
    suspend fun saveFcmToken(token: String) {
        dataStore.edit { prefs -> prefs[fcmTokenKey] = token }
    }
    
    fun getFcmToken(): Flow<String?> {
        return dataStore.data.map { prefs -> prefs[fcmTokenKey] }
    }
    
    // Device ID (from registration)
    suspend fun saveDeviceId(deviceId: String) {
        dataStore.edit { prefs -> prefs[deviceIdKey] = deviceId }
    }
    
    fun getDeviceId(): Flow<String?> {
        return dataStore.data.map { prefs -> prefs[deviceIdKey] }
    }
    
    // Onboarding State
    suspend fun saveOnboardingCompleted(completed: Boolean) {
        dataStore.edit { prefs -> prefs[onboardingCompletedKey] = completed.toString() }
    }
    
    fun isOnboardingCompleted(): Flow<Boolean> {
        return dataStore.data.map { prefs -> 
            prefs[onboardingCompletedKey]?.toBoolean() ?: false
        }
    }
    
    // Clear all tokens (on logout or auth failure)
    suspend fun clearTokens() {
        securePreferences.clearTokens()
    }
    
    // Clear all data
    suspend fun clearAll() {
        dataStore.edit { prefs -> prefs.clear() }
    }
}
