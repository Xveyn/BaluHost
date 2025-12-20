package com.baluhost.android.data.local.database.dao

import androidx.room.*
import com.baluhost.android.data.local.database.entities.PendingOperationEntity
import kotlinx.coroutines.flow.Flow
import java.time.Instant

/**
 * DAO for pending operations (offline queue).
 * Stores operations that failed due to network issues for retry.
 */
@Dao
interface PendingOperationDao {
    
    @Query("SELECT * FROM pending_operations WHERE status = 'PENDING' ORDER BY created_at ASC")
    fun getPendingOperations(): Flow<List<PendingOperationEntity>>
    
    @Query("SELECT * FROM pending_operations WHERE id = :id")
    suspend fun getOperationById(id: Long): PendingOperationEntity?
    
    @Query("SELECT * FROM pending_operations WHERE status = 'PENDING' ORDER BY created_at ASC")
    suspend fun getPendingOperationsList(): List<PendingOperationEntity>
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertOperation(operation: PendingOperationEntity): Long
    
    @Update
    suspend fun updateOperation(operation: PendingOperationEntity)
    
    @Query("UPDATE pending_operations SET status = :status WHERE id = :id")
    suspend fun updateStatus(id: Long, status: String)
    
    @Query("UPDATE pending_operations SET status = :status, error_message = :errorMessage, retry_count = retry_count + 1, last_retry_at = :timestamp WHERE id = :id")
    suspend fun markAsFailed(id: Long, status: String, errorMessage: String?, timestamp: Instant)
    
    @Query("UPDATE pending_operations SET status = 'COMPLETED', completed_at = :timestamp WHERE id = :id")
    suspend fun markAsCompleted(id: Long, timestamp: Instant)
    
    @Query("DELETE FROM pending_operations WHERE id = :id")
    suspend fun deleteOperation(id: Long)
    
    @Query("DELETE FROM pending_operations WHERE status = 'COMPLETED' AND completed_at < :cutoffTime")
    suspend fun deleteCompletedBefore(cutoffTime: Instant): Int
    
    @Query("SELECT COUNT(*) FROM pending_operations WHERE status = 'PENDING'")
    fun getPendingCount(): Flow<Int>
    
    @Query("SELECT COUNT(*) FROM pending_operations WHERE status = 'PENDING'")
    suspend fun getPendingCountSync(): Int
}
