package com.baluhost.android.data.sync

import android.content.Context
import android.net.Uri
import androidx.documentfile.provider.DocumentFile
import com.baluhost.android.domain.adapter.CloudAdapter
import com.baluhost.android.domain.model.sync.FileEntry
import com.baluhost.android.domain.model.sync.FolderStat
import com.baluhost.android.domain.model.sync.OperationResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.InputStream

/**
 * Adapter for Android SAF-backed trees (DocumentFile). Implements CloudAdapter
 * to allow using the same abstraction for local-external and remote stores.
 */
class SAFStorageAdapter(private val context: Context) : CloudAdapter {

    override suspend fun authenticate(): Boolean = true

    override suspend fun list(path: String): List<FileEntry> = withContext(Dispatchers.IO) {
        val uri = Uri.parse(path)
        val tree = DocumentFile.fromTreeUri(context, uri) ?: return@withContext emptyList()
        tree.listFiles().map { df ->
            FileEntry(df.uri.toString(), df.name ?: "", df.length(), df.lastModified(), df.isDirectory)
        }
    }

    override suspend fun stat(path: String): FolderStat? = withContext(Dispatchers.IO) {
        val uri = Uri.parse(path)
        val tree = DocumentFile.fromTreeUri(context, uri) ?: return@withContext null
        FolderStat(tree.uri.toString(), computeSize(tree), tree.listFiles().size, System.currentTimeMillis())
    }

    override suspend fun download(remotePath: String, localDstUri: String): OperationResult = withContext(Dispatchers.IO) {
        try {
            val remote = DocumentFile.fromSingleUri(context, Uri.parse(remotePath)) ?: return@withContext OperationResult(false, 0, 0, "remote_not_found")
            val `in`: InputStream = context.contentResolver.openInputStream(remote.uri) ?: return@withContext OperationResult(false,0,0,"open_failed")
            val dstFile = File(Uri.parse(localDstUri).path ?: return@withContext OperationResult(false,0,0,"dst_invalid"))
            dstFile.outputStream().use { out -> `in`.use { input -> input.copyTo(out) } }
            OperationResult(true, 0, dstFile.length(), null)
        } catch (ex: Exception) {
            OperationResult(false, 0, 0, ex.message)
        }
    }

    override suspend fun upload(localSrcUri: String, remotePath: String): OperationResult = withContext(Dispatchers.IO) {
        try {
            val src = File(Uri.parse(localSrcUri).path ?: return@withContext OperationResult(false,0,0,"src_invalid"))
            val parent = DocumentFile.fromTreeUri(context, Uri.parse(remotePath)) ?: return@withContext OperationResult(false,0,0,"remote_parent_invalid")
            val created = parent.createFile("application/octet-stream", src.name ?: "file") ?: return@withContext OperationResult(false,0,0,"create_failed")
            context.contentResolver.openOutputStream(created.uri)?.use { out -> src.inputStream().use { it.copyTo(out) } }
            OperationResult(true, 0, src.length(), null)
        } catch (ex: Exception) {
            OperationResult(false, 0, 0, ex.message)
        }
    }

    override suspend fun delete(remotePath: String): OperationResult = withContext(Dispatchers.IO) {
        try {
            val df = DocumentFile.fromFile(File(Uri.parse(remotePath).path ?: return@withContext OperationResult(false,0,0,"invalid")))
            val ok = df.delete()
            OperationResult(ok, 0, 0, if (ok) null else "delete_failed")
        } catch (ex: Exception) {
            OperationResult(false, 0, 0, ex.message)
        }
    }

    override fun supportsResume(): Boolean = false

    private fun computeSize(df: DocumentFile): Long {
        if (df.isFile) return df.length()
        var total = 0L
        val children = df.listFiles()
        for (c in children) total += computeSize(c)
        return total
    }
}
