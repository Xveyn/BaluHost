package com.baluhost.android.domain.repository

import com.baluhost.android.domain.model.sync.*

/**
 * Repository interface for folder synchronization operations.
 */
interface SyncRepository {
    
    /**
     * Get all sync folders for the current device.
     */
    suspend fun getSyncFolders(deviceId: String): Result<List<SyncFolderConfig>>
    
    /**
     * Create a new sync folder configuration.
     */
    suspend fun createSyncFolder(
        deviceId: String,
        localPath: String,
        remotePath: String,
        syncType: SyncType,
        autoSync: Boolean = true,
        conflictResolution: ConflictResolution = ConflictResolution.KEEP_NEWEST,
        excludePatterns: List<String> = emptyList()
    ): Result<SyncFolderConfig>
    
    /**
     * Update an existing sync folder.
     */
    suspend fun updateSyncFolder(
        folderId: String,
        remotePath: String? = null,
        syncType: SyncType? = null,
        autoSync: Boolean? = null,
        conflictResolution: ConflictResolution? = null,
        excludePatterns: List<String>? = null,
        status: SyncStatus? = null
    ): Result<SyncFolderConfig>
    
    /**
     * Delete a sync folder.
     */
    suspend fun deleteSyncFolder(folderId: String): Result<Unit>
    
    /**
     * Trigger manual sync for a folder.
     */
    suspend fun triggerSync(folderId: String): Result<String>
    
    /**
     * Get sync status for a folder.
     */
    suspend fun getSyncStatus(folderId: String): Result<SyncStatus>
    
    /**
     * Get upload queue for the current device.
     */
    suspend fun getUploadQueue(deviceId: String): Result<List<UploadQueueItem>>
    
    /**
     * Cancel an upload.
     */
    suspend fun cancelUpload(uploadId: String): Result<Unit>
    
    /**
     * Retry a failed upload.
     */
    suspend fun retryUpload(uploadId: String): Result<UploadQueueItem>
}
