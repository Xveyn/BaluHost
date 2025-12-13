package com.baluhost.android.data.remote.api

import com.baluhost.android.data.remote.dto.*
import retrofit2.http.GET
import retrofit2.http.Path

/**
 * API interface for system and storage endpoints.
 */
interface SystemApi {
    
    @GET("system/info")
    suspend fun getSystemInfo(): SystemInfoDto
    
    @GET("system/raid/status")
    suspend fun getRaidStatus(): RaidStatusResponseDto
    
    @GET("system/raid/available-disks")
    suspend fun getAvailableDisks(): AvailableDisksResponseDto
}
