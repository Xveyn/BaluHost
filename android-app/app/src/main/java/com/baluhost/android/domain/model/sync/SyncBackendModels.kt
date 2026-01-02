package com.baluhost.android.domain.model.sync

data class FolderStat(
    val uri: String,
    val totalSize: Long,
    val itemCount: Int,
    val lastScanTimestamp: Long
)

data class FileEntry(
    val uri: String,
    val name: String,
    val size: Long,
    val modifiedAt: Long,
    val isDirectory: Boolean
)

data class OperationResult(
    val success: Boolean,
    val durationMs: Long,
    val bytesTransferred: Long,
    val error: String?
)

data class MigrationPlan(
    val id: String,
    val sourceUri: String,
    val targetUri: String,
    val strategy: MigrationStrategy = MigrationStrategy.COPY_THEN_VERIFY,
    val options: Map<String, String> = emptyMap()
)

enum class MigrationStrategy { COPY_THEN_VERIFY, MIRROR }

data class MigrationHandle(
    val migrationId: String,
    val startTime: Long,
    val checkpoint: MigrationCheckpoint?
)

data class MigrationCheckpoint(
    val lastProcessedUri: String?,
    val completedCount: Int,
    val transferredBytes: Long,
    val checksumsVerified: Boolean
)

data class MigrationProgress(
    val migrationId: String,
    val status: String,
    val percent: Int,
    val transferredBytes: Long,
    val estimatedRemainingMs: Long,
    val currentItem: String?
)

data class SyncMetrics(
    val folderSize: Long,
    val freeSpace: Long,
    val copyDurations: List<Long>,
    val deleteDurations: List<Long>
)

data class FolderSize(val uri: String, val totalBytes: Long)
