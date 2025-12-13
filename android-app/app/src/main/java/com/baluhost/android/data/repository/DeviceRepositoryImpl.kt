package com.baluhost.android.data.repository

import android.util.Log
import com.baluhost.android.data.remote.api.MobileApi
import com.baluhost.android.domain.repository.DeviceRepository
import retrofit2.HttpException
import java.io.IOException
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
        try {
            Log.d("DeviceRepository", "Deleting device: $deviceId")
            val response = mobileApi.deleteDevice(deviceId)
            if (response.isSuccessful) {
                Log.d("DeviceRepository", "Device deleted successfully (${response.code()})")
            } else {
                val errorBody = response.errorBody()?.string()
                Log.e("DeviceRepository", "Delete failed: ${response.code()} - $errorBody")
                throw Exception("Server error (${response.code()}): $errorBody")
            }
        } catch (e: HttpException) {
            Log.e("DeviceRepository", "HTTP error deleting device: ${e.code()} - ${e.message()}")
            val errorBody = e.response()?.errorBody()?.string()
            Log.e("DeviceRepository", "Error body: $errorBody")
            throw Exception("Server error (${e.code()}): ${errorBody ?: e.message()}")
        } catch (e: IOException) {
            Log.e("DeviceRepository", "Network error deleting device", e)
            throw Exception("Network error: ${e.message}")
        } catch (e: Exception) {
            Log.e("DeviceRepository", "Unexpected error deleting device", e)
            throw Exception("Failed to delete device: ${e.message}")
        }
    }
}
