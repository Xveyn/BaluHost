package com.baluhost.android.data.repository

import android.util.Log
import com.baluhost.android.data.local.database.dao.PendingOperationDao
import com.baluhost.android.data.local.database.entities.OperationStatus as EntityOperationStatus
import com.baluhost.android.data.local.database.mappers.toDomain
import com.baluhost.android.data.local.database.mappers.toEntity
import com.baluhost.android.domain.model.OperationStatus
import com.baluhost.android.domain.model.OperationType
import com.baluhost.android.domain.model.PendingOperation
import com.baluhost.android.domain.repository.OfflineQueueRepository
import com.baluhost.android.util.Result
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.time.Instant
import javax.inject.Inject

/**
 * Implementation of OfflineQueueRepository using Room database.
 */
class OfflineQueueRepositoryImpl @Inject constructor(
    private val pendingOperationDao: PendingOperationDao
) : OfflineQueueRepository {
    
    companion object {
        private const val TAG = "OfflineQueueRepo"
    }
    
    override fun getPendingOperations(): Flow<List<PendingOperation>> {
        return pendingOperationDao.getPendingOperations()
            .map { entities -> entities.toDomain() }
    }
    
    override fun getPendingCount(): Flow<Int> {
        return pendingOperationDao.getPendingCount()
    }
    
    override suspend fun queueOperation(
        operationType: OperationType,
        filePath: String,
        localFilePath: String?,
        destinationPath: String?,
        operationData: String?
    ): Result<Long> {
        return try {
            val operation = PendingOperation(
                operationType = operationType,
                filePath = filePath,
                localFilePath = localFilePath,
                destinationPath = destinationPath,
                operationData = operationData,
                status = OperationStatus.PENDING,
                createdAt = Instant.now()
            )
            
            val id = pendingOperationDao.insertOperation(operation.toEntity())
            Log.d(TAG, "Queued operation: $operationType for $filePath (ID: $id)")
            Result.Success(id)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to queue operation", e)
            Result.Error(e)
        }
    }
    
    override suspend fun markAsCompleted(operationId: Long): Result<Unit> {
        return try {
            pendingOperationDao.markAsCompleted(
                id = operationId,
                timestamp = Instant.now()
            )
            Log.d(TAG, "Marked operation $operationId as completed")
            Result.Success(Unit)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to mark operation as completed", e)
            Result.Error(e)
        }
    }
    
    override suspend fun markAsFailed(
        operationId: Long,
        errorMessage: String
    ): Result<Unit> {
        return try {
            pendingOperationDao.markAsFailed(
                id = operationId,
                status = EntityOperationStatus.FAILED,
                errorMessage = errorMessage,
                timestamp = Instant.now()
            )
            Log.d(TAG, "Marked operation $operationId as failed: $errorMessage")
            Result.Success(Unit)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to mark operation as failed", e)
            Result.Error(e)
        }
    }
    
    override suspend fun updateStatus(
        operationId: Long,
        status: OperationStatus
    ): Result<Unit> {
        return try {
            pendingOperationDao.updateStatus(
                id = operationId,
                status = status.name
            )
            Log.d(TAG, "Updated operation $operationId status to $status")
            Result.Success(Unit)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to update operation status", e)
            Result.Error(e)
        }
    }
    
    override suspend fun deleteOperation(operationId: Long): Result<Unit> {
        return try {
            pendingOperationDao.deleteOperation(operationId)
            Log.d(TAG, "Deleted operation $operationId")
            Result.Success(Unit)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to delete operation", e)
            Result.Error(e)
        }
    }
    
    override suspend fun cleanupOldOperations(daysOld: Int): Result<Int> {
        return try {
            val cutoffTime = Instant.now().minusSeconds(daysOld * 24L * 60L * 60L)
            val deletedCount = pendingOperationDao.deleteCompletedBefore(cutoffTime)
            Log.d(TAG, "Cleaned up $deletedCount old operations")
            Result.Success(deletedCount)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to cleanup old operations", e)
            Result.Error(e)
        }
    }
    
    override suspend fun getOperationById(operationId: Long): Result<PendingOperation?> {
        return try {
            val entity = pendingOperationDao.getOperationById(operationId)
            Result.Success(entity?.toDomain())
        } catch (e: Exception) {
            Log.e(TAG, "Failed to get operation by ID", e)
            Result.Error(e)
        }
    }
}
