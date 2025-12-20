package com.baluhost.android.domain.usecase.vpn

import android.content.Context
import android.util.Base64
import android.util.Log
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.domain.model.VpnConfig
import com.baluhost.android.util.Result
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject

/**
 * Use case for importing VPN configuration from QR code.
 * 
 * Parses Base64-encoded WireGuard config, saves it to preferences,
 * and prepares for Android VPN Service registration.
 */
class ImportVpnConfigUseCase @Inject constructor(
    @ApplicationContext private val context: Context,
    private val preferencesManager: PreferencesManager
) {
    
    suspend operator fun invoke(configBase64: String, autoRegister: Boolean = true): Result<VpnConfig> {
        return try {
            val configString = String(
                Base64.decode(configBase64, Base64.DEFAULT),
                Charsets.UTF_8
            )
            
            Log.d(TAG, "Importing VPN config (${configString.length} bytes)")
            
            // Save config to preferences
            preferencesManager.saveVpnConfig(configString)
            
            // Parse config to extract key information
            val config = parseWireGuardConfig(configString)
            
            Log.d(TAG, "VPN config parsed: IP=${config.assignedIp}, Endpoint=${config.serverEndpoint}")
            
            // Auto-register VPN tunnel if requested
            if (autoRegister) {
                try {
                    prepareVpnTunnel(config)
                    Log.d(TAG, "VPN tunnel prepared successfully")
                } catch (e: Exception) {
                    Log.w(TAG, "VPN tunnel preparation failed (will require manual setup): ${e.message}")
                    // Don't fail the import if VPN registration fails
                    // User can still connect manually via VPN screen
                }
            }
            
            Result.Success(config)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to import VPN config", e)
            Result.Error(Exception("Failed to import VPN config: ${e.message}", e))
        }
    }
    
    private fun parseWireGuardConfig(configString: String): VpnConfig {
        val lines = configString.lines()
        var clientId = 0
        var deviceName = ""
        var publicKey = ""
        var assignedIp = ""
        var serverPublicKey = ""
        var serverEndpoint = ""
        var serverPort = 51820
        
        var currentSection = ""
        for (line in lines) {
            val trimmed = line.trim()
            when {
                trimmed.startsWith("[") -> currentSection = trimmed
                currentSection == "[Interface]" -> {
                    when {
                        trimmed.startsWith("Address") -> {
                            assignedIp = trimmed.substringAfter("=").trim().substringBefore("/")
                        }
                    }
                }
                currentSection == "[Peer]" -> {
                    when {
                        trimmed.startsWith("PublicKey") -> {
                            serverPublicKey = trimmed.substringAfter("=").trim()
                        }
                        trimmed.startsWith("Endpoint") -> {
                            val endpoint = trimmed.substringAfter("=").trim()
                            serverEndpoint = endpoint.substringBefore(":")
                            serverPort = endpoint.substringAfter(":").toIntOrNull() ?: 51820
                        }
                    }
                }
            }
        }
        
        return VpnConfig(
            clientId = clientId,
            deviceName = deviceName,
            publicKey = publicKey,
            assignedIp = assignedIp,
            configString = configString,
            serverPublicKey = serverPublicKey,
            serverEndpoint = serverEndpoint,
            serverPort = serverPort
        )
    }
    
    /**
     * Prepare VPN tunnel configuration for Android VPN Service.
     * This stores the tunnel data and makes it ready for connection.
     * 
     * Note: Actual VPN connection requires VpnService.prepare() permission check.
     */
    private fun prepareVpnTunnel(config: VpnConfig) {
        // Store VPN configuration metadata
        // This will be used by VPN screen to show connection status
        Log.d(TAG, "Storing VPN tunnel metadata for ${config.serverEndpoint}")
        
        // Configuration is already saved in preferences by invoke()
        // VPN connection will be handled by VpnScreen when user activates it
        // or automatically when user clicks "Verbinden" in VpnStatusBanner
    }
    
    companion object {
        private const val TAG = "ImportVpnConfigUseCase"
    }
}
