package com.baluhost.android.data.sync

import android.content.Context
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequest
import androidx.work.WorkManager
import com.baluhost.android.domain.model.sync.MigrationHandle
import com.baluhost.android.domain.model.sync.MigrationPlan
import java.util.UUID

/**
 * Orchestrates migrations by enqueuing a WorkManager job (MigrationWorker).
 * Returns a MigrationHandle containing the work id and start time.
 */
class SyncMigrationManager(private val context: Context) {

    companion object {
        const val INPUT_SOURCE = "input_source"
        const val INPUT_TARGET = "input_target"
        const val INPUT_MIGRATION_ID = "input_migration_id"
    }

    fun startMigration(plan: MigrationPlan): MigrationHandle {
        val migrationId = if (plan.id.isNotEmpty()) plan.id else UUID.randomUUID().toString()
        val input = Data.Builder()
            .putString(INPUT_SOURCE, plan.sourceUri)
            .putString(INPUT_TARGET, plan.targetUri)
            .putString(INPUT_MIGRATION_ID, migrationId)
            .build()

        val work = OneTimeWorkRequest.Builder(MigrationWorker::class.java)
            .setInputData(input)
            .build()

        WorkManager.getInstance(context).enqueueUniqueWork(migrationId, ExistingWorkPolicy.REPLACE, work)

        return MigrationHandle(migrationId, System.currentTimeMillis(), null)
    }

    fun cancelMigration(migrationId: String) {
        WorkManager.getInstance(context).cancelUniqueWork(migrationId)
    }
}
