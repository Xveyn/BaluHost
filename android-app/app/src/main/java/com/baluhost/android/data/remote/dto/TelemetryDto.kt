package com.baluhost.android.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * DTO for telemetry history response.
 */
data class TelemetryHistoryDto(
    @SerializedName("cpu") val cpu: List<CpuDataPoint>,
    @SerializedName("memory") val memory: List<MemoryDataPoint>,
    @SerializedName("network") val network: List<NetworkDataPoint>
)

data class CpuDataPoint(
    @SerializedName("timestamp") val timestamp: String,
    @SerializedName("usage") val usage: Double
)

data class MemoryDataPoint(
    @SerializedName("timestamp") val timestamp: String,
    @SerializedName("used") val used: Long,
    @SerializedName("total") val total: Long,
    @SerializedName("percent") val percent: Double
)

data class NetworkDataPoint(
    @SerializedName("timestamp") val timestamp: String,
    @SerializedName("rx_bytes") val rxBytes: Long,
    @SerializedName("tx_bytes") val txBytes: Long
)

/**
 * DTO for aggregated storage response.
 */
data class StorageAggregatedDto(
    @SerializedName("used") val used: Long,
    @SerializedName("total") val total: Long,
    @SerializedName("available") val available: Long,
    @SerializedName("percent") val percent: Double
)
