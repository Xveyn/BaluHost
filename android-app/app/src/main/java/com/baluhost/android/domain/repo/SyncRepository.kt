package com.baluhost.android.domain.repo

import com.baluhost.android.domain.model.sync.*
import kotlinx.coroutines.flow.Flow

interface SyncRepository {
    suspend fun validateFolder(folderUri: String): Boolean
    suspend fun listFiles(folderUri: String): List<FileEntry>
    fun observeFolderSize(folderUri: String): Flow<Long>
    suspend fun getAvailableCapacity(parentUri: String): Long
    suspend fun copyWithTiming(srcUri: String, dstUri: String): OperationResult
    suspend fun deleteWithTiming(uri: String): OperationResult
    suspend fun startMigration(plan: MigrationPlan): MigrationHandle
    fun observeMigrationProgress(migrationId: String): Flow<MigrationProgress?>
    suspend fun cancelMigration(migrationId: String): Boolean
    suspend fun observeMetrics(folderUri: String): SyncMetrics
}
