package com.baluhost.android.domain.usecase.vpn

import android.util.Base64
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.domain.model.VpnConfig
import com.baluhost.android.util.Result
import javax.inject.Inject

/**
 * Use case for importing VPN configuration from QR code.
 * 
 * Parses Base64-encoded WireGuard config and saves it to preferences.
 */
class ImportVpnConfigUseCase @Inject constructor(
    private val preferencesManager: PreferencesManager
) {
    
    suspend operator fun invoke(configBase64: String): Result<VpnConfig> {
        return try {
            val configString = String(
                Base64.decode(configBase64, Base64.DEFAULT),
                Charsets.UTF_8
            )
            
            // Save config to preferences
            preferencesManager.saveVpnConfig(configString)
            
            // Parse config to extract key information
            val config = parseWireGuardConfig(configString)
            
            Result.Success(config)
        } catch (e: Exception) {
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
}
