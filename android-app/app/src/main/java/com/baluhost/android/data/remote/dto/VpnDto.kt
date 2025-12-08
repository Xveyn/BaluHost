package com.baluhost.android.data.remote.dto

import com.google.gson.annotations.SerializedName

// ==================== VPN DTOs ====================

data class GenerateVpnConfigRequest(
    @SerializedName("device_name")
    val deviceName: String
)

data class VpnConfigResponse(
    val client: VpnClientDto,
    val config: String,
    @SerializedName("config_base64")
    val configBase64: String,
    @SerializedName("qr_code")
    val qrCode: String? = null
)

data class VpnClientDto(
    val id: Int,
    @SerializedName("user_id")
    val userId: Int,
    @SerializedName("device_name")
    val deviceName: String,
    @SerializedName("public_key")
    val publicKey: String,
    @SerializedName("assigned_ip")
    val assignedIp: String,
    @SerializedName("is_active")
    val isActive: Boolean,
    @SerializedName("created_at")
    val createdAt: String,
    @SerializedName("last_handshake")
    val lastHandshake: String?
)

data class VpnClientListResponse(
    val clients: List<VpnClientDto>
)

data class VpnServerConfigResponse(
    @SerializedName("server_public_key")
    val serverPublicKey: String,
    @SerializedName("server_ip")
    val serverIp: String,
    @SerializedName("server_port")
    val serverPort: Int,
    @SerializedName("network_cidr")
    val networkCidr: String
)

data class UpdateVpnClientRequest(
    @SerializedName("is_active")
    val isActive: Boolean? = null,
    @SerializedName("device_name")
    val deviceName: String? = null
)

data class VpnStatusResponse(
    @SerializedName("is_running")
    val isRunning: Boolean,
    @SerializedName("active_clients")
    val activeClients: Int
)
