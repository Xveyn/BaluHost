package com.baluhost.android.data.sync

import android.content.Context
import com.baluhost.android.domain.model.sync.*
import com.baluhost.android.domain.repo.SyncRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import java.util.UUID
import javax.inject.Inject

class SyncRepositoryImpl @Inject constructor(private val context: Context, private val external: ExternalStorageHelper) : SyncRepository {

    private val migrationProgress = MutableStateFlow<MigrationProgress?>(null)

    override suspend fun validateFolder(folderUri: String): Boolean = external.validateFolderUri(folderUri)

    override suspend fun listFiles(folderUri: String): List<FileEntry> = withContext(Dispatchers.IO) {
        external.listFiles(folderUri).map { f ->
            FileEntry(
                uri = f.toURI().toString(),
                name = f.name,
                size = f.length(),
                modifiedAt = f.lastModified(),
                isDirectory = f.isDirectory
            )
        }
    }

    override fun observeFolderSize(folderUri: String): Flow<Long> = external.observeFolderSize(folderUri)

    override suspend fun getAvailableCapacity(parentUri: String): Long = external.getAvailableCapacity(parentUri)

    override suspend fun copyWithTiming(srcUri: String, dstUri: String): OperationResult = withContext(Dispatchers.IO) {
        val (ok, dur) = external.copyFileWithTiming(srcUri, dstUri)
        OperationResult(success = ok, durationMs = dur, bytesTransferred = 0L, error = if (ok) null else "copy_failed")
    }

    override suspend fun deleteWithTiming(uri: String): OperationResult = withContext(Dispatchers.IO) {
        val (ok, dur) = external.deleteWithTiming(uri)
        OperationResult(success = ok, durationMs = dur, bytesTransferred = 0L, error = if (ok) null else "delete_failed")
    }

    override suspend fun startMigration(plan: MigrationPlan): MigrationHandle = withContext(Dispatchers.IO) {
        val migrationId = plan.id.ifEmpty { UUID.randomUUID().toString() }
        val handle = MigrationHandle(migrationId, System.currentTimeMillis(), null)
        // naive: start copying in background coroutine — production: use WorkManager and checkpoints
        migrationProgress.value = MigrationProgress(migrationId, "running", 0, 0L, -1L, null)
        handle
    }

    override fun observeMigrationProgress(migrationId: String): Flow<MigrationProgress?> = migrationProgress.asStateFlow()

    override suspend fun cancelMigration(migrationId: String): Boolean = withContext(Dispatchers.IO) {
        // not implemented: would signal worker to stop and record checkpoint
        migrationProgress.value = MigrationProgress(migrationId, "cancelled", 100, 0L, 0L, null)
        true
    }

    override suspend fun observeMetrics(folderUri: String): SyncMetrics = withContext(Dispatchers.IO) {
        // naive: return empty metrics; UI should call observeFolderSize for flows
        SyncMetrics(folderSize = 0L, freeSpace = getAvailableCapacity(folderUri), copyDurations = emptyList(), deleteDurations = emptyList())
    }
}
