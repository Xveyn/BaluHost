package com.baluhost.android.data.sync

import com.baluhost.android.domain.adapter.CloudAdapter
import com.baluhost.android.domain.model.sync.FileEntry
import com.baluhost.android.domain.model.sync.FolderStat
import com.baluhost.android.domain.model.sync.OperationResult

/**
 * SMB adapter stub. For production, consider using jcifs-ng or SMBJ and implement authentication,
 * directory listing, streaming, and retries.
 */
class SmbAdapter : CloudAdapter {
    override suspend fun authenticate(): Boolean = false
    override suspend fun list(path: String): List<FileEntry> = emptyList()
    override suspend fun stat(path: String): FolderStat? = null
    override suspend fun download(remotePath: String, localDstUri: String): OperationResult = OperationResult(false,0,0,"not_implemented")
    override suspend fun upload(localSrcUri: String, remotePath: String): OperationResult = OperationResult(false,0,0,"not_implemented")
    override suspend fun delete(remotePath: String): OperationResult = OperationResult(false,0,0,"not_implemented")
    override fun supportsResume(): Boolean = false
}
