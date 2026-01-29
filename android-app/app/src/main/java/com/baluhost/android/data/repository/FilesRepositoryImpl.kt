package com.baluhost.android.data.repository

import com.baluhost.android.data.local.database.dao.FileDao
import com.baluhost.android.data.local.database.entities.FileEntity
import com.baluhost.android.data.remote.api.FilesApi
import com.baluhost.android.data.remote.dto.CreateFolderRequest
import com.baluhost.android.data.remote.dto.FileItemDto
import com.baluhost.android.data.remote.dto.MoveFileRequest
import com.baluhost.android.data.remote.dto.RenameFileRequest
import com.baluhost.android.domain.model.FileItem
import com.baluhost.android.domain.repository.FilesRepository
import com.baluhost.android.util.Result
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.ResponseBody
import java.io.File
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Implementation of FilesRepository with offline cache support.
 *
 * Strategy:
 * - Cache-First: Try local cache first, then network
 * - Network requests update cache automatically
 * - Stale cache is refreshed after 5 minutes
 */
@Singleton
class FilesRepositoryImpl @Inject constructor(
    private val filesApi: FilesApi,
    private val fileDao: FileDao
) : FilesRepository {

    companion object {
        private const val CACHE_VALIDITY_SECONDS = 300L  // 5 minutes
    }

    /**
     * Get files from cache or network.
     * Returns Flow that emits cached data immediately, then network data when available.
     */
    override fun getFiles(path: String, forceRefresh: Boolean): Flow<List<FileItem>> {
        return fileDao.getFilesByPath(path).map { entities ->
            // Check if cache is stale
            val isStale = entities.isEmpty() ||
                entities.any {
                    Instant.now().minusSeconds(CACHE_VALIDITY_SECONDS).isAfter(it.cachedAt)
                }

            // Refresh if stale or forced
            if (isStale || forceRefresh) {
                refreshFiles(path)
            }

            // Return cached data (will be updated when refresh completes)
            entities.map { it.toDomain() }
        }
    }

    /**
     * Fetch files from network and update cache.
     */
    override suspend fun refreshFiles(path: String): Result<List<FileItem>> {
        return try {
            val response = filesApi.listFiles(path)

            val files = response.files.map { dto ->
                FileEntity(
                    path = dto.path,
                    name = dto.name,
                    size = dto.size,
                    isDirectory = dto.isDirectory,
                    modifiedAt = Instant.parse(dto.modifiedAt),
                    owner = dto.owner,
                    permissions = dto.permissions,
                    mimeType = dto.mimeType,
                    parentPath = path,
                    cachedAt = Instant.now()
                )
            }

            // Clear old cache for this path and insert new data
            fileDao.deleteFilesInPath(path)
            fileDao.insertFiles(files)

            Result.Success(files.map { it.toDomain() })
        } catch (e: Exception) {
            Result.Error(Exception("Failed to refresh files: ${e.message}", e))
        }
    }

    /**
     * Upload file to server.
     */
    override suspend fun uploadFile(file: File, destinationPath: String): Result<Unit> {
        return try {
            val requestFile = file.asRequestBody("application/octet-stream".toMediaTypeOrNull())
            val filePart = MultipartBody.Part.createFormData("files", file.name, requestFile)
            val pathBody = destinationPath.toRequestBody("text/plain".toMediaTypeOrNull())

            filesApi.uploadFile(filePart, pathBody)

            // Invalidate cache for the destination directory to force refresh
            val parentPath = destinationPath.substringBeforeLast('/', "")
            fileDao.deleteFilesInPath(parentPath)

            Result.Success(Unit)
        } catch (e: Exception) {
            Result.Error(Exception("Upload failed: ${e.message}", e))
        }
    }

    /**
     * Download file from server.
     */
    override suspend fun downloadFile(filePath: String): Result<ResponseBody> {
        return try {
            val response = filesApi.downloadFile(filePath)
            Result.Success(response)
        } catch (e: Exception) {
            Result.Error(Exception("Download failed: ${e.message}", e))
        }
    }

    /**
     * Delete file from network and cache.
     */
    override suspend fun deleteFile(filePath: String): Result<Boolean> {
        return try {
            filesApi.deleteFile(filePath)
            fileDao.deleteFile(filePath)

            // Invalidate parent directory cache to force refresh
            val parentPath = filePath.substringBeforeLast('/', "")
            fileDao.deleteFilesInPath(parentPath)

            Result.Success(true)
        } catch (e: Exception) {
            Result.Error(Exception("Delete failed: ${e.message}", e))
        }
    }

    /**
     * Create new folder on server.
     */
    override suspend fun createFolder(path: String, name: String): Result<FileItem> {
        return try {
            val response = filesApi.createFolder(CreateFolderRequest(path, name))

            // Invalidate cache for parent directory
            fileDao.deleteFilesInPath(path)

            Result.Success(response.folder.toDomain())
        } catch (e: Exception) {
            Result.Error(Exception("Create folder failed: ${e.message}", e))
        }
    }

    /**
     * Move file or folder to new location.
     */
    override suspend fun moveFile(sourcePath: String, destinationPath: String): Result<FileItem> {
        return try {
            val response = filesApi.moveFile(MoveFileRequest(sourcePath, destinationPath))

            // Invalidate cache for both source and destination directories
            val sourceParent = sourcePath.substringBeforeLast('/', "")
            val destParent = destinationPath.substringBeforeLast('/', "")
            fileDao.deleteFilesInPath(sourceParent)
            if (sourceParent != destParent) {
                fileDao.deleteFilesInPath(destParent)
            }

            Result.Success(response.file.toDomain())
        } catch (e: Exception) {
            Result.Error(Exception("Move failed: ${e.message}", e))
        }
    }

    /**
     * Rename file or folder.
     */
    override suspend fun renameFile(path: String, newName: String): Result<FileItem> {
        return try {
            val response = filesApi.renameFile(RenameFileRequest(path, newName))

            // Invalidate cache for parent directory
            val parentPath = path.substringBeforeLast('/', "")
            fileDao.deleteFilesInPath(parentPath)

            Result.Success(response.file.toDomain())
        } catch (e: Exception) {
            Result.Error(Exception("Rename failed: ${e.message}", e))
        }
    }

    /**
     * Get file metadata from server.
     */
    override suspend fun getFileMetadata(path: String): Result<FileItem> {
        return try {
            val response = filesApi.getFileMetadata(path)
            Result.Success(response.file.toDomain())
        } catch (e: Exception) {
            Result.Error(Exception("Get metadata failed: ${e.message}", e))
        }
    }

    /**
     * Clear all cached data (e.g., on logout).
     */
    override suspend fun clearCache() {
        fileDao.deleteAll()
    }

    /**
     * Delete cache older than specified timestamp.
     */
    override suspend fun cleanOldCache(olderThan: Instant) {
        fileDao.deleteOldCache(olderThan.toEpochMilli())
    }
}

/**
 * Convert FileEntity to domain model FileItem.
 */
private fun FileEntity.toDomain() = FileItem(
    name = name,
    path = path,
    size = size,
    isDirectory = isDirectory,
    modifiedAt = modifiedAt,
    owner = owner,
    permissions = permissions,
    mimeType = mimeType
)

/**
 * Convert FileItemDto to domain model FileItem.
 */
private fun FileItemDto.toDomain() = FileItem(
    name = name,
    path = path,
    size = size,
    isDirectory = isDirectory,
    modifiedAt = Instant.parse(modifiedAt),
    owner = owner,
    permissions = permissions,
    mimeType = mimeType
)
