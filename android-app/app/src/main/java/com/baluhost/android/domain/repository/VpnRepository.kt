package com.baluhost.android.domain.repository

import com.baluhost.android.domain.model.VpnClient
import com.baluhost.android.domain.model.VpnConfig
import com.baluhost.android.util.Result

/**
 * Repository interface for VPN operations.
 */
interface VpnRepository {
    
    /**
     * Fetch VPN configuration for current device.
     * Returns cached config if available, otherwise fetches from server.
     */
    suspend fun fetchVpnConfig(): Result<VpnConfig>
    
    /**
     * Generate new VPN configuration.
     */
    suspend fun generateVpnConfig(deviceName: String): Result<VpnConfig>
    
    /**
     * Save VPN configuration locally.
     */
    suspend fun saveVpnConfig(config: VpnConfig): Result<Unit>
    
    /**
     * Get cached VPN configuration.
     */
    suspend fun getCachedVpnConfig(): VpnConfig?
    
    /**
     * Get list of all VPN clients for user.
     */
    suspend fun getVpnClients(): Result<List<VpnClient>>
    
    /**
     * Update VPN client (e.g., deactivate).
     */
    suspend fun updateVpnClient(clientId: Int, isActive: Boolean): Result<VpnClient>
    
    /**
     * Delete/revoke VPN client.
     */
    suspend fun deleteVpnClient(clientId: Int): Result<Unit>
}
