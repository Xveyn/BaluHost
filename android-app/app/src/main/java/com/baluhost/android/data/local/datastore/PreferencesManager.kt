package com.baluhost.android.data.local.datastore

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import com.baluhost.android.data.local.security.SecurePreferencesManager
import com.baluhost.android.util.Constants
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
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
    private val userRoleKey = stringPreferencesKey("user_role")
    private val devModeKey = stringPreferencesKey("dev_mode")
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
    
    // User Role
    suspend fun saveUserRole(role: String) {
        dataStore.edit { prefs -> prefs[userRoleKey] = role }
    }
    
    fun getUserRole(): Flow<String?> {
        return dataStore.data.map { prefs -> prefs[userRoleKey] }
    }
    
    // Dev Mode Flag
    suspend fun saveDevMode(devMode: Boolean) {
        dataStore.edit { prefs -> prefs[devModeKey] = devMode.toString() }
    }
    
    fun getDevMode(): Flow<Boolean> {
        return dataStore.data.map { prefs -> 
            prefs[devModeKey]?.toBoolean() ?: false 
        }
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
    
    // Sync Folder URIs (stored as JSON string map: folderId -> URI string)
    suspend fun saveSyncFolderUri(folderId: String, uri: String) {
        dataStore.edit { prefs ->
            val key = stringPreferencesKey("sync_folder_uri_$folderId")
            prefs[key] = uri
        }
    }
    
    suspend fun getSyncFolderUri(folderId: String): String? {
        val key = stringPreferencesKey("sync_folder_uri_$folderId")
        return dataStore.data.map { prefs -> prefs[key] }.first()
    }
    
    suspend fun removeSyncFolderUri(folderId: String) {
        dataStore.edit { prefs ->
            val key = stringPreferencesKey("sync_folder_uri_$folderId")
            prefs.remove(key)
        }
    }
    
    // Pending conflicts for manual resolution
    suspend fun savePendingConflicts(folderId: Long, conflicts: List<com.baluhost.android.domain.model.sync.FileConflict>) {
        val key = stringPreferencesKey("pending_conflicts_$folderId")
        val conflictsJson = conflicts.joinToString("|||") { conflict ->
            "${conflict.id}::${conflict.relativePath}::${conflict.fileName}::" +
            "${conflict.localSize}::${conflict.remoteSize}::" +
            "${conflict.localModifiedAt}::${conflict.remoteModifiedAt}::${conflict.detectedAt}"
        }
        dataStore.edit { prefs ->
            prefs[key] = conflictsJson
        }
    }
    
    fun getPendingConflicts(folderId: Long): Flow<List<com.baluhost.android.domain.model.sync.FileConflict>> = flow {
        val key = stringPreferencesKey("pending_conflicts_$folderId")
        val conflictsJson = dataStore.data.map { prefs -> prefs[key] }.first()
        
        if (conflictsJson.isNullOrEmpty()) {
            emit(emptyList())
        } else {
            val conflicts = conflictsJson.split("|||").mapNotNull { entry ->
                try {
                    val parts = entry.split("::")
                    if (parts.size >= 8) {
                        com.baluhost.android.domain.model.sync.FileConflict(
                            id = parts[0],
                            relativePath = parts[1],
                            fileName = parts[2],
                            localSize = parts[3].toLong(),
                            remoteSize = parts[4].toLong(),
                            localModifiedAt = parts[5].toLong(),
                            remoteModifiedAt = parts[6].toLong(),
                            detectedAt = parts[7].toLong()
                        )
                    } else null
                } catch (e: Exception) {
                    null
                }
            }
            emit(conflicts)
        }
    }
    
    suspend fun clearPendingConflicts(folderId: Long) {
        dataStore.edit { prefs ->
            val key = stringPreferencesKey("pending_conflicts_$folderId")
            prefs.remove(key)
        }
    }
    
    // Sync History (stored as JSON string, max 50 entries)
    suspend fun saveSyncHistory(history: com.baluhost.android.domain.model.sync.SyncHistory) {
        val key = stringPreferencesKey("sync_history")
        
        // Get existing history
        val existingJson = dataStore.data.map { prefs -> prefs[key] }.first()
        val existingHistory = if (!existingJson.isNullOrEmpty()) {
            existingJson.split("|||").mapNotNull { entry ->
                try {
                    val parts = entry.split("::")
                    if (parts.size >= 10) {
                        com.baluhost.android.domain.model.sync.SyncHistory(
                            id = parts[0],
                            folderId = parts[1].toLong(),
                            folderName = parts[2],
                            timestamp = parts[3].toLong(),
                            status = com.baluhost.android.domain.model.sync.SyncHistoryStatus.valueOf(parts[4]),
                            filesUploaded = parts[5].toInt(),
                            filesDownloaded = parts[6].toInt(),
                            filesDeleted = parts[7].toInt(),
                            conflictsDetected = parts[8].toInt(),
                            conflictsResolved = parts[9].toInt(),
                            bytesTransferred = parts[10].toLong(),
                            durationMs = parts[11].toLong(),
                            errorMessage = parts.getOrNull(12)?.takeIf { it != "null" }
                        )
                    } else null
                } catch (e: Exception) {
                    null
                }
            }.toMutableList()
        } else {
            mutableListOf()
        }
        
        // Add new entry at the beginning
        existingHistory.add(0, history)
        
        // Keep only last 50 entries
        val trimmedHistory = existingHistory.take(50)
        
        // Serialize back to string
        val newJson = trimmedHistory.joinToString("|||") { h ->
            "${h.id}::${h.folderId}::${h.folderName}::" +
            "${h.timestamp}::${h.status}::" +
            "${h.filesUploaded}::${h.filesDownloaded}::${h.filesDeleted}::" +
            "${h.conflictsDetected}::${h.conflictsResolved}::" +
            "${h.bytesTransferred}::${h.durationMs}::${h.errorMessage}"
        }
        
        dataStore.edit { prefs ->
            prefs[key] = newJson
        }
    }
    
    fun getSyncHistory(folderId: Long? = null): Flow<List<com.baluhost.android.domain.model.sync.SyncHistory>> = flow {
        val key = stringPreferencesKey("sync_history")
        val historyJson = dataStore.data.map { prefs -> prefs[key] }.first()
        
        if (historyJson.isNullOrEmpty()) {
            emit(emptyList())
        } else {
            val history = historyJson.split("|||").mapNotNull { entry ->
                try {
                    val parts = entry.split("::")
                    if (parts.size >= 10) {
                        com.baluhost.android.domain.model.sync.SyncHistory(
                            id = parts[0],
                            folderId = parts[1].toLong(),
                            folderName = parts[2],
                            timestamp = parts[3].toLong(),
                            status = com.baluhost.android.domain.model.sync.SyncHistoryStatus.valueOf(parts[4]),
                            filesUploaded = parts[5].toInt(),
                            filesDownloaded = parts[6].toInt(),
                            filesDeleted = parts[7].toInt(),
                            conflictsDetected = parts[8].toInt(),
                            conflictsResolved = parts[9].toInt(),
                            bytesTransferred = parts[10].toLong(),
                            durationMs = parts[11].toLong(),
                            errorMessage = parts.getOrNull(12)?.takeIf { it != "null" }
                        )
                    } else null
                } catch (e: Exception) {
                    null
                }
            }
            
            // Filter by folderId if provided
            val filtered = if (folderId != null) {
                history.filter { it.folderId == folderId }
            } else {
                history
            }
            
            emit(filtered)
        }
    }
    
    fun getSyncHistorySummary(): Flow<com.baluhost.android.domain.model.sync.SyncHistorySummary> = flow {
        val history = getSyncHistory().first()
        
        val summary = com.baluhost.android.domain.model.sync.SyncHistorySummary(
            totalSyncs = history.size,
            successfulSyncs = history.count { it.status == com.baluhost.android.domain.model.sync.SyncHistoryStatus.SUCCESS },
            failedSyncs = history.count { it.status == com.baluhost.android.domain.model.sync.SyncHistoryStatus.FAILED },
            totalFilesUploaded = history.sumOf { it.filesUploaded },
            totalFilesDownloaded = history.sumOf { it.filesDownloaded },
            totalBytesTransferred = history.sumOf { it.bytesTransferred },
            totalConflictsDetected = history.sumOf { it.conflictsDetected },
            totalConflictsResolved = history.sumOf { it.conflictsResolved },
            lastSyncTimestamp = history.maxOfOrNull { it.timestamp }
        )
        
        emit(summary)
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
