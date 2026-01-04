package com.baluhost.android.data.repository

import android.util.Log
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.data.remote.api.VpnApi
import com.baluhost.android.data.remote.dto.GenerateVpnConfigRequest
import com.baluhost.android.data.remote.dto.UpdateVpnClientRequest
import com.baluhost.android.domain.model.VpnClient
import com.baluhost.android.domain.model.VpnConfig
import com.baluhost.android.domain.repository.VpnRepository
import com.baluhost.android.util.Result
import kotlinx.coroutines.flow.first
import javax.inject.Inject

/**
 * Implementation of VpnRepository.
 * 
 * Handles VPN operations with API and local storage.
 */
class VpnRepositoryImpl @Inject constructor(
    private val vpnApi: VpnApi,
    private val preferencesManager: PreferencesManager
) : VpnRepository {
    
    override suspend fun fetchVpnConfig(): Result<VpnConfig> = try {
        Log.d(TAG, "Fetching VPN config from backend")
        
        val response = vpnApi.generateConfig(GenerateVpnConfigRequest("Android Device"))
        
        val vpnConfig = VpnConfig(
            clientId = response.client.id,
            deviceName = response.client.deviceName,
            publicKey = response.client.publicKey,
            assignedIp = response.client.assignedIp,
            configString = response.config,
            configBase64 = response.configBase64,
            serverPublicKey = "", // From server config if needed
            serverEndpoint = "", // Parsed from config
            serverPort = 51820, // Default WireGuard port
            isActive = response.client.isActive,
            createdAt = response.client.createdAt,
            lastHandshake = response.client.lastHandshake
        )
        
        // Save to local storage
        saveVpnConfig(vpnConfig)
        
        Log.d(TAG, "VPN config fetched and saved successfully")
        Result.Success(vpnConfig)
        
    } catch (e: Exception) {
        Log.e(TAG, "Failed to fetch VPN config", e)
        
        // Try to return cached config on error
        val cachedConfig = getCachedVpnConfig()
        if (cachedConfig != null) {
            Log.d(TAG, "Returning cached VPN config")
            Result.Success(cachedConfig)
        } else {
            Result.Error(Exception("Failed to fetch VPN config: ${e.message}", e))
        }
    }
    
    override suspend fun generateVpnConfig(deviceName: String): Result<VpnConfig> = try {
        Log.d(TAG, "Generating new VPN config for device: $deviceName")
        
        val response = vpnApi.generateConfig(GenerateVpnConfigRequest(deviceName))
        
        val vpnConfig = VpnConfig(
            clientId = response.client.id,
            deviceName = response.client.deviceName,
            publicKey = response.client.publicKey,
            assignedIp = response.client.assignedIp,
            configString = response.config,
            configBase64 = response.configBase64,
            serverPublicKey = "",
            serverEndpoint = "",
            serverPort = 51820,
            isActive = response.client.isActive,
            createdAt = response.client.createdAt,
            lastHandshake = response.client.lastHandshake
        )
        
        // Save to local storage
        saveVpnConfig(vpnConfig)
        
        Log.d(TAG, "VPN config generated successfully")
        Result.Success(vpnConfig)
        
    } catch (e: Exception) {
        Log.e(TAG, "Failed to generate VPN config", e)
        Result.Error(Exception("Failed to generate VPN config: ${e.message}", e))
    }
    
    override suspend fun saveVpnConfig(config: VpnConfig): Result<Unit> = try {
        Log.d(TAG, "Saving VPN config locally")
        
        preferencesManager.saveVpnConfig(config.configString)
        preferencesManager.saveVpnClientId(config.clientId)
        preferencesManager.saveVpnDeviceName(config.deviceName)
        preferencesManager.saveVpnPublicKey(config.publicKey)
        preferencesManager.saveVpnAssignedIp(config.assignedIp)
        
        Log.d(TAG, "VPN config saved successfully")
        Result.Success(Unit)
        
    } catch (e: Exception) {
        Log.e(TAG, "Failed to save VPN config", e)
        Result.Error(Exception("Failed to save VPN config: ${e.message}", e))
    }
    
    override suspend fun getCachedVpnConfig(): VpnConfig? {
        return try {
            val configString = preferencesManager.getVpnConfig().first()
            
            if (configString.isNullOrEmpty()) {
                null
            } else {
                VpnConfig(
                    clientId = preferencesManager.getVpnClientId().first() ?: 0,
                    deviceName = preferencesManager.getVpnDeviceName().first() ?: "Unknown",
                    publicKey = preferencesManager.getVpnPublicKey().first() ?: "",
                    assignedIp = preferencesManager.getVpnAssignedIp().first() ?: "",
                    configString = configString,
                    configBase64 = null,
                    serverPublicKey = "",
                    serverEndpoint = "",
                    serverPort = 51820,
                    isActive = true
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to get cached VPN config", e)
            null
        }
    }
    
    override suspend fun getVpnClients(): Result<List<VpnClient>> = try {
        Log.d(TAG, "Fetching VPN clients")
        
        val response = vpnApi.getClients()
        
        val clients = response.clients.map { dto ->
            VpnClient(
                id = dto.id,
                userId = dto.userId,
                deviceName = dto.deviceName,
                publicKey = dto.publicKey,
                assignedIp = dto.assignedIp,
                isActive = dto.isActive,
                createdAt = dto.createdAt,
                lastHandshake = dto.lastHandshake
            )
        }
        
        Log.d(TAG, "VPN clients fetched: ${clients.size} clients")
        Result.Success(clients)
        
    } catch (e: Exception) {
        Log.e(TAG, "Failed to fetch VPN clients", e)
        Result.Error(Exception("Failed to fetch VPN clients: ${e.message}", e))
    }
    
    override suspend fun updateVpnClient(clientId: Int, isActive: Boolean): Result<VpnClient> = try {
        Log.d(TAG, "Updating VPN client: $clientId, isActive=$isActive")
        
        val response = vpnApi.updateClient(
            clientId,
            UpdateVpnClientRequest(isActive = isActive)
        )
        
        val client = VpnClient(
            id = response.id,
            userId = response.userId,
            deviceName = response.deviceName,
            publicKey = response.publicKey,
            assignedIp = response.assignedIp,
            isActive = response.isActive,
            createdAt = response.createdAt,
            lastHandshake = response.lastHandshake
        )
        
        Log.d(TAG, "VPN client updated successfully")
        Result.Success(client)
        
    } catch (e: Exception) {
        Log.e(TAG, "Failed to update VPN client", e)
        Result.Error(Exception("Failed to update VPN client: ${e.message}", e))
    }
    
    override suspend fun deleteVpnClient(clientId: Int): Result<Unit> = try {
        Log.d(TAG, "Deleting VPN client: $clientId")
        
        vpnApi.deleteClient(clientId)
        
        Log.d(TAG, "VPN client deleted successfully")
        Result.Success(Unit)
        
    } catch (e: Exception) {
        Log.e(TAG, "Failed to delete VPN client", e)
        Result.Error(Exception("Failed to delete VPN client: ${e.message}", e))
    }
    
    companion object {
        private const val TAG = "VpnRepositoryImpl"
    }
}
