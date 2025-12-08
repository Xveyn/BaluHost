package com.baluhost.android.data.local.datastore

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import com.baluhost.android.util.Constants
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manages app preferences using DataStore.
 * 
 * Stores non-sensitive data like server URL, user preferences.
 * Sensitive data (tokens) are stored in SecureStorage.
 */
@Singleton
class PreferencesManager @Inject constructor(
    private val dataStore: DataStore<Preferences>
) {
    
    // Keys
    private val accessTokenKey = stringPreferencesKey(Constants.PrefsKeys.ACCESS_TOKEN)
    private val refreshTokenKey = stringPreferencesKey(Constants.PrefsKeys.REFRESH_TOKEN)
    private val serverUrlKey = stringPreferencesKey(Constants.PrefsKeys.SERVER_URL)
    private val userIdKey = stringPreferencesKey(Constants.PrefsKeys.USER_ID)
    private val usernameKey = stringPreferencesKey(Constants.PrefsKeys.USERNAME)
    private val cameraBackupEnabledKey = stringPreferencesKey(Constants.PrefsKeys.CAMERA_BACKUP_ENABLED)
    private val wifiOnlyKey = stringPreferencesKey(Constants.PrefsKeys.WIFI_ONLY)
    private val lastBackupTimeKey = stringPreferencesKey(Constants.PrefsKeys.LAST_BACKUP_TIME)
    private val vpnConfigKey = stringPreferencesKey(Constants.PrefsKeys.VPN_CONFIG)
    
    // Access Token
    suspend fun saveAccessToken(token: String) {
        dataStore.edit { prefs -> prefs[accessTokenKey] = token }
    }
    
    fun getAccessToken(): Flow<String?> {
        return dataStore.data.map { prefs -> prefs[accessTokenKey] }
    }
    
    // Refresh Token
    suspend fun saveRefreshToken(token: String) {
        dataStore.edit { prefs -> prefs[refreshTokenKey] = token }
    }
    
    fun getRefreshToken(): Flow<String?> {
        return dataStore.data.map { prefs -> prefs[refreshTokenKey] }
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
    
    // Clear all tokens (on logout or auth failure)
    suspend fun clearTokens() {
        dataStore.edit { prefs ->
            prefs.remove(accessTokenKey)
            prefs.remove(refreshTokenKey)
        }
    }
    
    // Clear all data
    suspend fun clearAll() {
        dataStore.edit { prefs -> prefs.clear() }
    }
}
