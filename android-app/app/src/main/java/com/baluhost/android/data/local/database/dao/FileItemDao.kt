package com.baluhost.android.data.local.database.dao

import androidx.room.*
import com.baluhost.android.data.local.database.entity.FileItemEntity
import kotlinx.coroutines.flow.Flow

/**
 * DAO for file items cache.
 */
@Dao
interface FileItemDao {
    
    @Query("SELECT * FROM file_items WHERE parentPath = :path ORDER BY isDirectory DESC, name ASC")
    fun getFilesByPath(path: String): Flow<List<FileItemEntity>>
    
    @Query("SELECT * FROM file_items WHERE parentPath = :path ORDER BY isDirectory DESC, name ASC")
    suspend fun getFilesByPathSync(path: String): List<FileItemEntity>
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertFiles(files: List<FileItemEntity>)
    
    @Query("DELETE FROM file_items WHERE parentPath = :path")
    suspend fun deleteFilesByPath(path: String)
    
    @Query("DELETE FROM file_items WHERE path = :filePath")
    suspend fun deleteFile(filePath: String)
    
    @Query("DELETE FROM file_items WHERE cachedAt < :timestamp")
    suspend fun deleteOldCache(timestamp: Long)
    
    @Query("DELETE FROM file_items")
    suspend fun clearAll()
}
