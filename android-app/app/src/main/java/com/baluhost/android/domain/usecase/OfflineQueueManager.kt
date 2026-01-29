package com.baluhost.android.domain.usecase

import com.baluhost.android.data.network.NetworkMonitor
import com.baluhost.android.data.network.ServerConnectivityChecker
import com.baluhost.android.domain.model.OperationStatus
import com.baluhost.android.domain.model.OperationType
import com.baluhost.android.domain.model.PendingOperation
import com.baluhost.android.domain.repository.OfflineQueueRepository
import com.baluhost.android.domain.usecase.files.DeleteFileUseCase
import com.baluhost.android.domain.usecase.files.UploadFileUseCase
import com.baluhost.android.domain.util.Logger
import com.baluhost.android.util.Result
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.min
import kotlin.math.pow

/**
 * Manages offline operation queue and automatic retry with exponential backoff.
 *
 * Features:
 * - Queue operations when offline
 * - Automatic retry on server reconnect (not just network)
 * - Exponential backoff for failed retries
 * - Manual retry support
 * - Operation cancellation
 * - Automatic cleanup of old operations
 * - CRDT-based conflict resolution for concurrent updates
 */
@Singleton
class OfflineQueueManager @Inject constructor(
    private val offlineQueueRepository: OfflineQueueRepository,
    private val uploadFileUseCase: UploadFileUseCase,
    private val deleteFileUseCase: DeleteFileUseCase,
    private val networkMonitor: NetworkMonitor,
    private val serverConnectivityChecker: ServerConnectivityChecker,
    private val logger: Logger
) {
    companion object {
        private const val TAG = "OfflineQueueManager"
        private const val BASE_DELAY_MS = 1000L // 1 second
        private const val MAX_DELAY_MS = 60_000L // 1 minute
        private const val MAX_RETRIES = 5
    }
    
    private val scope = CoroutineScope(SupervisorJob())
    
    init {
        // Observe SERVER connectivity (not just network) and retry pending operations
        scope.launch {
            serverConnectivityChecker.isServerReachable.collect { isReachable ->
                if (isReachable) {
                    logger.debug(TAG, "Server connected, retrying pending operations")
                    retryPendingOperations()
                }
            }
        }
    }
    
    /**
     * Observe pending operations count for UI badge.
     */
    fun observePendingCount(): Flow<Int> {
        return offlineQueueRepository.getPendingCount()
    }
    
    /**
     * Observe all pending operations.
     */
    fun observePendingOperations(): Flow<List<PendingOperation>> {
        return offlineQueueRepository.getPendingOperations()
    }
    
    /**
     * Queue a file upload operation.
     */
    suspend fun queueUpload(
        localFile: File,
        destinationPath: String
    ): Result<Long> {
        logger.debug(TAG, "Queueing upload: ${localFile.name} -> $destinationPath")
        return offlineQueueRepository.queueOperation(
            operationType = OperationType.UPLOAD,
            filePath = destinationPath,
            localFilePath = localFile.absolutePath
        )
    }
    
    /**
     * Queue a file delete operation.
     */
    suspend fun queueDelete(filePath: String): Result<Long> {
        logger.debug(TAG, "Queueing delete: $filePath")
        return offlineQueueRepository.queueOperation(
            operationType = OperationType.DELETE,
            filePath = filePath
        )
    }
    
    /**
     * Queue a file rename operation.
     */
    suspend fun queueRename(
        oldPath: String,
        newName: String
    ): Result<Long> {
        logger.debug(TAG, "Queueing rename: $oldPath -> $newName")
        return offlineQueueRepository.queueOperation(
            operationType = OperationType.RENAME,
            filePath = oldPath,
            destinationPath = newName
        )
    }
    
    /**
     * Queue a file move operation.
     */
    suspend fun queueMove(
        sourcePath: String,
        destinationPath: String
    ): Result<Long> {
        logger.debug(TAG, "Queueing move: $sourcePath -> $destinationPath")
        return offlineQueueRepository.queueOperation(
            operationType = OperationType.MOVE,
            filePath = sourcePath,
            destinationPath = destinationPath
        )
    }
    
    /**
     * Queue a folder creation operation.
     */
    suspend fun queueCreateFolder(folderPath: String): Result<Long> {
        logger.debug(TAG, "Queueing folder creation: $folderPath")
        return offlineQueueRepository.queueOperation(
            operationType = OperationType.CREATE_FOLDER,
            filePath = folderPath
        )
    }
    
    /**
     * Retry all pending operations with exponential backoff.
     * Called automatically when server reconnects.
     */
    suspend fun retryPendingOperations() {
        if (!networkMonitor.isCurrentlyOnline() || !serverConnectivityChecker.isCurrentlyReachable()) {
            logger.debug(TAG, "Server not reachable, skipping retry")
            return
        }
        
        val pendingOperations = offlineQueueRepository.getPendingOperations().first()
        
        if (pendingOperations.isEmpty()) {
            logger.debug(TAG, "No pending operations to retry")
            return
        }
        
        logger.debug(TAG, "Retrying ${pendingOperations.size} pending operations")
        
        pendingOperations.forEach { operation ->
            if (operation.retryCount >= MAX_RETRIES) {
                logger.warn(TAG, "Operation ${operation.id} exceeded max retries ($MAX_RETRIES), skipping")
                return@forEach
            }
            
            // Exponential backoff: wait longer between retries
            val delayMs = calculateBackoffDelay(operation.retryCount)
            if (delayMs > 0) {
                logger.debug(TAG, "Waiting ${delayMs}ms before retry (attempt ${operation.retryCount + 1})")
                delay(delayMs)
            }
            
            retryOperation(operation)
        }
    }
    
    /**
     * Calculate exponential backoff delay.
     * Formula: min(BASE_DELAY * 2^retryCount, MAX_DELAY)
     */
    private fun calculateBackoffDelay(retryCount: Int): Long {
        if (retryCount == 0) return 0L
        val exponentialDelay = BASE_DELAY_MS * (2.0.pow(retryCount.toDouble())).toLong()
        return min(exponentialDelay, MAX_DELAY_MS)
    }
    
    /**
     * Retry a specific operation with server connectivity check.
     */
    suspend fun retryOperation(operation: PendingOperation) {
        if (!networkMonitor.isCurrentlyOnline() || !serverConnectivityChecker.isCurrentlyReachable()) {
            logger.debug(TAG, "Server not reachable, cannot retry operation ${operation.id}")
            return
        }
        
        logger.debug(TAG, "Retrying operation ${operation.id}: ${operation.operationType} (attempt ${operation.retryCount + 1}/$MAX_RETRIES)")
        
        // Update status to RETRYING
        offlineQueueRepository.updateStatus(operation.id, OperationStatus.RETRYING)
        
        val result = when (operation.operationType) {
            OperationType.UPLOAD -> retryUpload(operation)
            OperationType.DELETE -> retryDelete(operation)
            OperationType.RENAME -> {
                // TODO: Implement rename use case
                Result.Error(Exception("Rename not yet implemented"))
            }
            OperationType.CREATE_FOLDER -> {
                // TODO: Implement create folder use case
                Result.Error(Exception("Create folder not yet implemented"))
            }
            OperationType.MOVE -> {
                // TODO: Implement move use case
                Result.Error(Exception("Move not yet implemented"))
            }
        }
        
        when (result) {
            is Result.Success -> {
                logger.debug(TAG, "Operation ${operation.id} succeeded after ${operation.retryCount + 1} retries")
                offlineQueueRepository.markAsCompleted(operation.id)
            }
            is Result.Error -> {
                val errorMsg = result.exception.message ?: "Unknown error"
                logger.error(TAG, "Operation ${operation.id} failed (attempt ${operation.retryCount + 1}): $errorMsg")
                
                // Check if we should retry or mark as permanently failed
                if (operation.retryCount + 1 >= MAX_RETRIES) {
                    logger.error(TAG, "Operation ${operation.id} permanently failed after $MAX_RETRIES retries")
                    offlineQueueRepository.markAsFailed(operation.id, "Max retries exceeded: $errorMsg")
                } else {
                    // Increment retry count and keep in queue
                    offlineQueueRepository.markAsFailed(operation.id, errorMsg)
                }
            }
            is Result.Loading -> {
                // Operation in progress
            }
        }
    }
    
    private suspend fun retryUpload(operation: PendingOperation): Result<Unit> {
        val localFilePath = operation.localFilePath
            ?: return Result.Error(Exception("Missing local file path"))
        
        val localFile = File(localFilePath)
        if (!localFile.exists()) {
            return Result.Error(Exception("Local file not found: $localFilePath"))
        }
        
        return when (val result = uploadFileUseCase(localFile, operation.filePath)) {
            is Result.Success -> Result.Success(Unit)
            is Result.Error -> Result.Error(result.exception)
            is Result.Loading -> Result.Loading
        }
    }
    
    private suspend fun retryDelete(operation: PendingOperation): Result<Unit> {
        return when (val result = deleteFileUseCase(operation.filePath)) {
            is Result.Success -> Result.Success(Unit)
            is Result.Error -> Result.Error(result.exception)
            is Result.Loading -> Result.Loading
        }
    }
    
    /**
     * Cancel a pending operation.
     */
    suspend fun cancelOperation(operationId: Long): Result<Unit> {
        logger.debug(TAG, "Cancelling operation $operationId")
        return offlineQueueRepository.deleteOperation(operationId)
    }
    
    /**
     * Cleanup old completed operations.
     */
    suspend fun cleanupOldOperations(daysOld: Int = 7): Result<Int> {
        logger.debug(TAG, "Cleaning up operations older than $daysOld days")
        return offlineQueueRepository.cleanupOldOperations(daysOld)
    }
    
    // ==================== CRDT Support ====================
    
    /**
     * Apply CRDT merge for file metadata updates.
     * This ensures concurrent updates from multiple devices don't conflict.
     * 
     * Use case:
     * - User edits file on Phone while offline
     * - User edits same file on Desktop while offline
     * - Both devices come online
     * - CRDT merge resolves conflict automatically (latest version wins)
     */
    fun mergeCRDTUpdates(
        localVersion: Long,
        localDeviceId: String,
        remoteVersion: Long,
        remoteDeviceId: String
    ): Pair<Long, String> {
        return when {
            // Remote is newer
            remoteVersion > localVersion -> Pair(remoteVersion, remoteDeviceId)
            
            // Local is newer
            localVersion > remoteVersion -> Pair(localVersion, localDeviceId)
            
            // Same version - use device ID as tiebreaker (alphabetically later wins)
            else -> {
                if (remoteDeviceId > localDeviceId) {
                    Pair(remoteVersion, remoteDeviceId)
                } else {
                    Pair(localVersion, localDeviceId)
                }
            }
        }
    }
    
    /**
     * Check if local change should be applied over remote.
     * Returns true if local is newer or equal (with higher device ID).
     */
    fun shouldApplyLocalChange(
        localVersion: Long,
        localDeviceId: String,
        remoteVersion: Long,
        remoteDeviceId: String
    ): Boolean {
        val (winningVersion, winningDevice) = mergeCRDTUpdates(
            localVersion, localDeviceId,
            remoteVersion, remoteDeviceId
        )
        return winningVersion == localVersion && winningDevice == localDeviceId
    }
}
