package com.baluhost.android.data.remote.dto.sync

import com.google.gson.annotations.SerializedName

/**
 * DTOs for sync folder endpoints.
 * Matches backend schemas from mobile_schemas.py
 */

data class SyncFolderDto(
    @SerializedName("id")
    val id: String,
    @SerializedName("device_id")
    val deviceId: String,
    @SerializedName("local_path")
    val localPath: String,
    @SerializedName("remote_path")
    val remotePath: String,
    @SerializedName("sync_type")
    val syncType: String,
    @SerializedName("auto_sync")
    val autoSync: Boolean,
    @SerializedName("conflict_resolution")
    val conflictResolution: String? = null,
    @SerializedName("exclude_patterns")
    val excludePatterns: List<String>? = null,
    @SerializedName("last_sync")
    val lastSync: String?,
    @SerializedName("status")
    val status: String
)

data class SyncFolderCreateDto(
    @SerializedName("local_path")
    val localPath: String,
    @SerializedName("remote_path")
    val remotePath: String,
    @SerializedName("sync_type")
    val syncType: String,
    @SerializedName("auto_sync")
    val autoSync: Boolean = true,
    @SerializedName("conflict_resolution")
    val conflictResolution: String = "keep_newest",
    @SerializedName("adapter_type")
    val adapterType: String = "webdav",
    @SerializedName("adapter_username")
    val adapterUsername: String? = null,
    @SerializedName("adapter_password")
    val adapterPassword: String? = null,
    @SerializedName("save_credentials")
    val saveCredentials: Boolean = false,
    @SerializedName("exclude_patterns")
    val excludePatterns: List<String> = emptyList()
)

data class SyncFolderUpdateDto(
    @SerializedName("remote_path")
    val remotePath: String? = null,
    @SerializedName("sync_type")
    val syncType: String? = null,
    @SerializedName("auto_sync")
    val autoSync: Boolean? = null,
    @SerializedName("conflict_resolution")
    val conflictResolution: String? = null,
    @SerializedName("adapter_type")
    val adapterType: String? = null,
    @SerializedName("adapter_username")
    val adapterUsername: String? = null,
    @SerializedName("adapter_password")
    val adapterPassword: String? = null,
    @SerializedName("save_credentials")
    val saveCredentials: Boolean? = null,
    @SerializedName("exclude_patterns")
    val excludePatterns: List<String>? = null,
    @SerializedName("status")
    val status: String? = null
)

data class SyncFolderListResponseDto(
    @SerializedName("folders")
    val folders: List<SyncFolderDto>
)

data class UploadQueueDto(
    @SerializedName("id")
    val id: String,
    @SerializedName("device_id")
    val deviceId: String,
    @SerializedName("folder_id")
    val folderId: String?,
    @SerializedName("filename")
    val filename: String,
    @SerializedName("remote_path")
    val remotePath: String,
    @SerializedName("file_size")
    val fileSize: Long,
    @SerializedName("uploaded_bytes")
    val uploadedBytes: Long,
    @SerializedName("status")
    val status: String,
    @SerializedName("retry_count")
    val retryCount: Int,
    @SerializedName("created_at")
    val createdAt: String,
    @SerializedName("error_message")
    val errorMessage: String?
)

data class UploadQueueListResponseDto(
    @SerializedName("items")
    val items: List<UploadQueueDto>
)

data class SyncTriggerResponseDto(
    @SerializedName("status")
    val status: String,
    @SerializedName("message")
    val message: String
)

data class SyncStatusResponseDto(
    @SerializedName("folder_id")
    val folderId: String,
    @SerializedName("status")
    val status: String,
    @SerializedName("progress")
    val progress: Float?,
    @SerializedName("total_files")
    val totalFiles: Int?,
    @SerializedName("synced_files")
    val syncedFiles: Int?,
    @SerializedName("last_sync")
    val lastSync: String?,
    @SerializedName("error_message")
    val errorMessage: String?
)
