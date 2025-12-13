package com.baluhost.android.domain.service

import com.baluhost.android.domain.model.sync.*
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Service for detecting and handling file conflicts during synchronization.
 * 
 * Conflict detection rules:
 * 1. Both local and remote files modified since last sync -> CONFLICT
 * 2. Only local modified -> UPLOAD
 * 3. Only remote modified -> DOWNLOAD
 * 4. Neither modified -> NO_ACTION
 * 5. File exists only locally -> UPLOAD
 * 6. File exists only remotely -> DOWNLOAD
 * 
 * Best Practices:
 * - Immutable data structures
 * - Pure functions (no side effects)
 * - Timestamp-based conflict detection
 * - Hash-based change detection
 */
@Singleton
class ConflictDetectionService @Inject constructor() {
    
    /**
     * Action to take for a file during sync.
     */
    enum class SyncAction {
        UPLOAD,      // Upload local version to server
        DOWNLOAD,    // Download server version to local
        CONFLICT,    // Manual resolution required
        NO_ACTION,   // File is up-to-date
        DELETE_LOCAL,   // Delete local file (deleted on server)
        DELETE_REMOTE   // Delete remote file (deleted locally)
    }
    
    /**
     * Result of conflict detection for a single file.
     */
    data class ConflictCheckResult(
        val relativePath: String,
        val action: SyncAction,
        val localInfo: LocalFileInfo?,
        val remoteInfo: RemoteFileInfo?,
        val reason: String
    )
    
    /**
     * Local file information for conflict detection.
     */
    data class LocalFileInfo(
        val relativePath: String,
        val hash: String,
        val size: Long,
        val modifiedAt: Long
    )
    
    /**
     * Batch conflict detection result.
     */
    data class ConflictAnalysisResult(
        val toUpload: List<ConflictCheckResult>,
        val toDownload: List<ConflictCheckResult>,
        val conflicts: List<ConflictCheckResult>,
        val noAction: List<ConflictCheckResult>,
        val summary: ConflictSummary
    )
    
    data class ConflictSummary(
        val totalFiles: Int,
        val uploadsNeeded: Int,
        val downloadsNeeded: Int,
        val conflictsFound: Int,
        val noActionNeeded: Int
    )
    
    /**
     * Detect conflicts between local and remote files.
     * 
     * @param localFiles List of local files with metadata
     * @param remoteFiles List of remote files with metadata
     * @param lastSyncTime Timestamp of last successful sync (null if first sync)
     * @return Action to take for each file
     */
    fun analyzeConflicts(
        localFiles: List<LocalFileInfo>,
        remoteFiles: List<RemoteFileInfo>,
        lastSyncTime: Long?
    ): ConflictAnalysisResult {
        val results = mutableListOf<ConflictCheckResult>()
        
        // Create maps for efficient lookup
        val localMap = localFiles.associateBy { it.relativePath }
        val remoteMap = remoteFiles.associateBy { it.relativePath }
        
        // Get all unique file paths
        val allPaths = (localFiles.map { it.relativePath } + remoteFiles.map { it.relativePath }).distinct()
        
        // Analyze each file
        for (path in allPaths) {
            val local = localMap[path]
            val remote = remoteMap[path]
            
            val result = when {
                // File exists in both locations
                local != null && remote != null -> {
                    detectConflictForExistingFile(local, remote, lastSyncTime)
                }
                
                // File only exists locally
                local != null && remote == null -> {
                    ConflictCheckResult(
                        relativePath = path,
                        action = SyncAction.UPLOAD,
                        localInfo = local,
                        remoteInfo = null,
                        reason = "New local file"
                    )
                }
                
                // File only exists remotely
                local == null && remote != null -> {
                    ConflictCheckResult(
                        relativePath = path,
                        action = SyncAction.DOWNLOAD,
                        localInfo = null,
                        remoteInfo = remote,
                        reason = "New remote file"
                    )
                }
                
                else -> error("Impossible state: file path with no files")
            }
            
            results.add(result)
        }
        
        // Group results by action
        val toUpload = results.filter { it.action == SyncAction.UPLOAD }
        val toDownload = results.filter { it.action == SyncAction.DOWNLOAD }
        val conflicts = results.filter { it.action == SyncAction.CONFLICT }
        val noAction = results.filter { it.action == SyncAction.NO_ACTION }
        
        return ConflictAnalysisResult(
            toUpload = toUpload,
            toDownload = toDownload,
            conflicts = conflicts,
            noAction = noAction,
            summary = ConflictSummary(
                totalFiles = results.size,
                uploadsNeeded = toUpload.size,
                downloadsNeeded = toDownload.size,
                conflictsFound = conflicts.size,
                noActionNeeded = noAction.size
            )
        )
    }
    
