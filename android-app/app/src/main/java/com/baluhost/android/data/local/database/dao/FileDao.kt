package com.baluhost.android.data.local.database.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.baluhost.android.data.local.database.entities.FileEntity
import kotlinx.coroutines.flow.Flow

/**
 * DAO for file operations.
 */
@Dao
interface FileDao {
    
    @Query("SELECT * FROM files WHERE parent_path = :parentPath ORDER BY is_directory DESC, name ASC")
    fun getFilesByPath(parentPath: String): Flow<List<FileEntity>>
    
    @Query("SELECT * FROM files WHERE parent_path = :parentPath ORDER BY is_directory DESC, name ASC")
    suspend fun getFilesByPathSync(parentPath: String): List<FileEntity>
    
    @Query("SELECT * FROM files WHERE path = :path")
    suspend fun getFileByPath(path: String): FileEntity?
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertFile(file: FileEntity)
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertFiles(files: List<FileEntity>)
    
    @Query("DELETE FROM files WHERE path = :path")
    suspend fun deleteFile(path: String)
    
    @Query("DELETE FROM files WHERE parent_path = :parentPath")
    suspend fun deleteFilesInPath(parentPath: String)
    
    @Query("DELETE FROM files WHERE cached_at < :timestamp")
    suspend fun deleteOldCache(timestamp: Long)
    
    @Query("SELECT COUNT(*) FROM files")
    suspend fun getCacheFileCount(): Int
    
    @Query("DELETE FROM files WHERE path IN (SELECT path FROM files ORDER BY cached_at ASC LIMIT :limit)")
    suspend fun deleteOldestCacheFiles(limit: Int)
    
    @Query("SELECT MIN(cached_at) FROM files")
    suspend fun getOldestCacheTimestamp(): Long?
    
    @Query("SELECT MAX(cached_at) FROM files")
    suspend fun getNewestCacheTimestamp(): Long?
    
    @Query("DELETE FROM files")
    suspend fun deleteAll()
}
