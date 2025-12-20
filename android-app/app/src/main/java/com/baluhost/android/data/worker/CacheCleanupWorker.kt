package com.baluhost.android.data.worker

import android.content.Context
import android.util.Log
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.baluhost.android.data.local.database.dao.FileDao
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.time.Instant

/**
 * Background worker for cleaning up file cache.
 * 
 * Cleanup strategies:
 * 1. LRU Eviction: Delete oldest cached files if count exceeds MAX_CACHE_FILES
 * 2. Age-based: Delete files older than MAX_CACHE_AGE_DAYS
 * 
 * Scheduled daily to keep cache size manageable.
 */
@HiltWorker
class CacheCleanupWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted workerParams: WorkerParameters,
    private val fileDao: FileDao
) : CoroutineWorker(appContext, workerParams) {
    
    companion object {
        const val TAG = "CacheCleanupWorker"
        const val WORK_NAME = "cache_cleanup"
        
        // Cleanup parameters
        const val MAX_CACHE_FILES = 1000
        const val MAX_CACHE_AGE_DAYS = 7
        
        // Input data keys
        const val KEY_MAX_FILES = "max_files"
        const val KEY_MAX_AGE_DAYS = "max_age_days"
    }
    
    override suspend fun doWork(): Result {
        Log.d(TAG, "Starting cache cleanup worker")
        
        val maxFiles = inputData.getInt(KEY_MAX_FILES, MAX_CACHE_FILES)
        val maxAgeDays = inputData.getInt(KEY_MAX_AGE_DAYS, MAX_CACHE_AGE_DAYS)
        
        return try {
            var deletedCount = 0
            
            // 1. Age-based cleanup: Delete files older than maxAgeDays
            val maxAgeTimestamp = Instant.now()
                .minusSeconds(maxAgeDays * 24L * 60 * 60)
                .toEpochMilli()
            
            Log.d(TAG, "Deleting cache older than $maxAgeDays days (timestamp: $maxAgeTimestamp)")
            fileDao.deleteOldCache(maxAgeTimestamp)
            
            // 2. LRU Eviction: Check if cache exceeds max file count
            val currentCount = fileDao.getCacheFileCount()
            Log.d(TAG, "Current cache file count: $currentCount (max: $maxFiles)")
            
            if (currentCount > maxFiles) {
                val excessCount = currentCount - maxFiles
                Log.d(TAG, "Cache exceeds limit by $excessCount files, performing LRU eviction")
                
                // Delete oldest files beyond the limit
                fileDao.deleteOldestCacheFiles(excessCount)
                deletedCount += excessCount
            }
            
            Log.d(TAG, "Cache cleanup completed. Deleted $deletedCount files")
            Result.success()
            
        } catch (e: Exception) {
            Log.e(TAG, "Cache cleanup failed", e)
            Result.failure()
        }
    }
}
