package com.baluhost.android.domain.model.sync

/**
 * Sync history entry for tracking completed syncs.
 */
data class SyncHistory(
    val id: String,
    val folderId: Long,
    val folderName: String,
    val timestamp: Long,
    val status: SyncHistoryStatus,
    val filesUploaded: Int,
    val filesDownloaded: Int,
    val filesDeleted: Int,
    val conflictsDetected: Int,
    val conflictsResolved: Int,
    val bytesTransferred: Long,
    val durationMs: Long,
    val errorMessage: String? = null
) {
    val startTime: Long
        get() = timestamp
    
    val endTime: Long
        get() = timestamp + durationMs
    
    val duration: Long
        get() = durationMs
    
    val isSuccessful: Boolean
        get() = status == SyncHistoryStatus.SUCCESS
}

/**
 * Status of a sync history entry.
 */
enum class SyncHistoryStatus {
    SUCCESS,
    PARTIAL_SUCCESS,  // Completed with some conflicts
    FAILED,
    CANCELLED;
    
    companion object {
        fun fromString(value: String): SyncHistoryStatus {
            return when (value.lowercase()) {
                "success" -> SUCCESS
                "partial_success", "partial" -> PARTIAL_SUCCESS
                "failed", "error" -> FAILED
                "cancelled" -> CANCELLED
                else -> FAILED
            }
        }
    }
}

/**
 * Summary statistics for sync history.
 */
data class SyncHistorySummary(
    val totalSyncs: Int,
    val successfulSyncs: Int,
    val failedSyncs: Int,
    val totalFilesUploaded: Int,
    val totalFilesDownloaded: Int,
    val totalBytesTransferred: Long,
    val totalConflictsDetected: Int,
    val totalConflictsResolved: Int,
    val lastSyncTimestamp: Long?,
    val totalFilesTransferred: Int = totalFilesUploaded + totalFilesDownloaded,
    val averageDuration: Long = 0L,
    val lastSyncTime: Long? = lastSyncTimestamp
)
