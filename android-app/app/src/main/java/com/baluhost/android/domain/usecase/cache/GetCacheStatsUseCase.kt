package com.baluhost.android.domain.usecase.cache

import com.baluhost.android.data.local.database.dao.FileDao
import java.time.Instant
import javax.inject.Inject

/**
 * Use case for getting cache statistics.
 */
class GetCacheStatsUseCase @Inject constructor(
    private val fileDao: FileDao
) {
    
    data class CacheStats(
        val fileCount: Int,
        val oldestFileAge: Long? = null,  // Age in milliseconds
        val newestFileAge: Long? = null   // Age in milliseconds
    )
    
    suspend operator fun invoke(): CacheStats {
        val fileCount = fileDao.getCacheFileCount()
        
        // Get oldest and newest cache timestamps
        val oldestTimestamp = fileDao.getOldestCacheTimestamp()
        val newestTimestamp = fileDao.getNewestCacheTimestamp()
        
        val now = Instant.now().toEpochMilli()
        
        return CacheStats(
            fileCount = fileCount,
            oldestFileAge = oldestTimestamp?.let { now - it },
            newestFileAge = newestTimestamp?.let { now - it }
        )
    }
}
