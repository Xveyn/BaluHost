package com.baluhost.android.data.remote.api

import com.baluhost.android.data.remote.dto.GenerateVpnConfigRequest
import com.baluhost.android.data.remote.dto.UpdateVpnClientRequest
import com.baluhost.android.data.remote.dto.VpnClientDto
import com.baluhost.android.data.remote.dto.VpnClientListResponse
import com.baluhost.android.data.remote.dto.VpnConfigResponse
import com.baluhost.android.data.remote.dto.VpnServerConfigResponse
import com.baluhost.android.data.remote.dto.VpnStatusResponse
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path

/**
 * VPN management API endpoints.
 */
interface VpnApi {
    
    @POST("vpn/generate-config")
    suspend fun generateConfig(
        @Body request: GenerateVpnConfigRequest
    ): VpnConfigResponse
    
    @GET("vpn/clients")
    suspend fun getClients(): VpnClientListResponse
    
    @GET("vpn/clients/{clientId}")
    suspend fun getClient(
        @Path("clientId") clientId: Int
    ): VpnClientDto
    
    @PUT("vpn/clients/{clientId}")
    suspend fun updateClient(
        @Path("clientId") clientId: Int,
        @Body request: UpdateVpnClientRequest
    ): VpnClientDto
    
    @DELETE("vpn/clients/{clientId}")
    suspend fun deleteClient(
        @Path("clientId") clientId: Int
    ): VpnClientDto
    
    @POST("vpn/clients/{clientId}/revoke")
    suspend fun revokeClient(
        @Path("clientId") clientId: Int
    ): VpnClientDto
    
    @GET("vpn/server-config")
    suspend fun getServerConfig(): VpnServerConfigResponse
    
    @GET("vpn/status")
    suspend fun getStatus(): VpnStatusResponse
}
