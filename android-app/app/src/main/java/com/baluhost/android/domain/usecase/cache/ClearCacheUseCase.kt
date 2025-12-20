package com.baluhost.android.domain.usecase.cache

import android.content.Context
import com.baluhost.android.data.worker.OfflineQueueWorkScheduler
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject

/**
 * Use case for manually triggering cache cleanup.
 */
class ClearCacheUseCase @Inject constructor(
    @ApplicationContext private val context: Context
) {
    
    operator fun invoke(
        maxFiles: Int? = null,
        maxAgeDays: Int? = null
    ) {
        OfflineQueueWorkScheduler.triggerImmediateCacheCleanup(
            context = context,
            maxFiles = maxFiles ?: com.baluhost.android.data.worker.CacheCleanupWorker.MAX_CACHE_FILES,
            maxAgeDays = maxAgeDays ?: com.baluhost.android.data.worker.CacheCleanupWorker.MAX_CACHE_AGE_DAYS
        )
    }
}
