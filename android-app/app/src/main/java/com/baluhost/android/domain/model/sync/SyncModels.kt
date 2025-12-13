package com.baluhost.android.domain.model.sync

import android.net.Uri

/**
 * Domain models for folder synchronization.
 * Matches backend SyncFolder model from mobile_schemas.py
 */

data class SyncFolderConfig(
    val id: String,
    val deviceId: String,
    val localUri: Uri,  // SAF content URI
    val remotePath: String,
    val syncType: SyncType,
    val autoSync: Boolean,
    val conflictResolution: ConflictResolution,
    val syncStatus: SyncStatus,
    val lastSync: Long?,  // Timestamp in milliseconds
    val totalFiles: Int = 0,
    val syncedFiles: Int = 0,
    val excludePatterns: List<String> = emptyList()
) {
    val syncProgress: Float
        get() = if (totalFiles > 0) syncedFiles.toFloat() / totalFiles else 0f
}

/**
 * Sync type defines the direction of synchronization.
 */
enum class SyncType {
    UPLOAD_ONLY,      // Only upload local files to server
    DOWNLOAD_ONLY,    // Only download server files to local
    BIDIRECTIONAL;    // Sync in both directions
    
    companion object {
        fun fromString(value: String): SyncType {
            return when (value.lowercase()) {
                "upload", "upload_only" -> UPLOAD_ONLY
                "download", "download_only" -> DOWNLOAD_ONLY
                "bidirectional", "two_way" -> BIDIRECTIONAL
                else -> UPLOAD_ONLY
            }
        }
    }
    
    fun toApiString(): String {
        return when (this) {
            UPLOAD_ONLY -> "upload"
            DOWNLOAD_ONLY -> "download"
            BIDIRECTIONAL -> "bidirectional"
        }
    }
}

/**
 * Sync status represents the current state of synchronization.
 */
enum class SyncStatus {
    IDLE,       // Not currently syncing
    SYNCING,    // Actively syncing files
    ERROR,      // Sync failed
    PAUSED;     // User paused sync
    
    companion object {
        fun fromString(value: String): SyncStatus {
            return when (value.lowercase()) {
                "idle" -> IDLE
                "syncing", "in_progress" -> SYNCING
                "error", "failed" -> ERROR
                "paused" -> PAUSED
                else -> IDLE
            }
        }
    }
    
    fun toApiString(): String {
        return name.lowercase()
    }
}

/**
 * Conflict resolution strategy when file is modified on both sides.
 */
enum class ConflictResolution {
    KEEP_LOCAL,     // Always prefer phone version
    KEEP_SERVER,    // Always prefer NAS version
    KEEP_NEWEST,    // Compare timestamps
    ASK_USER;       // Show dialog for each conflict
    
    companion object {
        fun fromString(value: String): ConflictResolution {
            return when (value.lowercase()) {
                "keep_local", "local" -> KEEP_LOCAL
                "keep_server", "server" -> KEEP_SERVER
                "keep_newest", "newest" -> KEEP_NEWEST
                "ask_user", "ask", "manual" -> ASK_USER
                else -> KEEP_NEWEST
            }
        }
    }
    
    fun toApiString(): String {
        return when (this) {
            KEEP_LOCAL -> "keep_local"
            KEEP_SERVER -> "keep_server"
            KEEP_NEWEST -> "keep_newest"
            ASK_USER -> "ask_user"
        }
    }
}

/**
 * Upload queue item for tracking individual file uploads.
 */
data class UploadQueueItem(
    val id: String,
    val folderId: String,
    val fileName: String,
    val filePath: String,
    val remotePath: String,
    val fileSize: Long,
    val uploadedBytes: Long,
    val status: UploadStatus,
    val retryCount: Int,
    val maxRetries: Int = 3,
    val createdAt: Long,
    val errorMessage: String? = null
) {
    val progress: Float
        get() = if (fileSize > 0) uploadedBytes.toFloat() / fileSize else 0f
    
    val canRetry: Boolean
        get() = retryCount < maxRetries && status == UploadStatus.FAILED
}

enum class UploadStatus {
    PENDING,
    UPLOADING,
    COMPLETED,
    FAILED,
    CANCELLED;
    
    companion object {
        fun fromString(value: String): UploadStatus {
            return when (value.lowercase()) {
                "pending" -> PENDING
                "uploading", "in_progress" -> UPLOADING
                "completed", "success" -> COMPLETED
                "failed", "error" -> FAILED
                "cancelled" -> CANCELLED
                else -> PENDING
            }
        }
    }
}

/**
 * File conflict details.
 */
data class FileConflict(
    val id: String,
    val relativePath: String,
    val fileName: String,
    val localSize: Long,
    val remoteSize: Long,
    val localModifiedAt: Long,
    val remoteModifiedAt: Long,
    val detectedAt: Long,
    val filePath: String = relativePath,
    val localHash: String = "",
    val serverHash: String = "",
    val localModified: Long = localModifiedAt,
    val serverModified: Long = remoteModifiedAt,
    val resolution: ConflictResolution? = null
)

/**
 * Sync result summary.
 */
data class SyncResult(
    val folderId: String,
    val success: Boolean,
    val filesUploaded: Int,
    val filesDownloaded: Int,
    val filesDeleted: Int,
    val conflicts: Int,
    val errors: List<String>,
    val duration: Long,  // Milliseconds
    val timestamp: Long
)

/**
 * Information about a remote file on the server.
 */
data class RemoteFileInfo(
    val relativePath: String,
    val name: String,
    val size: Long,
    val hash: String,
    val modifiedAt: Long  // Timestamp in milliseconds
)
