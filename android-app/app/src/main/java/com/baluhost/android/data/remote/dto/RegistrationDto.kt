package com.baluhost.android.data.remote.dto

import com.google.gson.annotations.SerializedName

// ==================== Mobile Registration DTOs ====================

data class RegistrationQrData(
    val token: String,
    val server: String,
    @SerializedName("expires_at")
    val expiresAt: String,
    @SerializedName("vpn_config")
    val vpnConfig: String? = null
)

data class RegisterDeviceRequest(
    val token: String,
    @SerializedName("device_info")
    val deviceInfo: DeviceInfoDto
)

data class DeviceInfoDto(
    @SerializedName("device_name")
    val deviceName: String,
    @SerializedName("device_type")
    val deviceType: String = "android",
    @SerializedName("device_model")
    val deviceModel: String,
    @SerializedName("os_version")
    val osVersion: String,
    @SerializedName("app_version")
    val appVersion: String
)

data class RegisterDeviceResponse(
    @SerializedName("access_token")
    val accessToken: String,
    @SerializedName("refresh_token")
    val refreshToken: String,
    @SerializedName("token_type")
    val tokenType: String,
    val user: UserDto,
    val device: MobileDeviceDto
)

data class MobileDeviceDto(
    val id: Int,
    @SerializedName("user_id")
    val userId: Int,
    @SerializedName("device_name")
    val deviceName: String,
    @SerializedName("device_type")
    val deviceType: String,
    @SerializedName("device_model")
    val deviceModel: String?,
    @SerializedName("last_seen")
    val lastSeen: String,
    @SerializedName("is_active")
    val isActive: Boolean
)

data class CameraSettingsDto(
    @SerializedName("backup_enabled")
    val backupEnabled: Boolean,
    @SerializedName("wifi_only")
    val wifiOnly: Boolean,
    @SerializedName("backup_folder")
    val backupFolder: String
)

data class UpdateCameraSettingsRequest(
    @SerializedName("backup_enabled")
    val backupEnabled: Boolean?,
    @SerializedName("wifi_only")
    val wifiOnly: Boolean?,
    @SerializedName("backup_folder")
    val backupFolder: String?
)
