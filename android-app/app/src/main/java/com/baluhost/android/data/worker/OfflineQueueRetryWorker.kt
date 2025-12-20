package com.baluhost.android.data.worker

import android.content.Context
import android.util.Log
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.baluhost.android.domain.usecase.OfflineQueueManager
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject

/**
 * Background worker for retrying pending operations.
 * 
 * Scheduled periodically or when network reconnects.
 * Uses Hilt for dependency injection.
 */
@HiltWorker
class OfflineQueueRetryWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted workerParams: WorkerParameters,
    private val offlineQueueManager: OfflineQueueManager
) : CoroutineWorker(appContext, workerParams) {
    
    companion object {
        const val TAG = "OfflineQueueRetryWorker"
        const val WORK_NAME = "offline_queue_retry"
    }
    
    override suspend fun doWork(): Result {
        Log.d(TAG, "Starting offline queue retry worker")
        
        return try {
            // Retry all pending operations
            offlineQueueManager.retryPendingOperations()
            
            Log.d(TAG, "Offline queue retry completed successfully")
            Result.success()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to retry pending operations", e)
            
            if (runAttemptCount < 3) {
                Result.retry()
            } else {
                Result.failure()
            }
        }
    }
}
