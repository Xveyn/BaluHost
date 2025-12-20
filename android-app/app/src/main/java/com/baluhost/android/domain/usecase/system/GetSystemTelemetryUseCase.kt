package com.baluhost.android.domain.usecase.system

import com.baluhost.android.data.remote.api.SystemApi
import com.baluhost.android.domain.model.SystemInfo
import com.baluhost.android.util.Result
import javax.inject.Inject

/**
 * UseCase to get system telemetry data (CPU, Memory, Storage, Uptime).
 */
class GetSystemTelemetryUseCase @Inject constructor(
    private val systemApi: SystemApi
) {
    suspend operator fun invoke(): Result<SystemInfo> {
        return try {
            // Get system info - already returns domain model
            val systemInfo = systemApi.getSystemInfo()
            
            // Map DTO to domain model
            val domainModel = SystemInfo(
                cpu = com.baluhost.android.domain.model.CpuStats(
                    usagePercent = systemInfo.cpu.usage,
                    cores = systemInfo.cpu.cores,
                    frequencyMhz = systemInfo.cpu.frequencyMhz
                ),
                memory = com.baluhost.android.domain.model.MemoryStats(
                    totalBytes = systemInfo.memory.total,
                    usedBytes = systemInfo.memory.used,
                    availableBytes = systemInfo.memory.free,
                    usagePercent = if (systemInfo.memory.total > 0) {
                        (systemInfo.memory.used.toDouble() / systemInfo.memory.total.toDouble()) * 100.0
                    } else 0.0
                ),
                disk = com.baluhost.android.domain.model.DiskStats(
                    totalBytes = systemInfo.disk.total,
                    usedBytes = systemInfo.disk.used,
                    availableBytes = systemInfo.disk.free,
                    usagePercent = if (systemInfo.disk.total > 0) {
                        (systemInfo.disk.used.toDouble() / systemInfo.disk.total.toDouble()) * 100.0
                    } else 0.0
                ),
                uptime = systemInfo.uptime,
                devMode = systemInfo.devMode
            )
            
            Result.Success(domainModel)
        } catch (e: Exception) {
            Result.Error(e)
        }
    }
}
