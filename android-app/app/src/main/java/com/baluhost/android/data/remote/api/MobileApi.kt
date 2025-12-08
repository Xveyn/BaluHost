package com.baluhost.android.data.remote.api

import com.baluhost.android.data.remote.dto.CameraSettingsDto
import com.baluhost.android.data.remote.dto.MobileDeviceDto
import com.baluhost.android.data.remote.dto.RegisterDeviceRequest
import com.baluhost.android.data.remote.dto.RegisterDeviceResponse
import com.baluhost.android.data.remote.dto.UpdateCameraSettingsRequest
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path

/**
 * Mobile device registration and management API endpoints.
 */
interface MobileApi {
    
    @POST("mobile/register")
    suspend fun registerDevice(
        @Body request: RegisterDeviceRequest
    ): RegisterDeviceResponse
    
    @GET("mobile/devices")
    suspend fun getDevices(): List<MobileDeviceDto>
    
    @GET("mobile/devices/{deviceId}")
    suspend fun getDevice(
        @Path("deviceId") deviceId: Int
    ): MobileDeviceDto
    
    @GET("mobile/camera/settings/{deviceId}")
    suspend fun getCameraSettings(
        @Path("deviceId") deviceId: Int
    ): CameraSettingsDto
    
    @PUT("mobile/camera/settings/{deviceId}")
    suspend fun updateCameraSettings(
        @Path("deviceId") deviceId: Int,
        @Body request: UpdateCameraSettingsRequest
    ): CameraSettingsDto
}
