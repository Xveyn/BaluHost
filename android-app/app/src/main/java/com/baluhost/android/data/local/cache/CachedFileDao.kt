package com.baluhost.android.data.local.cache

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

/**
 * Cached file metadata for offline viewing.
 * Stores only file structure (names, icons, paths), not actual file content.
 */
@Entity(tableName = "cached_files")
data class CachedFileEntity(
    @PrimaryKey
    val path: String,  // Full file path (unique identifier)
    
    val name: String,
    val isDirectory: Boolean,
    val size: Long,
    val mimeType: String?,
    val parentPath: String,  // Parent directory path
    
    // Metadata
    val lastModified: Long,
    val cachedAt: Long = System.currentTimeMillis(),
    
    // Download status
    val isDownloaded: Boolean = false,  // True if actual file content is available locally
    val localFilePath: String? = null    // Path to downloaded file (if isDownloaded)
)

@Dao
interface CachedFileDao {
    
    /**
     * Get all cached files in a directory.
     */
    @Query("SELECT * FROM cached_files WHERE parentPath = :path ORDER BY isDirectory DESC, name ASC")
    fun getCachedFiles(path: String): Flow<List<CachedFileEntity>>
    
    /**
     * Get cached files synchronously (for offline use).
     */
    @Query("SELECT * FROM cached_files WHERE parentPath = :path ORDER BY isDirectory DESC, name ASC")
    suspend fun getCachedFilesSync(path: String): List<CachedFileEntity>
    
    /**
     * Cache file metadata.
     */
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun cacheFiles(files: List<CachedFileEntity>)
    
    /**
     * Mark file as downloaded (actual content available).
     */
    @Query("UPDATE cached_files SET isDownloaded = :isDownloaded, localFilePath = :localPath WHERE path = :filePath")
    suspend fun markAsDownloaded(filePath: String, isDownloaded: Boolean, localPath: String?)
    
    /**
     * Delete cached file metadata.
     */
    @Query("DELETE FROM cached_files WHERE path = :path")
    suspend fun deleteCachedFile(path: String)
    
    /**
     * Delete all cached files in a directory.
     */
    @Query("DELETE FROM cached_files WHERE parentPath = :path")
    suspend fun deleteCachedFilesInDirectory(path: String)
    
    /**
     * Clear old cache (older than specified time).
     */
    @Query("DELETE FROM cached_files WHERE cachedAt < :timestamp AND isDownloaded = 0")
    suspend fun clearOldCache(timestamp: Long)
    
    /**
     * Get all downloaded files.
     */
    @Query("SELECT * FROM cached_files WHERE isDownloaded = 1")
    suspend fun getDownloadedFiles(): List<CachedFileEntity>
    
    /**
     * Clear all cache.
     */
    @Query("DELETE FROM cached_files")
    suspend fun clearAllCache()
}
