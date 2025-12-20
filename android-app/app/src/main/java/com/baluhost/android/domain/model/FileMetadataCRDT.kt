package com.baluhost.android.domain.model

import java.time.Instant

/**
 * CRDT (Conflict-free Replicated Data Type) for file metadata.
 * 
 * Uses Last-Write-Wins (LWW) strategy with vector clocks for conflict resolution.
 * This ensures that concurrent updates from multiple devices can be merged
 * deterministically without conflicts.
 * 
 * Key principles:
 * - Every update gets a timestamp (Lamport timestamp)
 * - Later timestamps win
 * - If timestamps are equal, use device ID as tiebreaker
 * - Changes are commutative (order doesn't matter)
 */
data class FileMetadataCRDT(
    val path: String,
    val name: String,
    val size: Long,
    val isDirectory: Boolean,
    val modifiedAt: Instant,
    val version: Long,  // Lamport timestamp (logical clock)
    val deviceId: String,  // Device that made the last change
    val checksum: String? = null  // For detecting actual file changes
) {
    companion object {
        /**
         * Merge two CRDT states using Last-Write-Wins strategy.
         * 
         * Rules:
         * 1. Higher version (timestamp) wins
         * 2. If versions are equal, compare deviceId (alphabetically)
         * 3. If both are equal, they're the same update
         */
        fun merge(local: FileMetadataCRDT, remote: FileMetadataCRDT): FileMetadataCRDT {
            require(local.path == remote.path) {
                "Cannot merge metadata for different files: ${local.path} vs ${remote.path}"
            }
            
            return when {
                // Remote version is newer
                remote.version > local.version -> remote
                
                // Local version is newer
                local.version > remote.version -> local
                
                // Same version - use deviceId as tiebreaker
                remote.version == local.version -> {
                    if (remote.deviceId > local.deviceId) remote else local
                }
                
                // Should never happen
                else -> local
            }
        }
        
        /**
         * Check if update should be applied (true if remote is newer).
         */
        fun shouldApplyUpdate(local: FileMetadataCRDT, remote: FileMetadataCRDT): Boolean {
            return when {
                remote.version > local.version -> true
                local.version > remote.version -> false
                else -> remote.deviceId > local.deviceId  // Tiebreaker
            }
        }
    }
    
    /**
     * Create a new version with incremented timestamp.
     */
    fun incrementVersion(newDeviceId: String): FileMetadataCRDT {
        return copy(
            version = version + 1,
            deviceId = newDeviceId,
            modifiedAt = Instant.now()
        )
    }
    
    /**
     * Check if this CRDT is newer than another.
     */
    fun isNewerThan(other: FileMetadataCRDT): Boolean {
        return when {
            version > other.version -> true
            version < other.version -> false
            else -> deviceId > other.deviceId  // Tiebreaker
        }
    }
}

/**
 * CRDT-based file operation for offline queue.
 * Stores the CRDT state to replay on server when back online.
 */
data class CRDTOperation(
    val id: Long = 0,
    val operationType: OperationType,
    val metadata: FileMetadataCRDT,
    val localFilePath: String? = null,  // For uploads
    val createdAt: Instant = Instant.now(),
    val status: OperationStatus = OperationStatus.PENDING
)

/**
 * Vector clock for tracking causal dependencies between updates.
 * Maps deviceId -> version number.
 * 
 * Example:
 * Device A: {A: 5, B: 2, C: 1}  means:
 * - Device A has made 5 updates
 * - Device A has seen 2 updates from Device B
 * - Device A has seen 1 update from Device C
 */
data class VectorClock(
    val clocks: Map<String, Long> = emptyMap()
) {
    /**
     * Increment version for this device.
     */
    fun increment(deviceId: String): VectorClock {
        val currentVersion = clocks[deviceId] ?: 0
        return VectorClock(clocks + (deviceId to currentVersion + 1))
    }
    
    /**
     * Merge with another vector clock (take max of each device).
     */
    fun merge(other: VectorClock): VectorClock {
        val allDevices = (clocks.keys + other.clocks.keys).toSet()
        val mergedClocks = allDevices.associateWith { deviceId ->
            maxOf(clocks[deviceId] ?: 0, other.clocks[deviceId] ?: 0)
        }
        return VectorClock(mergedClocks)
    }
    
    /**
     * Check if this clock happened before another (causally).
     */
    fun happensBefore(other: VectorClock): Boolean {
        return clocks.all { (deviceId, version) ->
            version <= (other.clocks[deviceId] ?: 0)
        } && this != other
    }
    
    /**
     * Check if clocks are concurrent (no causal relationship).
     */
    fun isConcurrentWith(other: VectorClock): Boolean {
        return !happensBefore(other) && !other.happensBefore(this)
    }
}
