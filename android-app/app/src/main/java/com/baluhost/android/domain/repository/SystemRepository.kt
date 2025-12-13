package com.baluhost.android.domain.repository

import com.baluhost.android.domain.model.*

/**
 * Repository interface for system and storage operations.
 */
interface SystemRepository {
    
    /**
     * Get system information including CPU, memory, disk stats.
     */
    suspend fun getSystemInfo(): Result<SystemInfo>
    
    /**
     * Get RAID array status.
     */
    suspend fun getRaidStatus(): Result<List<RaidArray>>
    
    /**
     * Get list of available disks (admin only).
     */
    suspend fun getAvailableDisks(): Result<List<StorageDisk>>
}
