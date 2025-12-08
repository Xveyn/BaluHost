package com.baluhost.android.domain.model

/**
 * Domain model for Mobile Device.
 */
data class MobileDevice(
    val id: Int,
    val userId: Int,
    val deviceName: String,
    val deviceType: String,
    val deviceModel: String?,
    val lastSeen: String,
    val isActive: Boolean
)
