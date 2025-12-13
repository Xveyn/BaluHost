package com.baluhost.android.data.repository

import com.baluhost.android.data.local.database.dao.FileDao
import com.baluhost.android.data.local.database.entities.FileEntity
import com.baluhost.android.data.remote.api.FilesApi
import com.baluhost.android.domain.model.FileItem
import com.baluhost.android.util.Result
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository for file operations with offline cache support.
 * 
 * Strategy:
 * - Cache-First: Try local cache first, then network
 * - Network requests update cache automatically
 * - Stale cache is refreshed after 5 minutes
 */
@Singleton
class FileRepository @Inject constructor(
    private val filesApi: FilesApi,
    private val fileDao: FileDao
) {
    
    companion object {
        private const val CACHE_VALIDITY_SECONDS = 300L  // 5 minutes
    }
    
    /**
     * Get files from cache or network.
     * Returns Flow that emits cached data immediately, then network data when available.
     */
    fun getFiles(path: String, forceRefresh: Boolean = false): Flow<List<FileItem>> {
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
    suspend fun refreshFiles(path: String): Result<List<FileItem>> {
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
     * Delete file from network and cache.
     */
    suspend fun deleteFile(filePath: String): Result<Boolean> {
        return try {
            filesApi.deleteFile(filePath)
            fileDao.deleteFile(filePath)
            Result.Success(true)
        } catch (e: Exception) {
            Result.Error(Exception("Delete failed: ${e.message}", e))
        }
    }
    
    /**
     * Clear all cached data (e.g., on logout).
     */
    suspend fun clearCache() {
        fileDao.deleteAll()
    }
    
    /**
     * Delete cache older than specified timestamp.
     */
    suspend fun cleanOldCache(olderThan: Instant = Instant.now().minusSeconds(7 * 24 * 60 * 60)) {
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