    /**
     * Detect conflict for a file that exists in both locations.
     */
    private fun detectConflictForExistingFile(
        local: LocalFileInfo,
        remote: RemoteFileInfo,
        lastSyncTime: Long?
    ): ConflictCheckResult {
        // If hashes match, no action needed
        if (local.hash == remote.hash) {
            return ConflictCheckResult(
                relativePath = local.relativePath,
                action = SyncAction.NO_ACTION,
                localInfo = local,
                remoteInfo = remote,
                reason = "Files are identical (hash match)"
            )
        }
        
        // If no last sync time, use timestamp comparison
        if (lastSyncTime == null) {
            return if (local.modifiedAt > remote.modifiedAt) {
                ConflictCheckResult(
                    relativePath = local.relativePath,
                    action = SyncAction.UPLOAD,
                    localInfo = local,
                    remoteInfo = remote,
                    reason = "Local file is newer (first sync)"
                )
            } else if (remote.modifiedAt > local.modifiedAt) {
                ConflictCheckResult(
                    relativePath = local.relativePath,
                    action = SyncAction.DOWNLOAD,
                    localInfo = local,
                    remoteInfo = remote,
                    reason = "Remote file is newer (first sync)"
                )
            } else {
                // Same timestamp but different hash - conflict
                ConflictCheckResult(
                    relativePath = local.relativePath,
                    action = SyncAction.CONFLICT,
                    localInfo = local,
                    remoteInfo = remote,
                    reason = "Same timestamp but different content"
                )
            }
        }
        
        // Check if files were modified after last sync
        val localModifiedAfterSync = local.modifiedAt > lastSyncTime
        val remoteModifiedAfterSync = remote.modifiedAt > lastSyncTime
        
        return when {
            // Both modified after last sync -> CONFLICT
            localModifiedAfterSync && remoteModifiedAfterSync -> {
                ConflictCheckResult(
                    relativePath = local.relativePath,
                    action = SyncAction.CONFLICT,
                    localInfo = local,
                    remoteInfo = remote,
                    reason = "Both files modified since last sync"
                )
            }
            
            // Only local modified -> UPLOAD
            localModifiedAfterSync && !remoteModifiedAfterSync -> {
                ConflictCheckResult(
                    relativePath = local.relativePath,
                    action = SyncAction.UPLOAD,
                    localInfo = local,
                    remoteInfo = remote,
                    reason = "Local file modified since last sync"
                )
            }
            
            // Only remote modified -> DOWNLOAD
            !localModifiedAfterSync && remoteModifiedAfterSync -> {
                ConflictCheckResult(
                    relativePath = local.relativePath,
                    action = SyncAction.DOWNLOAD,
                    localInfo = local,
                    remoteInfo = remote,
                    reason = "Remote file modified since last sync"
                )
            }
            
            // Neither modified but hashes differ (edge case)
            else -> {
                ConflictCheckResult(
                    relativePath = local.relativePath,
                    action = SyncAction.CONFLICT,
                    localInfo = local,
                    remoteInfo = remote,
                    reason = "Files differ but timestamps unchanged"
                )
            }
        }
    }
    
    /**
     * Resolve a conflict based on the specified resolution strategy.
     */
    fun resolveConflict(
        conflict: FileConflict,
        resolution: ConflictResolution
    ): SyncAction {
        return when (resolution) {
            ConflictResolution.KEEP_LOCAL -> SyncAction.UPLOAD
            ConflictResolution.KEEP_SERVER -> SyncAction.DOWNLOAD
            ConflictResolution.KEEP_NEWEST -> {
                if (conflict.localModifiedAt > conflict.remoteModifiedAt) {
                    SyncAction.UPLOAD
                } else {
                    SyncAction.DOWNLOAD
                }
            }
            ConflictResolution.ASK_USER -> SyncAction.CONFLICT // Let dialog handle
        }
    }
    
    /**
     * Resolve multiple conflicts in batch.
     */
    fun resolveConflicts(
        conflicts: List<FileConflict>,
        resolution: ConflictResolution
    ): Map<String, SyncAction> {
        return conflicts.associate { conflict ->
            conflict.relativePath to resolveConflict(conflict, resolution)
        }
    }
    
    /**
     * Check if automatic resolution is possible.
     */
    fun canAutoResolve(
        conflict: FileConflict,
        resolution: ConflictResolution
    ): Boolean {
        return resolution != ConflictResolution.ASK_USER
    }
    
    /**
     * Get human-readable conflict reason.
     */
    fun getConflictReason(conflict: FileConflict): String {
        return when {
            conflict.localModifiedAt > conflict.remoteModifiedAt -> {
                "Lokale Datei ist neuer (${formatTimeDiff(conflict.localModifiedAt - conflict.remoteModifiedAt)} neuer)"
            }
            conflict.remoteModifiedAt > conflict.localModifiedAt -> {
                "Server-Datei ist neuer (${formatTimeDiff(conflict.remoteModifiedAt - conflict.localModifiedAt)} neuer)"
            }
            else -> {
                "Beide Dateien haben den gleichen Zeitstempel, aber unterschiedlichen Inhalt"
            }
        }
    }
    
    /**
     * Format time difference in human-readable format.
     */
    private fun formatTimeDiff(millisDiff: Long): String {
        val seconds = millisDiff / 1000
        val minutes = seconds / 60
        val hours = minutes / 60
        val days = hours / 24
        
        return when {
            days > 0 -> "$days Tag${if (days != 1L) "e" else ""}"
            hours > 0 -> "$hours Stunde${if (hours != 1L) "n" else ""}"
            minutes > 0 -> "$minutes Minute${if (minutes != 1L) "n" else ""}"
            else -> "$seconds Sekunde${if (seconds != 1L) "n" else ""}"
        }
    }
}
