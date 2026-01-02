package com.baluhost.android.data.repository

import android.net.Uri
import com.baluhost.android.data.remote.api.SyncApi
import com.baluhost.android.data.remote.dto.sync.*
import com.baluhost.android.domain.model.sync.*
import com.baluhost.android.domain.repository.SyncRepository
import java.time.Instant
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import javax.inject.Inject

/**
 * Implementation of SyncRepository.
 * Handles API calls and DTO to domain model mapping for folder synchronization.
 */
class SyncRepositoryImpl @Inject constructor(
    private val syncApi: SyncApi
) : SyncRepository {
    
    override suspend fun getSyncFolders(deviceId: String): Result<List<SyncFolderConfig>> {
        return try {
            val response = syncApi.getSyncFolders(deviceId)
            Result.success(response.folders.map { it.toDomain() })
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    override suspend fun createSyncFolder(
        deviceId: String,
        localPath: String,
        remotePath: String,
        syncType: SyncType,
        autoSync: Boolean,
        conflictResolution: ConflictResolution,
        excludePatterns: List<String>,
        adapterType: String,
        adapterUsername: String?,
        adapterPassword: String?,
        saveCredentials: Boolean
    ): Result<SyncFolderConfig> {
        return try {
            val dto = SyncFolderCreateDto(
                localPath = localPath,
                remotePath = remotePath,
                syncType = syncType.toApiString(),
                autoSync = autoSync,
                conflictResolution = conflictResolution.toApiString(),
                adapterType = adapterType,
                adapterUsername = adapterUsername,
                adapterPassword = adapterPassword,
                saveCredentials = saveCredentials,
                excludePatterns = excludePatterns
            )
            val response = syncApi.createSyncFolder(deviceId, dto)
            Result.success(response.toDomain())
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    override suspend fun updateSyncFolder(
        folderId: String,
        remotePath: String?,
        syncType: SyncType?,
        autoSync: Boolean?,
        conflictResolution: ConflictResolution?,
        excludePatterns: List<String>?,
        status: SyncStatus?,
        adapterType: String?,
        adapterUsername: String?,
        adapterPassword: String?,
        saveCredentials: Boolean?
    ): Result<SyncFolderConfig> {
        return try {
            val dto = SyncFolderUpdateDto(
                remotePath = remotePath,
                syncType = syncType?.toApiString(),
                autoSync = autoSync,
                conflictResolution = conflictResolution?.toApiString(),
                adapterType = adapterType,
                adapterUsername = adapterUsername,
                adapterPassword = adapterPassword,
                saveCredentials = saveCredentials,
                excludePatterns = excludePatterns,
                status = status?.toApiString()
            )
            val response = syncApi.updateSyncFolder(folderId, dto)
            Result.success(response.toDomain())
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    override suspend fun deleteSyncFolder(folderId: String): Result<Unit> {
        return try {
            syncApi.deleteSyncFolder(folderId)
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    override suspend fun triggerSync(folderId: String): Result<String> {
        return try {
            val response = syncApi.triggerSync(folderId)
            Result.success(response.message)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    override suspend fun getSyncStatus(folderId: String): Result<SyncStatus> {
        return try {
            val response = syncApi.getSyncStatus(folderId)
            Result.success(SyncStatus.fromString(response.status))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    override suspend fun getUploadQueue(deviceId: String): Result<List<UploadQueueItem>> {
        return try {
            val response = syncApi.getUploadQueue(deviceId)
            Result.success(response.items.map { it.toDomain() })
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    override suspend fun cancelUpload(uploadId: String): Result<Unit> {
        return try {
            syncApi.cancelUpload(uploadId)
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    override suspend fun retryUpload(uploadId: String): Result<UploadQueueItem> {
        return try {
            val response = syncApi.retryUpload(uploadId)
            Result.success(response.toDomain())
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    /**
     * List remote files in a folder.
     */
    suspend fun listRemoteFiles(folderId: Long, remotePath: String): List<RemoteFileInfo> {
        return try {
            val response = syncApi.listRemoteFiles(folderId.toString(), remotePath)
            response.files.map { it.toDomain() }
        } catch (e: Exception) {
            emptyList()
        }
    }
    
    /**
     * Upload a file (for small files).
     */
    suspend fun uploadFile(
        folderId: Long,
        remotePath: String,
        file: okhttp3.MultipartBody.Part
    ) {
        syncApi.uploadFile(folderId.toString(), remotePath, file)
    }
    
    /**
     * Initiate chunked upload.
     */
    suspend fun initiateChunkedUpload(
        request: InitiateUploadDto
    ): InitiateUploadResponseDto {
        return syncApi.initiateChunkedUpload(request)
    }
    
    /**
     * Upload a chunk.
     */
    suspend fun uploadChunk(
        metadata: ChunkUploadDto,
        chunk: okhttp3.MultipartBody.Part
    ): ChunkUploadResponseDto {
        return syncApi.uploadChunk(metadata, chunk)
    }
    
    /**
     * Finalize chunked upload.
     */
    suspend fun finalizeChunkedUpload(uploadId: String) {
        syncApi.finalizeChunkedUpload(uploadId)
    }
    
    /**
     * Cancel chunked upload.
     */
    suspend fun cancelChunkedUpload(uploadId: String) {
        syncApi.cancelChunkedUpload(uploadId)
    }
    
    /**
     * Download a file.
     */
    suspend fun downloadFile(
        folderId: Long,
        remotePath: String
    ): okhttp3.ResponseBody {
        return syncApi.downloadFile(folderId.toString(), remotePath)
    }
}

/**
 * Extension functions to map DTOs to domain models.
 */

private fun SyncFolderDto.toDomain() = SyncFolderConfig(
    id = id,
    deviceId = deviceId,
    localUri = Uri.parse(localPath),
    remotePath = remotePath,
    syncType = SyncType.fromString(syncType),
    autoSync = autoSync,
    conflictResolution = ConflictResolution.fromString(conflictResolution ?: "keep_newest"),
    syncStatus = SyncStatus.fromString(status),
    lastSync = lastSync?.let { parseIsoTimestamp(it) },
    excludePatterns = excludePatterns ?: emptyList()
)

private fun RemoteFileDto.toDomain() = RemoteFileInfo(
    relativePath = relativePath,
    name = name,
    size = size,
    hash = hash,
    modifiedAt = parseIsoTimestamp(modifiedAt)
)

private fun UploadQueueDto.toDomain() = UploadQueueItem(
    id = id,
    folderId = folderId ?: "",
    fileName = filename,
    filePath = "", // Local path not returned by API
    remotePath = remotePath,
    fileSize = fileSize,
    uploadedBytes = uploadedBytes,
    status = UploadStatus.fromString(status),
    retryCount = retryCount,
    createdAt = parseIsoTimestamp(createdAt),
    errorMessage = errorMessage
)

/**
 * Parse ISO 8601 timestamp to milliseconds since epoch.
 */
private fun parseIsoTimestamp(timestamp: String): Long {
    return try {
        val zonedDateTime = ZonedDateTime.parse(timestamp, DateTimeFormatter.ISO_DATE_TIME)
        zonedDateTime.toInstant().toEpochMilli()
    } catch (e: Exception) {
        // Fallback to simple ISO instant parsing
        try {
            Instant.parse(timestamp).toEpochMilli()
        } catch (e2: Exception) {
            0L
        }
    }
}
