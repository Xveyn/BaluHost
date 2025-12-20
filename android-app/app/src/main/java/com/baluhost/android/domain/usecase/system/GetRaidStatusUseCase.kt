package com.baluhost.android.domain.usecase.system

import com.baluhost.android.data.remote.api.SystemApi
import com.baluhost.android.domain.model.RaidArray
import com.baluhost.android.domain.model.RaidDevice
import com.baluhost.android.domain.model.RaidStatus
import com.baluhost.android.util.Result
import javax.inject.Inject

/**
 * UseCase to get RAID status from the server.
 */
class GetRaidStatusUseCase @Inject constructor(
    private val systemApi: SystemApi
) {
    suspend operator fun invoke(): Result<List<RaidArray>> {
        return try {
            val response = systemApi.getRaidStatus()
            
            // Map DTOs to domain models
            val raidArrays = response.arrays.map { arrayDto ->
                RaidArray(
                    name = arrayDto.name,
                    level = arrayDto.level,
                    sizeBytes = arrayDto.sizeBytes,
                    status = when (arrayDto.status.lowercase()) {
                        "optimal" -> RaidStatus.OPTIMAL
                        "degraded" -> RaidStatus.DEGRADED
                        "rebuilding" -> RaidStatus.REBUILDING
                        "failed" -> RaidStatus.FAILED
                        else -> RaidStatus.OPTIMAL
                    },
                    devices = arrayDto.devices.map { deviceDto ->
                        RaidDevice(
                            name = deviceDto.name,
                            state = com.baluhost.android.domain.model.RaidDeviceState.fromString(deviceDto.state)
                        )
                    },
                    resyncProgress = arrayDto.resyncProgress,
                    bitmap = arrayDto.bitmap,
                    syncAction = arrayDto.syncAction
                )
            }
            
            Result.Success(raidArrays)
        } catch (e: Exception) {
            Result.Error(e)
        }
    }
}
