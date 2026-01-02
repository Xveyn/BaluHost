package com.baluhost.android.domain.adapter

import com.baluhost.android.domain.model.sync.FileEntry
import com.baluhost.android.domain.model.sync.FolderStat
import com.baluhost.android.domain.model.sync.OperationResult

interface CloudAdapter {
    suspend fun authenticate(): Boolean
    suspend fun list(path: String): List<FileEntry>
    suspend fun stat(path: String): FolderStat?
    suspend fun download(remotePath: String, localDstUri: String): OperationResult
    suspend fun upload(localSrcUri: String, remotePath: String): OperationResult
    suspend fun delete(remotePath: String): OperationResult
    fun supportsResume(): Boolean
}
