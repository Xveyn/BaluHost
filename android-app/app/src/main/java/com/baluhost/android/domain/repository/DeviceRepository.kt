package com.baluhost.android.domain.repository

/**
 * Repository for mobile device management operations.
 */
interface DeviceRepository {
    
    /**
     * Delete the current device from the server.
     * This will invalidate the device's access and remove it from the registered devices list.
     * 
     * @param deviceId The device ID to delete
     * @throws Exception if deletion fails
     */
    suspend fun deleteDevice(deviceId: String)
}
