package com.baluhost.android.data.worker

import android.content.Context
import android.util.Log
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.baluhost.android.domain.usecase.OfflineQueueManager
import com.baluhost.android.util.Result
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject

/**
 * Background worker for cleaning up old completed operations.
 * 
 * Scheduled daily to keep database clean.
 */
@HiltWorker
class OfflineQueueCleanupWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted workerParams: WorkerParameters,
    private val offlineQueueManager: OfflineQueueManager
) : CoroutineWorker(appContext, workerParams) {
    
    companion object {
        const val TAG = "OfflineQueueCleanupWorker"
        const val WORK_NAME = "offline_queue_cleanup"
        const val DAYS_OLD_DEFAULT = 7
    }
    
    override suspend fun doWork(): Result {
        Log.d(TAG, "Starting offline queue cleanup worker")
        
        val daysOld = inputData.getInt("days_old", DAYS_OLD_DEFAULT)
        
        return try {
            when (val result = offlineQueueManager.cleanupOldOperations(daysOld)) {
                is com.baluhost.android.util.Result.Success -> {
                    Log.d(TAG, "Cleaned up ${result.data} old operations")
                    Result.success()
                }
                is com.baluhost.android.util.Result.Error -> {
                    Log.e(TAG, "Failed to cleanup operations", result.exception)
                    Result.failure()
                }
                is com.baluhost.android.util.Result.Loading -> {
                    Result.retry()
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to cleanup operations", e)
            Result.failure()
        }
    }
}
