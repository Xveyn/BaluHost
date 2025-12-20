package com.baluhost.android.data.worker

import android.content.Context
import androidx.work.*
import java.util.concurrent.TimeUnit

/**
 * WorkManager scheduler for offline queue workers.
 */
object OfflineQueueWorkScheduler {
    
    /**
     * Schedule periodic retry worker.
     * Runs every 15 minutes when device is idle.
     */
    fun schedulePeriodicRetry(context: Context) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        
        val retryWork = PeriodicWorkRequestBuilder<OfflineQueueRetryWorker>(
            repeatInterval = 15,
            repeatIntervalTimeUnit = TimeUnit.MINUTES
        )
            .setConstraints(constraints)
            .setBackoffCriteria(
                BackoffPolicy.EXPONENTIAL,
                WorkRequest.MIN_BACKOFF_MILLIS,
                TimeUnit.MILLISECONDS
            )
            .build()
        
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            OfflineQueueRetryWorker.WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            retryWork
        )
    }
    
    /**
     * Schedule daily cleanup worker.
     * Runs once per day to remove old completed operations.
     */
    fun scheduleDailyCleanup(context: Context) {
        val cleanupWork = PeriodicWorkRequestBuilder<OfflineQueueCleanupWorker>(
            repeatInterval = 1,
            repeatIntervalTimeUnit = TimeUnit.DAYS
        )
            .setBackoffCriteria(
                BackoffPolicy.LINEAR,
                WorkRequest.MIN_BACKOFF_MILLIS,
                TimeUnit.MILLISECONDS
            )
            .setInputData(
                workDataOf("days_old" to 7)
            )
            .build()
        
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            OfflineQueueCleanupWorker.WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            cleanupWork
        )
    }
    
    /**
     * Trigger immediate retry (e.g., on network reconnect).
     */
    fun triggerImmediateRetry(context: Context) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        
        val retryWork = OneTimeWorkRequestBuilder<OfflineQueueRetryWorker>()
            .setConstraints(constraints)
            .build()
        
        WorkManager.getInstance(context).enqueue(retryWork)
    }
    
    /**
     * Schedule daily cache cleanup worker.
     * Runs once per day to clean old cached files (LRU + age-based).
     */
    fun scheduleCacheCleanup(
        context: Context,
        maxFiles: Int = CacheCleanupWorker.MAX_CACHE_FILES,
        maxAgeDays: Int = CacheCleanupWorker.MAX_CACHE_AGE_DAYS
    ) {
        val constraints = Constraints.Builder()
            .setRequiresDeviceIdle(true)  // Run when device is idle
            .setRequiresCharging(false)   // Can run on battery
            .build()
        
        val cacheCleanupWork = PeriodicWorkRequestBuilder<CacheCleanupWorker>(
            repeatInterval = 1,
            repeatIntervalTimeUnit = TimeUnit.DAYS
        )
            .setConstraints(constraints)
            // Cannot use backoffCriteria with idle mode job
            .setInputData(
                workDataOf(
                    CacheCleanupWorker.KEY_MAX_FILES to maxFiles,
                    CacheCleanupWorker.KEY_MAX_AGE_DAYS to maxAgeDays
                )
            )
            .build()
        
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            CacheCleanupWorker.WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            cacheCleanupWork
        )
    }
    
    /**
     * Trigger immediate cache cleanup.
     */
    fun triggerImmediateCacheCleanup(
        context: Context,
        maxFiles: Int = CacheCleanupWorker.MAX_CACHE_FILES,
        maxAgeDays: Int = CacheCleanupWorker.MAX_CACHE_AGE_DAYS
    ) {
        val cacheCleanupWork = OneTimeWorkRequestBuilder<CacheCleanupWorker>()
            .setInputData(
                workDataOf(
                    CacheCleanupWorker.KEY_MAX_FILES to maxFiles,
                    CacheCleanupWorker.KEY_MAX_AGE_DAYS to maxAgeDays
                )
            )
            .build()
        
        WorkManager.getInstance(context).enqueue(cacheCleanupWork)
    }
    
    /**
     * Cancel all scheduled workers.
     */
    fun cancelAll(context: Context) {
        WorkManager.getInstance(context).apply {
            cancelUniqueWork(OfflineQueueRetryWorker.WORK_NAME)
            cancelUniqueWork(OfflineQueueCleanupWorker.WORK_NAME)
        }
    }
}
