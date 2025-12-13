package com.baluhost.android.data.remote.dto.sync

import com.google.gson.annotations.SerializedName

/**
 * DTO for initiating a chunked upload.
 */
data class InitiateUploadDto(
    @SerializedName("folder_id")
    val folderId: Long,
    @SerializedName("remote_path")
    val remotePath: String,
    @SerializedName("file_size")
    val fileSize: Long,
    @SerializedName("file_hash")
    val fileHash: String,
    @SerializedName("total_chunks")
    val totalChunks: Int
)

/**
 * Response from initiating a chunked upload.
 */
data class InitiateUploadResponseDto(
    @SerializedName("upload_id")
    val uploadId: String,
    @SerializedName("total_chunks")
    val totalChunks: Int,
    @SerializedName("chunk_size")
    val chunkSize: Long
)

/**
 * DTO for uploading a chunk.
 */
data class ChunkUploadDto(
    @SerializedName("upload_id")
    val uploadId: String,
    @SerializedName("chunk_index")
    val chunkIndex: Int,
    @SerializedName("chunk_hash")
    val chunkHash: String
)

/**
 * Response from uploading a chunk.
 */
data class ChunkUploadResponseDto(
    @SerializedName("upload_id")
    val uploadId: String,
    @SerializedName("chunk_index")
    val chunkIndex: Int,
    @SerializedName("received")
    val received: Boolean
)

/**
 * DTO for remote file information.
 */
data class RemoteFileDto(
    @SerializedName("relative_path")
    val relativePath: String,
    @SerializedName("name")
    val name: String,
    @SerializedName("size")
    val size: Long,
    @SerializedName("hash")
    val hash: String,
    @SerializedName("modified_at")
    val modifiedAt: String
)

/**
 * Response containing list of remote files.
 */
data class RemoteFileListResponseDto(
    @SerializedName("files")
    val files: List<RemoteFileDto>
)
