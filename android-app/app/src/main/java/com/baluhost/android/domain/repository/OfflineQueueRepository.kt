package com.baluhost.android.domain.repository

import com.baluhost.android.domain.model.OperationStatus
import com.baluhost.android.domain.model.OperationType
import com.baluhost.android.domain.model.PendingOperation
import com.baluhost.android.util.Result
import kotlinx.coroutines.flow.Flow

/**
 * Repository for managing offline operations queue.
 */
interface OfflineQueueRepository {
    
    /**
     * Observe all pending operations.
     */
    fun getPendingOperations(): Flow<List<PendingOperation>>
    
    /**
     * Get count of pending operations.
     */
    fun getPendingCount(): Flow<Int>
    
    /**
     * Add operation to queue.
     */
    suspend fun queueOperation(
        operationType: OperationType,
        filePath: String,
        localFilePath: String? = null,
        destinationPath: String? = null,
        operationData: String? = null
    ): Result<Long>
    
    /**
     * Mark operation as completed.
     */
    suspend fun markAsCompleted(operationId: Long): Result<Unit>
    
    /**
     * Mark operation as failed with error message.
     */
    suspend fun markAsFailed(
        operationId: Long,
        errorMessage: String
    ): Result<Unit>
    
    /**
     * Update operation status.
     */
    suspend fun updateStatus(
        operationId: Long,
        status: OperationStatus
    ): Result<Unit>
    
    /**
     * Delete operation from queue.
     */
    suspend fun deleteOperation(operationId: Long): Result<Unit>
    
    /**
     * Delete completed operations older than specified days.
     */
    suspend fun cleanupOldOperations(daysOld: Int = 7): Result<Int>
    
    /**
     * Get operation by ID.
     */
    suspend fun getOperationById(operationId: Long): Result<PendingOperation?>
}
