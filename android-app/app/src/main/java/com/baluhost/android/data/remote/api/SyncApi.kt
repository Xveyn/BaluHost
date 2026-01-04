package com.baluhost.android.data.remote.api

import com.baluhost.android.data.remote.dto.sync.*
import retrofit2.http.*

/**
 * API interface for folder synchronization endpoints.
 * Connects to existing backend sync endpoints from mobile_routes.py
 */
interface SyncApi {
    
    /**
     * Get all sync folders for a device.
     */
    @GET("mobile/sync/folders/{device_id}")
    suspend fun getSyncFolders(
        @Path("device_id") deviceId: String
    ): List<SyncFolderDto>
    
    /**
     * Create a new sync folder configuration.
     */
    @POST("mobile/sync/folders/{device_id}")
    suspend fun createSyncFolder(
        @Path("device_id") deviceId: String,
        @Body folder: SyncFolderCreateDto
    ): SyncFolderDto
    
    /**
     * Update an existing sync folder.
     */
    @PUT("mobile/sync/folders/{folder_id}")
    suspend fun updateSyncFolder(
        @Path("folder_id") folderId: String,
        @Body updates: SyncFolderUpdateDto
    ): SyncFolderDto
    
    /**
     * Delete a sync folder.
     */
    @DELETE("mobile/sync/folders/{folder_id}")
    suspend fun deleteSyncFolder(
        @Path("folder_id") folderId: String
    )
    
    /**
     * Trigger manual sync for a folder.
     */
    @POST("mobile/sync/folders/{folder_id}/trigger")
    suspend fun triggerSync(
        @Path("folder_id") folderId: String
    ): SyncTriggerResponseDto
    
    /**
     * Get sync status for a folder.
     */
    @GET("mobile/sync/folders/{folder_id}/status")
    suspend fun getSyncStatus(
        @Path("folder_id") folderId: String
    ): SyncStatusResponseDto
    
    /**
     * Get upload queue for a device.
     */
    @GET("mobile/upload/queue/{device_id}")
    suspend fun getUploadQueue(
        @Path("device_id") deviceId: String
    ): UploadQueueListResponseDto
    
    /**
     * Cancel an upload.
     */
    @DELETE("mobile/upload/queue/{upload_id}")
    suspend fun cancelUpload(
        @Path("upload_id") uploadId: String
    )
    
    /**
     * Retry a failed upload.
     */
    @POST("mobile/upload/queue/{upload_id}/retry")
    suspend fun retryUpload(
        @Path("upload_id") uploadId: String
    ): UploadQueueDto
    
    /**
     * List files in a remote folder.
     */
    @GET("mobile/sync/folders/{folder_id}/files")
    suspend fun listRemoteFiles(
        @Path("folder_id") folderId: String,
        @Query("path") remotePath: String
    ): RemoteFileListResponseDto
    
    /**
     * Upload a file (single request for small files).
     */
    @Multipart
    @POST("mobile/upload/file/{folder_id}")
    suspend fun uploadFile(
        @Path("folder_id") folderId: String,
        @Query("remote_path") remotePath: String,
        @Part file: okhttp3.MultipartBody.Part
    )
    
    /**
     * Initiate a chunked upload for large files.
     */
    @POST("mobile/upload/chunked/initiate")
    suspend fun initiateChunkedUpload(
        @Body request: InitiateUploadDto
    ): InitiateUploadResponseDto
    
    /**
     * Upload a single chunk.
     */
    @Multipart
    @POST("mobile/upload/chunked/chunk")
    suspend fun uploadChunk(
        @Part("metadata") metadata: ChunkUploadDto,
        @Part chunk: okhttp3.MultipartBody.Part
    ): ChunkUploadResponseDto
    
    /**
     * Finalize a chunked upload.
     */
    @POST("mobile/upload/chunked/{upload_id}/finalize")
    suspend fun finalizeChunkedUpload(
        @Path("upload_id") uploadId: String
    )
    
    /**
     * Cancel a chunked upload.
     */
    @DELETE("mobile/upload/chunked/{upload_id}/cancel")
    suspend fun cancelChunkedUpload(
        @Path("upload_id") uploadId: String
    )
    
    /**
     * Download a file from server.
     */
    @Streaming
    @GET("mobile/download/file/{folder_id}")
    suspend fun downloadFile(
        @Path("folder_id") folderId: String,
        @Query("remote_path") remotePath: String
    ): okhttp3.ResponseBody
}
