package com.baluhost.android.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * DTOs for system information and storage endpoints.
 * Matches backend schemas from system_schemas.py
 */

data class SystemInfoDto(
    @SerializedName("cpu")
    val cpu: CpuStatsDto,
    @SerializedName("memory")
    val memory: MemoryStatsDto,
    @SerializedName("disk")
    val disk: DiskStatsDto,
    @SerializedName("uptime")
    val uptime: Double,
    @SerializedName("dev_mode")
    val devMode: Boolean = false
)

data class CpuStatsDto(
    @SerializedName("usage_percent")
    val usagePercent: Double,
    @SerializedName("cores")
    val cores: Int,
    @SerializedName("frequency_mhz")
    val frequencyMhz: Double?
)

data class MemoryStatsDto(
    @SerializedName("total_bytes")
    val totalBytes: Long,
    @SerializedName("used_bytes")
    val usedBytes: Long,
    @SerializedName("available_bytes")
    val availableBytes: Long,
    @SerializedName("usage_percent")
    val usagePercent: Double
)

data class DiskStatsDto(
    @SerializedName("total_bytes")
    val totalBytes: Long,
    @SerializedName("used_bytes")
    val usedBytes: Long,
    @SerializedName("available_bytes")
    val availableBytes: Long,
    @SerializedName("usage_percent")
    val usagePercent: Double
)

data class RaidStatusResponseDto(
    @SerializedName("arrays")
    val arrays: List<RaidArrayDto>,
    @SerializedName("speed_limits")
    val speedLimits: RaidSpeedLimitsDto?
)

data class RaidArrayDto(
    @SerializedName("name")
    val name: String,
    @SerializedName("level")
    val level: String,
    @SerializedName("size_bytes")
    val sizeBytes: Long,
    @SerializedName("status")
    val status: String,
    @SerializedName("devices")
    val devices: List<RaidDeviceDto>,
    @SerializedName("resync_progress")
    val resyncProgress: Double?,
    @SerializedName("bitmap")
    val bitmap: String?,
    @SerializedName("sync_action")
    val syncAction: String?
)

data class RaidDeviceDto(
    @SerializedName("name")
    val name: String,
    @SerializedName("state")
    val state: String
)

data class RaidSpeedLimitsDto(
    @SerializedName("min_speed_kb")
    val minSpeedKb: Int,
    @SerializedName("max_speed_kb")
    val maxSpeedKb: Int
)

data class AvailableDisksResponseDto(
    @SerializedName("disks")
    val disks: List<AvailableDiskDto>
)

data class AvailableDiskDto(
    @SerializedName("name")
    val name: String,
    @SerializedName("size_bytes")
    val sizeBytes: Long,
    @SerializedName("model")
    val model: String?,
    @SerializedName("is_partitioned")
    val isPartitioned: Boolean = false,
    @SerializedName("partitions")
    val partitions: List<String> = emptyList(),
    @SerializedName("in_raid")
    val inRaid: Boolean = false
)
