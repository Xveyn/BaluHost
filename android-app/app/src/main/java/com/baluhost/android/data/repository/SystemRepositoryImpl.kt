package com.baluhost.android.data.repository

import com.baluhost.android.data.remote.api.SystemApi
import com.baluhost.android.data.remote.dto.*
import com.baluhost.android.domain.model.*
import com.baluhost.android.domain.repository.SystemRepository
import javax.inject.Inject

/**
 * Implementation of SystemRepository.
 * Handles API calls and DTO to domain model mapping.
 */
class SystemRepositoryImpl @Inject constructor(
    private val systemApi: SystemApi
) : SystemRepository {
    
    override suspend fun getSystemInfo(): Result<SystemInfo> {
        return try {
            val dto = systemApi.getSystemInfo()
            Result.success(dto.toDomain())
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    override suspend fun getRaidStatus(): Result<List<RaidArray>> {
        return try {
            val dto = systemApi.getRaidStatus()
            Result.success(dto.arrays.map { it.toDomain() })
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    override suspend fun getAvailableDisks(): Result<List<StorageDisk>> {
        return try {
            val dto = systemApi.getAvailableDisks()
            Result.success(dto.disks.map { it.toDomain() })
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}

/**
 * Extension functions to map DTOs to domain models.
 */

private fun SystemInfoDto.toDomain() = SystemInfo(
    cpu = cpu.toDomain(),
    memory = memory.toDomain(),
    disk = disk.toDomain(),
    uptime = uptime,
    devMode = devMode
)

private fun CpuStatsDto.toDomain() = CpuStats(
    usagePercent = usagePercent,
    cores = cores,
    frequencyMhz = frequencyMhz
)

private fun MemoryStatsDto.toDomain() = MemoryStats(
    totalBytes = totalBytes,
    usedBytes = usedBytes,
    availableBytes = availableBytes,
    usagePercent = usagePercent
)

private fun DiskStatsDto.toDomain() = DiskStats(
    totalBytes = totalBytes,
    usedBytes = usedBytes,
    availableBytes = availableBytes,
    usagePercent = usagePercent
)

private fun RaidArrayDto.toDomain() = RaidArray(
    name = name,
    level = level,
    sizeBytes = sizeBytes,
    status = RaidStatus.fromString(status),
    devices = devices.map { it.toDomain() },
    resyncProgress = resyncProgress,
    bitmap = bitmap,
    syncAction = syncAction
)

private fun RaidDeviceDto.toDomain() = RaidDevice(
    name = name,
    state = RaidDeviceState.fromString(state)
)

private fun AvailableDiskDto.toDomain() = StorageDisk(
    name = name,
    sizeBytes = sizeBytes,
    model = model,
    isPartitioned = isPartitioned,
    partitions = partitions,
    inRaid = inRaid
)
