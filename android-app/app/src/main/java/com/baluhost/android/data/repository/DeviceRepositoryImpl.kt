package com.baluhost.android.data.repository

import com.baluhost.android.data.remote.api.MobileApi
import com.baluhost.android.domain.repository.DeviceRepository
import javax.inject.Inject

/**
 * Implementation of DeviceRepository.
 * 
 * Handles mobile device management operations.
 */
class DeviceRepositoryImpl @Inject constructor(
    private val mobileApi: MobileApi
) : DeviceRepository {
    
    override suspend fun deleteDevice(deviceId: String) {
        mobileApi.deleteDevice(deviceId)
    }
}
