package com.baluhost.android.domain.model

/**
 * Domain model for VPN configuration.
 */
data class VpnConfig(
    val clientId: Int,
    val deviceName: String,
    val publicKey: String,
    val assignedIp: String,
    val configString: String,      // Full WireGuard config
    val configBase64: String? = null,  // Base64 encoded (optional)
    val serverPublicKey: String,
    val serverEndpoint: String,
    val serverPort: Int,
    val allowedIps: List<String> = listOf("0.0.0.0/0"),
    val isActive: Boolean = true,
    val createdAt: String? = null,
    val lastHandshake: String? = null
)

/**
 * Domain model for VPN client.
 */
data class VpnClient(
    val id: Int,
    val userId: Int,
    val deviceName: String,
    val publicKey: String,
    val assignedIp: String,
    val isActive: Boolean,
    val createdAt: String,
    val lastHandshake: String? = null
)
