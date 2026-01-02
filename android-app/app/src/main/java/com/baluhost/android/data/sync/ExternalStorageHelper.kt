package com.baluhost.android.data.sync

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.withContext
import java.io.File
import java.net.URI

/**
 * Minimal helper for local storage operations used by `SyncRepositoryImpl`.
 * This helper is intentionally Android-free so it can be unit tested on the JVM.
 */
class ExternalStorageHelper() {

    suspend fun validateFolderUri(folderUri: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val file = uriToFile(folderUri) ?: return@withContext false
            file.exists() && file.isDirectory
        } catch (ex: Exception) {
            false
        }
    }

    suspend fun listFiles(folderUri: String): List<File> = withContext(Dispatchers.IO) {
        val file = uriToFile(folderUri) ?: return@withContext emptyList()
        file.listFiles()?.toList() ?: emptyList()
    }

    fun observeFolderSize(folderUri: String): Flow<Long> = flow {
        val size = runCatching {
            computeFolderSize(uriToFile(folderUri))
        }.getOrElse { 0L }
        emit(size)
    }

    suspend fun getAvailableCapacity(parentUri: String): Long = withContext(Dispatchers.IO) {
        val file = uriToFile(parentUri) ?: return@withContext 0L
        val stat = File(file.path)
        stat.freeSpace
    }

    suspend fun copyFileWithTiming(srcUri: String, dstUri: String): Pair<Boolean, Long> = withContext(Dispatchers.IO) {
        val start = System.currentTimeMillis()
        try {
            val src = uriToFile(srcUri) ?: return@withContext Pair(false, 0L)
            val dst = uriToFile(dstUri) ?: return@withContext Pair(false, 0L)
            src.copyTo(dst, overwrite = true)
            val dur = System.currentTimeMillis() - start
            Pair(true, dur)
        } catch (ex: Exception) {
            val dur = System.currentTimeMillis() - start
            Pair(false, dur)
        }
    }

    suspend fun deleteWithTiming(uri: String): Pair<Boolean, Long> = withContext(Dispatchers.IO) {
        val start = System.currentTimeMillis()
        try {
            val file = uriToFile(uri) ?: return@withContext Pair(false, 0L)
            val ok = file.deleteRecursively()
            Pair(ok, System.currentTimeMillis() - start)
        } catch (ex: Exception) {
            Pair(false, System.currentTimeMillis() - start)
        }
    }

    internal fun uriToFile(uriStr: String): File? {
        return try {
            val uri = URI.create(uriStr)
            if (uri.scheme == null || uri.scheme == "file") File(uri.path)
            else File(uri.path)
        } catch (ex: Exception) {
            null
        }
    }

    private fun computeFolderSize(file: File?): Long {
        if (file == null || !file.exists()) return 0L
        if (file.isFile) return file.length()
        var total = 0L
        val children = file.listFiles() ?: return 0L
        for (c in children) total += computeFolderSize(c)
        return total
    }
}

