package com.baluhost.android.data.sync

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.Data
import androidx.work.WorkerParameters
import com.baluhost.android.domain.model.sync.MigrationProgress
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class MigrationWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val source = inputData.getString(SyncMigrationManager.INPUT_SOURCE) ?: return@withContext Result.failure()
        val target = inputData.getString(SyncMigrationManager.INPUT_TARGET) ?: return@withContext Result.failure()
        val migrationId = inputData.getString(SyncMigrationManager.INPUT_MIGRATION_ID) ?: ""

        try {
            // naive recursive copy using ExternalStorageHelper
            val helper = ExternalStorageHelper()
            val srcFile = helper.uriToFile(source) ?: return@withContext Result.failure()
            val dstFile = helper.uriToFile(target) ?: return@withContext Result.failure()

            if (srcFile.isDirectory) {
                copyRecursively(helper, srcFile, dstFile)
            } else {
                val dst = if (dstFile.isDirectory) java.io.File(dstFile, srcFile.name) else dstFile
                srcFile.copyTo(dst, overwrite = true)
            }

            val progress = MigrationProgress(migrationId, "done", 100, 0L, 0L, null)
            setProgressAsync(Data.Builder().putInt("percent", 100).build())
            Result.success()
        } catch (ex: Exception) {
            Result.failure()
        }
    }

    private fun copyRecursively(helper: ExternalStorageHelper, src: java.io.File, dst: java.io.File) {
        if (!dst.exists()) dst.mkdirs()
        src.listFiles()?.forEach { child ->
            val childDst = java.io.File(dst, child.name)
            if (child.isDirectory) copyRecursively(helper, child, childDst)
            else child.copyTo(childDst, overwrite = true)
        }
    }
}
