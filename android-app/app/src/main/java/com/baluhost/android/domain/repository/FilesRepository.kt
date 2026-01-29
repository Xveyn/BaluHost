package com.baluhost.android.domain.repository

import com.baluhost.android.domain.model.FileItem
import com.baluhost.android.util.Result
import kotlinx.coroutines.flow.Flow
import okhttp3.ResponseBody
import java.io.File
import java.time.Instant

/**
 * Repository interface for file operations.
 *
 * Provides file management capabilities with offline caching support.
 */
interface FilesRepository {

    /**
     * Get files from cache or network.
     * Returns Flow that emits cached data immediately, then network data when available.
     *
     * @param path Directory path to list files from
     * @param forceRefresh Force refresh from network even if cache is valid
     * @return Flow of file lists
     */
    fun getFiles(path: String, forceRefresh: Boolean = false): Flow<List<FileItem>>

    /**
     * Fetch files from network and update cache.
     *
     * @param path Directory path to refresh
     * @return Result with list of files or error
     */
    suspend fun refreshFiles(path: String): Result<List<FileItem>>

    /**
     * Upload file to server.
     *
     * @param file Local file to upload
     * @param destinationPath Destination path on server
     * @return Result with uploaded file metadata or error
     */
    suspend fun uploadFile(file: File, destinationPath: String): Result<Unit>

    /**
     * Download file from server.
     *
     * @param filePath File path on server
     * @return Result with ResponseBody for streaming or error
     */
    suspend fun downloadFile(filePath: String): Result<ResponseBody>

    /**
     * Delete file from server and cache.
     *
     * @param filePath File path to delete
     * @return Result with success status or error
     */
    suspend fun deleteFile(filePath: String): Result<Boolean>

    /**
     * Create new folder on server.
     *
     * @param path Parent directory path
     * @param name Folder name
     * @return Result with created folder metadata or error
     */
    suspend fun createFolder(path: String, name: String): Result<FileItem>

    /**
     * Move file or folder to new location.
     *
     * @param sourcePath Current file path
     * @param destinationPath New file path
     * @return Result with moved file metadata or error
     */
    suspend fun moveFile(sourcePath: String, destinationPath: String): Result<FileItem>

    /**
     * Rename file or folder.
     *
     * @param path Current file path
     * @param newName New file name
     * @return Result with renamed file metadata or error
     */
    suspend fun renameFile(path: String, newName: String): Result<FileItem>

    /**
     * Get file metadata from server.
     *
     * @param path File path
     * @return Result with file metadata or error
     */
    suspend fun getFileMetadata(path: String): Result<FileItem>

    /**
     * Clear all cached files (e.g., on logout).
     */
    suspend fun clearCache()

    /**
     * Delete cached files older than specified timestamp.
     *
     * @param olderThan Instant timestamp (default: 7 days ago)
     */
    suspend fun cleanOldCache(olderThan: Instant = Instant.now().minusSeconds(7 * 24 * 60 * 60))
}
