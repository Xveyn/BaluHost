package com.baluhost.android.data.remote.dto

import com.google.gson.annotations.SerializedName

// ==================== File DTOs ====================

data class FileListResponse(
    val path: String,
    val files: List<FileItemDto>
)

data class FileItemDto(
    val name: String,
    val path: String,
    val size: Long,
    @SerializedName("is_directory")
    val isDirectory: Boolean,
    @SerializedName("modified_at")
    val modifiedAt: String,
    val owner: String? = null,
    val permissions: String? = null,
    @SerializedName("mime_type")
    val mimeType: String? = null
)

data class UploadFileResponse(
    val message: String,
    val uploaded: Int,
    @SerializedName("upload_ids")
    val uploadIds: List<String>? = null
)

data class DeleteFileRequest(
    val path: String
)

data class DeleteFileResponse(
    val message: String,
    val path: String
)

data class CreateFolderRequest(
    val path: String,
    val name: String
)

data class CreateFolderResponse(
    val message: String,
    val folder: FileItemDto
)

data class MoveFileRequest(
    @SerializedName("source_path")
    val sourcePath: String,
    @SerializedName("destination_path")
    val destinationPath: String
)

data class MoveFileResponse(
    val message: String,
    val file: FileItemDto
)

data class RenameFileRequest(
    val path: String,
    @SerializedName("new_name")
    val newName: String
)

data class RenameFileResponse(
    val message: String,
    val file: FileItemDto
)

data class FileMetadataResponse(
    val file: FileItemDto
)
